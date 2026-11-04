"""推送通道共用：错误类型、重试、幂等账本、分段投递、Markdown→HTML。

约定（ARCHITECTURE §5、§10）：
- 每个通道自己处理长度限制和分段；本模块提供 ``deliver_parts`` 统一完成
  "逐段发送 + 失败最多重试 2 次（指数退避）+ 按 report_id+channel_id 幂等"。
- 幂等账本存在 ``data/cache/deliveries/<channel_id>.json``：记录每份报告已成功的段号。
  同一报告再次投递时跳过已发出的段，只补发失败的段；测试消息（is_test）不记账。
- 错误信息一律中文，且不得包含密钥、Webhook 地址或完整正文。
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import json
import logging
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx

from bureau.contracts import DeliveryResult, ReportPayload

log = logging.getLogger("bureau.channel")

MAX_RETRIES = 2                 # 失败后最多再试 2 次
RETRY_BASE_DELAY = 1.0          # 第 1 次重试前等 1 秒，第 2 次等 2 秒
HTTP_TIMEOUT = httpx.Timeout(20.0, connect=8.0)


class SendError(Exception):
    """一次发送失败。message 必须是可直接展示给用户的中文，不含密钥。"""

    def __init__(self, message: str, *, retryable: bool = False, code: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.code = code


@dataclass
class PartOutcome:
    external_id: str | None = None
    note: str | None = None


# ---------------------------------------------------------------- HTTP 小工具

def scrub(text: str, *secrets: str | None) -> str:
    """把出现在文本里的密钥替换成 ***，防止异常信息泄露。"""
    out = text or ""
    for s in secrets:
        if s and len(s) >= 4:
            out = out.replace(s, "***")
    return out


async def post_json(
    url: str,
    payload: Any,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
    headers: dict[str, str] | None = None,
    timeout: httpx.Timeout | float = HTTP_TIMEOUT,
    secrets: tuple[str | None, ...] = (),
    service: str = "服务",
) -> tuple[int, Any]:
    """POST JSON，返回 (HTTP 状态码, 解析后的 JSON 或 None)。

    网络错误转成可重试的 SendError；不调用 raise_for_status，避免异常里带出含密钥的 URL。
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    hdrs = {"Content-Type": "application/json; charset=utf-8"}
    hdrs.update(headers or {})
    try:
        async with httpx.AsyncClient(timeout=timeout, transport=transport, follow_redirects=False) as client:
            resp = await client.post(url, content=body, headers=hdrs)
    except httpx.TimeoutException:
        raise SendError(f"连接{service}超时，请检查网络", retryable=True) from None
    except httpx.HTTPError as exc:
        reason = scrub(type(exc).__name__, *secrets)
        raise SendError(f"无法连接{service}（{reason}），请检查网络或代理设置", retryable=True) from None
    try:
        data = resp.json()
    except ValueError:
        data = None
    return resp.status_code, data


def http_status_error(status: int, service: str) -> SendError:
    """非 2xx 的统一中文错误；429 与 5xx 视为可重试。"""
    if status == 429:
        return SendError(f"{service}返回 429：请求过于频繁，请稍后再试", retryable=True, code=status)
    if status >= 500:
        return SendError(f"{service}暂时不可用（HTTP {status}），稍后会自动重试", retryable=True, code=status)
    if status in (401, 403):
        return SendError(f"{service}拒绝了请求（HTTP {status}），请检查密钥是否正确", code=status)
    if status == 404:
        return SendError(f"{service}地址不存在（HTTP 404），请检查地址或密钥", code=status)
    return SendError(f"{service}返回异常状态 HTTP {status}", code=status)


# ---------------------------------------------------------------- 重试

async def with_retries(
    fn: Callable[[], Awaitable[PartOutcome]],
    *,
    retries: int = MAX_RETRIES,
    base_delay: float = RETRY_BASE_DELAY,
) -> PartOutcome:
    """执行 fn；遇到 retryable 的 SendError 时按 1s、2s 指数退避重试，最多 retries 次。"""
    attempt = 0
    while True:
        try:
            return await fn()
        except SendError as exc:
            if not exc.retryable or attempt >= retries:
                raise
            delay = base_delay * (2 ** attempt)
            attempt += 1
            log.info("推送失败，%.1f 秒后第 %d 次重试：%s", delay, attempt, exc.message)
            if delay > 0:
                await asyncio.sleep(delay)


# ---------------------------------------------------------------- 幂等

def idempotency_key(report: ReportPayload, channel_id: str, part: int | None = None, *, max_len: int = 50) -> str:
    """由 report_id + channel_id（+ 段号）生成稳定的幂等键，长度不超过 max_len。

    测试消息（is_test）每次都要真的发出去，所以加上时间戳避免被平台去重。
    """
    seed = f"{report.report_id}|{channel_id}"
    if report.is_test:
        seed += f"|{time.time_ns()}"
    key = "ib-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:32]
    if part is not None:
        key += f"-p{part}"
    return key[:max_len]


_LEDGER_LOCK = threading.Lock()
_LEDGER_KEEP = 300


class DeliveryLedger:
    """每个通道一份 JSON：{report_id: {"fp": 内容指纹, "parts": [已成功的段号], "ext": {段号: 外部ID}}}。"""

    def __init__(self, data_dir: Path, channel_id: str) -> None:
        safe = re.sub(r"[^A-Za-z0-9_.-]", "_", channel_id) or "channel"
        self.path = Path(data_dir) / "cache" / "deliveries" / f"{safe}.json"

    def _load(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save(self, data: dict[str, Any]) -> None:
        if len(data) > _LEDGER_KEEP:
            for key in sorted(data, key=lambda k: data[k].get("ts", 0))[: len(data) - _LEDGER_KEEP]:
                data.pop(key, None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ledger-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False)
            os.replace(tmp, self.path)
        except OSError:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    def sent_parts(self, report_id: str, fingerprint: str) -> dict[int, str | None]:
        with _LEDGER_LOCK:
            entry = self._load().get(report_id) or {}
        if entry.get("fp") != fingerprint:
            return {}
        ext = entry.get("ext") or {}
        return {int(p): ext.get(str(p)) for p in entry.get("parts", [])}

    def mark(self, report_id: str, fingerprint: str, part: int, external_id: str | None) -> None:
        with _LEDGER_LOCK:
            data = self._load()
            entry = data.get(report_id)
            if not entry or entry.get("fp") != fingerprint:
                entry = {"fp": fingerprint, "parts": [], "ext": {}}
            if part not in entry["parts"]:
                entry["parts"].append(part)
            if external_id:
                entry["ext"][str(part)] = external_id
            entry["ts"] = time.time()
            data[report_id] = entry
            try:
                self._save(data)
            except OSError as exc:      # 记账失败不影响本次投递结果
                log.warning("写入投递账本失败：%s", type(exc).__name__)


def fingerprint(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()[:16]


@dataclass
class DeliveryPlan:
    """一次投递的上下文。"""
    channel: Any                         # bureau.channels.base.Channel 实例
    report: ReportPayload
    parts: list[str]
    unit: str = "条"                      # 详情里的量词："条消息" / "张卡片" / "封邮件"
    interval: float = 0.0                 # 段间隔（秒）
    retries: int = MAX_RETRIES
    retry_base_delay: float | None = None
    notes: list[str] = field(default_factory=list)


async def deliver_parts(
    plan: DeliveryPlan,
    send_one: Callable[[int, str], Awaitable[PartOutcome]],
) -> DeliveryResult:
    """逐段发送并处理重试与幂等；永远不抛异常，失败时返回 ok=False 的 DeliveryResult。

    send_one(index, text) 负责真正发出第 index 段（从 0 开始）；失败时抛 SendError。
    """
    ch = plan.channel
    report = plan.report
    parts = [p for p in plan.parts if p and p.strip()]
    if not parts:
        return ch.result(False, "没有可发送的内容（报告正文为空）", parts=0)
    total = len(parts)
    # 通道实例可以设置 retry_base_delay 属性（测试里设为 0，避免真的等待）
    base_delay = (plan.retry_base_delay if plan.retry_base_delay is not None
                  else float(getattr(ch, "retry_base_delay", RETRY_BASE_DELAY)))
    ledger = None if report.is_test else DeliveryLedger(ch.ctx.data_dir, ch.ctx.channel_id)
    fp = fingerprint(parts)
    done: dict[int, str | None] = ledger.sent_parts(report.report_id, fp) if ledger else {}
    if ledger and len(done) >= total:
        last = done.get(total - 1)
        return ch.result(True, f"该报告已投递过（共 {total} {plan.unit}），本次跳过重复发送",
                         external_id=last, parts=total)

    last_ext: str | None = None
    sent_now = 0
    first = True
    for idx, text in enumerate(parts):
        if idx in done:
            last_ext = done[idx] or last_ext
            continue
        if not first and plan.interval > 0:
            await asyncio.sleep(plan.interval)
        first = False

        async def attempt(i: int = idx, t: str = text) -> PartOutcome:
            return await send_one(i, t)

        try:
            outcome = await with_retries(attempt, retries=plan.retries, base_delay=base_delay)
        except SendError as exc:
            prefix = f"第 {idx + 1}/{total} {plan.unit}发送失败：" if total > 1 else "发送失败："
            tail = f"（此前已成功 {idx} {plan.unit}，再次投递时只补发剩余部分）" if idx else ""
            ch.ctx.logger.warning("[%s] %s%s", ch.ctx.channel_id, prefix, exc.message)
            return ch.result(False, prefix + exc.message + tail, retryable=exc.retryable,
                             parts=idx, external_id=last_ext)
        except Exception as exc:  # noqa: BLE001 — 通道约定不得抛异常
            ch.ctx.logger.exception("[%s] 推送出现未预期的错误", ch.ctx.channel_id)
            return ch.result(False, f"推送出现未预期的错误（{type(exc).__name__}），详情见日志",
                             retryable=True, parts=idx, external_id=last_ext)
        sent_now += 1
        last_ext = outcome.external_id or last_ext
        if outcome.note:
            plan.notes.append(outcome.note)
        if ledger:
            ledger.mark(report.report_id, fp, idx, outcome.external_id)

    detail = f"已发送 {total} {plan.unit}" if total > 1 else "发送成功"
    if done:
        detail = f"补发 {sent_now} {plan.unit}，共 {total} {plan.unit}已全部送达"
    if plan.notes:
        detail += "；" + "；".join(dict.fromkeys(plan.notes))
    return ch.result(True, detail, external_id=last_ext, parts=total)


def number_parts(parts: list[str], fmt: str = "（{i}/{n}）") -> list[str]:
    """多段时在每段开头加序号。"""
    if len(parts) <= 1:
        return parts
    n = len(parts)
    return [fmt.format(i=i + 1, n=n) + p for i, p in enumerate(parts)]


def with_dashboard_link(text: str, url: str | None, *, markdown: bool = True) -> str:
    """正文里还没有工作台链接时，在末尾补一行。"""
    if not url or url in (text or ""):
        return text
    line = f"[完整报告：在工作台查看]({url})" if markdown else f"完整报告：{url}"
    return (text or "").rstrip() + "\n\n" + line


def report_markdown(report: ReportPayload) -> str:
    """推送用的 Markdown：summary_md（为空时退回 full_md）+ 工作台链接。"""
    body = (report.summary_md or "").strip() or (report.full_md or "").strip()
    return with_dashboard_link(body, report.dashboard_url)


def report_text(report: ReportPayload) -> str:
    """推送用的纯文本：summary_text（为空时由 summary_md 粗略去标记）+ 工作台链接。"""
    body = (report.summary_text or "").strip() or strip_markdown(report.summary_md or "")
    return with_dashboard_link(body, report.dashboard_url, markdown=False)


# ---------------------------------------------------------------- Markdown

_MD_LINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MD_CODE = re.compile(r"`([^`\n]+)`")


def strip_markdown(md: str) -> str:
    """Markdown → 近似纯文本。"""
    out = []
    for line in (md or "").splitlines():
        s = re.sub(r"^\s{0,3}#{1,6}\s+", "", line)
        s = re.sub(r"^\s{0,3}>\s?", "", s)
        s = _MD_LINK.sub(lambda m: f"{m.group(1)}（{m.group(2)}）", s)
        s = _MD_BOLD.sub(r"\1", s)
        s = _MD_CODE.sub(r"\1", s)
        out.append(s)
    return "\n".join(out).strip()


def _inline(text: str) -> str:
    s = html.escape(text, quote=True)
    s = _MD_CODE.sub(lambda m: f"<code>{m.group(1)}</code>", s)
    s = _MD_BOLD.sub(lambda m: f"<strong>{m.group(1)}</strong>", s)
    # 链接只允许 http/https；URL 已经过 html.escape
    s = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)",
               lambda m: f'<a href="{m.group(2)}">{m.group(1)}</a>', s)
    return s


def markdown_to_html(md: str) -> str:
    """把 summary_md 这类简单 Markdown 转成邮件可用的 HTML 片段。

    只支持标题、列表、引用、分隔线、粗体、行内代码、链接；原始 HTML 一律转义。
    """
    out: list[str] = []
    para: list[str] = []
    list_tag: str | None = None

    def flush_para() -> None:
        if para:
            out.append("<p>" + "<br>".join(_inline(x) for x in para) + "</p>")
            para.clear()

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            out.append(f"</{list_tag}>")
            list_tag = None

    for raw in (md or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush_para()
            close_list()
            continue
        m_h = re.match(r"^\s{0,3}(#{1,6})\s+(.*)$", line)
        m_ul = re.match(r"^\s*[-*+]\s+(.*)$", line)
        m_ol = re.match(r"^\s*\d+[.)]\s+(.*)$", line)
        if m_h:
            flush_para()
            close_list()
            lvl = min(len(m_h.group(1)) + 1, 6)        # 邮件里 h1 过大，整体降一级
            out.append(f"<h{lvl}>{_inline(m_h.group(2))}</h{lvl}>")
        elif re.match(r"^\s{0,3}([-*_])(\s*\1){2,}\s*$", line):
            flush_para()
            close_list()
            out.append("<hr>")
        elif m_ul or m_ol:
            flush_para()
            tag = "ul" if m_ul else "ol"
            if list_tag != tag:
                close_list()
                out.append(f"<{tag}>")
                list_tag = tag
            out.append(f"<li>{_inline((m_ul or m_ol).group(1))}</li>")
        elif re.match(r"^\s{0,3}>", line):
            flush_para()
            close_list()
            out.append(f"<blockquote>{_inline(re.sub(r'^\s{0,3}>\s?', '', line))}</blockquote>")
        else:
            close_list()
            para.append(line.strip())
    flush_para()
    close_list()
    return "\n".join(out)
