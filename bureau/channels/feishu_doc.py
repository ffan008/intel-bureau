"""飞书文档通道：用 lark-cli 把报告写进飞书。两种模式（设置项 ``mode``）：

- ``wiki``（v2 默认）：知识库树（docs/V2_KNOWLEDGE.md §3.4）::

      情报局知识库（空间；没有就自动创建，space_id 记在 data/cache/feishu_wiki.json）
      └─ 每日风向标（节点；没有就自动创建或复用同名节点）
         └─ 2026-10-30（今日风向标）   ← 总览：今日总览 + 专题直达 + 资源库 + 快讯
            ├─ 01-{专题标题}
            └─ …

  顺序：空间 → 「每日风向标」→ 当天总览页（先写不带链接的初稿）→ 各篇专题子文档（附图尽力插入）→
  用带专题链接的终稿覆盖总览页。以 report_id 为键记录每一步的结果：重试时跳过已完成的部分，
  结果不明（超时）的创建先按标题查找再决定是否补建，不会重复建文档。
- ``single``（v1）：整份报告写成一篇云文档，行为不变，另外返回 ``DeliveryResult.url``。
  旧配置里填了 parent_token / parent_position、又没有 mode 的，仍按 single 处理。

按 lark-cli 1.0.98 的 ``--help`` 与内置技能 lark-wiki、lark-doc 核实（2026-10-30）：
- ``wiki +space-list --as <id> --page-all`` → data.spaces[{space_id, name, …}]（权限 wiki:space:retrieve）。
- ``wiki +space-create --as user --name --description`` → data.{space_id, …}；只支持用户身份（wiki:space:write_only）。
- ``wiki +node-create --space-id <id> --title`` → data.{node_token, obj_token, obj_type, resolved_space_id}，不返回 url。
- ``wiki +node-list --space-id <id> [--parent-node-token <tok>] --page-all`` → data.nodes[{node_token, obj_token, title}]。
- ``wiki +node-get --node-token <node_token|obj_token|URL>`` → data.{space_id, node_token, obj_token, …}。
- ``docs +create --parent-token <wiki node_token> --doc-format markdown --content @f.md --title <标题>``
  → data.document.{document_id, url}；建在该节点下。
- ``docs +update --doc <document_id> --command overwrite|append --doc-format markdown --content @f.md``。
- Markdown 里本地图片写作 ``![说明](@./images/x.png)``（路径必须在 cwd 内）；``<`` 会被当作 XML 标签解析，
  字面的 ``<`` 要写成 ``\\<``（代码块和行内代码里不用）。``@file`` 只接受 cwd 下的相对路径。
- 创建类接口都不幂等；结构超限返回 131003，不能原样重试。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from bureau.channels.base import Channel
from bureau.contracts import ArticleBrief, ConfigField, DeliveryResult, ReportPayload, ResourceBrief
from bureau.core.platform_hints import LARK_CLI_INSTALL
from bureau.integrations.lark_cli import LarkCli, LarkCliError, sanitize_arg
from bureau.integrations.push_common import DeliveryPlan, PartOutcome, SendError, deliver_parts, with_dashboard_link

SPACE_NAME = "情报局知识库"
SPACE_DESC = "情报局工作台自动整理的每日风向标与专题知识文章"
ROOT_TITLE = "每日风向标"
STATE_FILE = "feishu_wiki.json"
KEEP_REPORTS = 60                 # 每个通道最多记住多少份报告的建档结果
MAX_IMAGES = 6                    # 每篇专题最多插入几张图
SECTION_MAX = 40000               # 总览页里单个板块的字数上限
ARTICLE_MAX = 60000               # 单篇专题的字数上限
WRITE_INTERVAL = 0.4              # 两次写操作之间的间隔（秒），避免触发飞书限流
_FATAL = {"auth", "scope", "not_found", "confirm", "unsafe_args"}
_IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
_TOKEN = re.compile(r"^[A-Za-z0-9]{8,64}$")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_STATE_LOCK = threading.Lock()


class _Stop(Exception):
    """wiki 流程中断。message 为中文；fatal 表示重试也没用（权限、认证等）。"""

    def __init__(self, message: str, *, retryable: bool = False, fatal: bool = False, unknown: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.fatal = fatal
        self.unknown = unknown          # 写操作结果不明（超时），可能已经生效


# ---------------------------------------------------------------- Markdown 小工具

def escape_lt(md: str) -> str:
    """飞书 Markdown 会把 ``<tag>`` 当作 XML 解析：代码块和行内代码以外的 ``<`` 一律转义成 ``\\<``。"""
    out: list[str] = []
    fence: str | None = None
    for line in (md or "").split("\n"):
        s = line.lstrip()
        if fence is None and re.match(r"^(```+|~~~+)", s):
            fence = re.match(r"^(```+|~~~+)", s).group(1)[:3]
            out.append(line)
            continue
        if fence is not None:
            if s.startswith(fence):
                fence = None
            out.append(line)
            continue
        parts = re.split(r"(`+[^`]*`+)", line)
        out.append("".join(p if p.startswith("`") else re.sub(r"(?<!\\)<", r"\\<", p) for p in parts))
    return "\n".join(out)


def demote_headings(md: str, by: int = 1) -> str:
    """把 Markdown 标题整体降级（代码块内不动），用于把板块内容嵌进总览页。"""
    out: list[str] = []
    in_code = False
    for line in (md or "").split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
        elif not in_code:
            m = re.match(r"^(#{1,6})(\s+.*)$", line)
            if m:
                line = "#" * min(len(m.group(1)) + by, 6) + m.group(2)
        out.append(line)
    return "\n".join(out)


def _plain(s: str) -> str:
    return re.sub(r"[^\w一-鿿]+", "", s or "")


def nest_section(md: str, title: str) -> str:
    """把板块 Markdown 嵌到总览页的二级标题下：去掉与板块名重复的开头标题，其余标题整体移到三级起。"""
    lines = (md or "").strip().split("\n")
    if lines and re.match(r"^#{1,6}\s", lines[0]) and _plain(lines[0].lstrip("#")) in (_plain(title), ""):
        lines = lines[1:]
    body = "\n".join(lines).strip()
    levels, in_code = [], False
    for line in body.split("\n"):
        if line.lstrip().startswith(("```", "~~~")):
            in_code = not in_code
        elif not in_code and (m := re.match(r"^(#{1,6})\s", line)):
            levels.append(len(m.group(1)))
    shift = max(0, 3 - min(levels)) if levels else 0
    return demote_headings(body, shift) if shift else body


def _clip(md: str, limit: int, dashboard_url: str | None) -> str:
    md = (md or "").strip()
    if len(md) <= limit:
        return md
    tail = f"[在工作台查看全文]({dashboard_url})" if dashboard_url else "在工作台查看全文"
    return md[:limit].rstrip() + f"\n\n（内容较长，这里只保留前 {limit} 字，{tail}）"


def _cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value if value is not None else "")).replace("|", "\\|").strip()


_KIND_TITLES = [("github", "🐙 GitHub 项目"), ("x", "🐦 X / 推特"), ("wechat_article", "📑 公众号文章"),
                ("netdisk", "💾 网盘资料"), ("video", "🎬 视频"), ("doc", "📄 在线文档"), ("web", "🔗 网页"),
                ("other", "📎 其它")]


def resources_markdown(resources: list[ResourceBrief]) -> str:
    """payload.sections 里没有 resources 时，按类别生成资源表（提取码、链接原样照录）。"""
    blocks: list[str] = []
    for kind, title in _KIND_TITLES:
        items = [r for r in resources if r.kind == kind]
        if not items:
            continue
        rows = ["| 资源 | 要点 | 提取码 | 分享人 | 来源 |", "| --- | --- | --- | --- | --- |"]
        for r in items:
            m = r.meta or {}
            if kind == "github":
                info = " · ".join(x for x in (f"⭐ {m['stars']}" if m.get("stars") is not None else "",
                                              str(m.get("language") or "")) if x)
            elif kind == "x":
                info = " · ".join(x for x in (f"❤ {m['likes']}" if m.get("likes") is not None else "",
                                              f"🔁 {m['retweets']}" if m.get("retweets") is not None else "") if x)
            elif kind == "wechat_article":
                info = f"{m['words']} 字" if m.get("words") else ""
            elif kind == "netdisk":
                info = str(m.get("provider") or "")
            else:
                info = str(m.get("provider") or "")
            info = " · ".join(x for x in (info, str(r.note or "")) if x)
            when = r.sent_at.strftime("%m-%d %H:%M") if r.sent_at else ""
            src = " · ".join(x for x in (r.group_name or "", when) if x)
            rows.append(f"| [{_cell(r.title) or '链接'}]({r.url}) | {_cell(info)} | {_cell(r.code)} | "
                        f"{_cell(r.shared_by)} | {_cell(src)} |")
        blocks.append(f"### {title}（{len(items)}）\n\n" + "\n".join(rows))
    return "\n\n".join(blocks)


def overview_markdown(report: ReportPayload, links: dict[int, str]) -> str:
    """当天总览页：今日总览 + 专题直达（目录）+ 资源库 + 快讯与其余。links 为 {序号: 专题文档链接}。"""
    sec = report.sections or {}
    parts: list[str] = []
    overview = (sec.get("overview") or "").strip()
    if not overview and not sec:
        overview = (report.full_md or report.summary_md or "").strip()     # 没有分板块时用整份报告
    if overview:
        parts.append("## 今日总览\n\n" + _clip(nest_section(overview, "今日总览"), SECTION_MAX, report.dashboard_url))
    if report.articles:
        lines = []
        for a in sorted(report.articles, key=lambda x: x.seq):
            name = f"{a.seq:02d}-{a.title}"
            item = f"[{name}]({links[a.seq]})" if links.get(a.seq) else f"{name}（文档生成中）"
            extra = f"：{a.hook}" if a.hook else ""
            flags = f"（⚠️ {'、'.join(a.risk_flags)}）" if a.risk_flags else ""
            lines.append(f"{a.seq}. {item}{extra}{flags}")
        parts.append(f"## 📌 今日 {len(report.articles)} 篇专题（目录）\n\n" + "\n".join(lines))
    resources = (sec.get("resources") or "").strip() or resources_markdown(report.resources)
    if resources:
        parts.append("## 🔥 资源库\n\n" + _clip(nest_section(resources, "资源库"), SECTION_MAX, report.dashboard_url))
    briefs = (sec.get("briefs") or "").strip()
    if briefs:
        parts.append("## 快讯与其余\n\n" + _clip(nest_section(briefs, "快讯与其余"), SECTION_MAX, report.dashboard_url))
    if report.dashboard_url:
        parts.append(f"---\n\n[在工作台查看完整报告（12 个板块）]({report.dashboard_url})")
    return "\n\n".join(p for p in parts if p.strip()) or "（今日没有内容）"


def article_markdown(article: ArticleBrief, dashboard_url: str | None) -> str:
    """专题正文：去掉与文档标题重复的首个一级标题。"""
    body = (article.body_md or "").strip()
    body = re.sub(r"^#\s+[^\n]*\n?", "", body, count=1).strip() if body.startswith("# ") else body
    return _clip(body or (article.hook or "（正文为空）"), ARTICLE_MAX, dashboard_url)


def _date_of(report: ReportPayload) -> str:
    m = _DATE.search(report.date_label or "") or _DATE.search(report.title or "")
    return m.group(0) if m else datetime.now().strftime("%Y-%m-%d")


def _find(data: Any, key: str) -> Any:
    """在 lark-cli 返回的 data 里找字段（顶层或下一层）。"""
    if not isinstance(data, dict):
        return None
    if data.get(key) not in (None, ""):
        return data[key]
    for v in data.values():
        if isinstance(v, dict) and v.get(key) not in (None, ""):
            return v[key]
    return None


def _wiki_token(value: str) -> str:
    v = (value or "").strip()
    m = re.search(r"/wiki/([A-Za-z0-9]+)", v)
    return m.group(1) if m else v


class FeishuDocChannel(Channel):
    kind = "feishu_doc"
    label = "飞书文档 / 知识库"
    platform_label = "飞书"
    cli: LarkCli | None = None
    retry_base_delay = 2.0
    write_interval = WRITE_INTERVAL

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="mode", label="写入方式", type="select", default="wiki",
                        options=[{"value": "wiki", "label": "知识库树（推荐：每天一页总览，每篇专题一篇子文档）"},
                                 {"value": "single", "label": "单篇文档（v1：整份报告写成一篇云文档）"}]),
            ConfigField(key="identity", label="创建身份", type="select", default="user",
                        options=[{"value": "user", "label": "用户身份（文档归你所有，推荐）"},
                                 {"value": "bot", "label": "机器人身份（文档归应用所有，会尝试给你授权）"}],
                        help="知识库模式下自动创建空间只支持用户身份；用机器人身份时请填写知识空间 ID"),
            ConfigField(key="space_id", label="知识空间 ID（知识库模式）", placeholder="留空自动查找或创建「情报局知识库」",
                        help="纯数字。可在空间设置页的地址里找到，或运行 `lark-cli wiki +space-list --as user`"),
            ConfigField(key="parent_node", label="「每日风向标」节点（知识库模式）",
                        placeholder="留空自动创建或复用同名节点",
                        help="想放到已有页面下时，填该页面的知识库链接或 node_token"),
            ConfigField(key="parent_token", label="父文件夹 / 知识库节点 token（单篇模式）",
                        help="留空则建在默认位置；填知识库节点 token 可直接写进知识库"),
            ConfigField(key="parent_position", label="父节点位置（单篇模式）", placeholder="如 my_library",
                        help="与上一项二选一"),
            ConfigField(key="base_url", label="飞书网页地址（可选）", placeholder="如 https://xxx.feishu.cn",
                        help="用于生成知识库页面链接；留空时从飞书返回的文档链接里自动识别"),
            ConfigField(key="cli_path", label="lark-cli 路径", placeholder="留空自动查找"),
        ]

    # ---------------------------------------------------------------- 配置
    @property
    def mode(self) -> str:
        s = self.ctx.settings
        mode = str(s.get("mode") or "").strip().lower()
        if mode in ("wiki", "single"):
            return mode
        return "single" if (s.get("parent_token") or s.get("parent_position")) else "wiki"

    @property
    def identity(self) -> str:
        return "bot" if self.ctx.settings.get("identity") == "bot" else "user"

    def validate(self) -> list[str]:
        errors = super().validate()
        s = self.ctx.settings
        if self.mode == "single":
            if s.get("parent_token") and s.get("parent_position"):
                errors.append("「父文件夹 token」和「父节点位置」只能填一个")
            return errors
        space = str(s.get("space_id") or "").strip()
        if space and not (space.isdigit() or space == "my_library"):
            errors.append("知识空间 ID 应为纯数字（或 my_library）")
        if space == "my_library" and self.identity == "bot":
            errors.append("机器人身份不能使用 my_library，请填写真实的知识空间 ID")
        node = _wiki_token(str(s.get("parent_node") or ""))
        if node and not _TOKEN.match(node):
            errors.append("「每日风向标」节点应为知识库链接或 node_token")
        base = str(s.get("base_url") or "").strip()
        if base and not re.match(r"^https://[A-Za-z0-9.-]+\.(?:feishu\.cn|larksuite\.com|larkoffice\.com|feishu\.net)/?$",
                                 base):
            errors.append("飞书网页地址应形如 https://xxx.feishu.cn")
        return errors

    def _cli(self) -> LarkCli:
        if self.cli is None:
            self.cli = LarkCli(cli_path=str(self.ctx.settings.get("cli_path") or "") or None, timeout=120.0)
        return self.cli

    # ---------------------------------------------------------------- 入口
    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        cli = self._cli()
        if not cli.available:
            return self.result(False, f"没有找到 lark-cli，请{LARK_CLI_INSTALL}")
        if self.mode == "single":
            res = await self._send_single(cli, report)
            if res.ok and res.external_id and res.external_id.startswith("https://"):
                res = res.model_copy(update={"url": res.external_id})
            return res
        try:
            return await self._send_wiki(cli, report)
        except Exception as exc:  # noqa: BLE001 — 通道约定不得抛异常
            self.ctx.logger.exception("[%s] 写入飞书知识库出现未预期的错误", self.ctx.channel_id)
            return self.result(False, f"写入飞书知识库出现未预期的错误（{type(exc).__name__}），详情见日志",
                               retryable=True)

    # ---------------------------------------------------------------- single（v1 行为）
    async def _send_single(self, cli: LarkCli, report: ReportPayload) -> DeliveryResult:
        identity = self.identity
        body = (report.full_md or "").strip() or (report.summary_md or "").strip()
        body = with_dashboard_link(body, report.dashboard_url)
        tmp_root = Path(self.ctx.data_dir) / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        async def send_one(_i: int, text: str) -> PartOutcome:
            work = Path(tempfile.mkdtemp(prefix="feishu-doc-", dir=tmp_root))
            try:
                (work / "report.md").write_text(text, encoding="utf-8")
                args = ["docs", "+create", "--as", identity, "--doc-format", "markdown",
                        "--content", "@report.md", "--title", sanitize_arg(report.title, max_len=120)]
                if self.ctx.settings.get("parent_token"):
                    args += ["--parent-token", str(self.ctx.settings["parent_token"]).strip()]
                elif self.ctx.settings.get("parent_position"):
                    args += ["--parent-position", str(self.ctx.settings["parent_position"]).strip()]
                try:
                    data = await cli.run(args, cwd=str(work), timeout=120.0, identity=identity)
                except LarkCliError as exc:
                    if exc.kind == "timeout":
                        raise SendError("创建文档超时，文档可能已经建好，请先到飞书云文档里确认，避免重复创建") from None
                    raise SendError(exc.message + (f"（{exc.hint}）" if exc.hint else ""),
                                    retryable=exc.kind == "rate_limit", code=exc.code) from None
            finally:
                shutil.rmtree(work, ignore_errors=True)
            doc = (data or {}).get("document") or {}
            url = str(doc.get("url") or "").strip()
            if not url:
                raise SendError("lark-cli 没有返回文档链接，请在飞书云文档里确认是否已创建")
            note = f"文档链接：{url}"
            grant = (data or {}).get("permission_grant") or {}
            if identity == "bot" and grant.get("status") in ("failed", "skipped"):
                note += "（文档归机器人所有，给你授权未成功，可能打不开）"
            if (data or {}).get("warnings"):
                note += f"（飞书提示 {len((data or {}).get('warnings'))} 条警告）"
            return PartOutcome(external_id=url, note=note)

        return await deliver_parts(DeliveryPlan(self, report, [body], unit="篇文档"), send_one)

    # ---------------------------------------------------------------- 状态（data/cache/feishu_wiki.json）
    def _state_path(self) -> Path:
        return Path(self.ctx.data_dir) / "cache" / STATE_FILE

    def _load_state(self) -> dict[str, Any]:
        with _STATE_LOCK:
            try:
                doc = json.loads(self._state_path().read_text("utf-8"))
            except (OSError, ValueError):
                doc = {}
        st = doc.get(self.ctx.channel_id) if isinstance(doc, dict) else None
        st = st if isinstance(st, dict) else {}
        if not isinstance(st.get("reports"), dict):
            st["reports"] = {}
        return st

    def _save_state(self, st: dict[str, Any]) -> None:
        reports = st.get("reports") or {}
        if len(reports) > KEEP_REPORTS:
            for key in sorted(reports, key=lambda k: reports[k].get("ts", 0))[: len(reports) - KEEP_REPORTS]:
                reports.pop(key, None)
        path = self._state_path()
        with _STATE_LOCK:
            try:
                doc = json.loads(path.read_text("utf-8"))
                doc = doc if isinstance(doc, dict) else {}
            except (OSError, ValueError):
                doc = {}
            doc[self.ctx.channel_id] = st
            tmp = None
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".feishu-wiki-", suffix=".tmp")
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    json.dump(doc, fh, ensure_ascii=False, indent=1)
                os.replace(tmp, path)
            except OSError as exc:
                if tmp:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
                self.ctx.logger.warning("[%s] 写入知识库建档记录失败：%s", self.ctx.channel_id, type(exc).__name__)

    # ---------------------------------------------------------------- lark-cli
    async def _run(self, args: list[str], *, cwd: Path | None = None, write: bool, idempotent: bool,
                   what: str) -> Any:
        """执行 lark-cli。限流时退避重试；只读或幂等的命令遇到网络错误也重试；创建类遇到超时不重试。"""
        cli = self._cli()
        for attempt in range(3):
            if write and self.write_interval > 0:
                await asyncio.sleep(self.write_interval)
            try:
                return await cli.run(args, cwd=str(cwd) if cwd else None, timeout=120.0, identity=self.identity)
            except LarkCliError as exc:
                transient = exc.kind in ("timeout", "network") or (exc.retryable and exc.kind != "rate_limit")
                if (exc.kind == "rate_limit" or (idempotent and transient)) and attempt < 2:
                    delay = self.retry_base_delay * (2 ** attempt)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
                if transient and not idempotent:
                    raise _Stop(f"{what}超时或网络中断，结果不明；再次投递时会先按标题查找，不会重复创建",
                                retryable=True, unknown=True) from None
                hint = f"（{exc.hint}）" if exc.hint else ""
                raise _Stop(f"{what}失败：{exc.message}{hint}", retryable=exc.retryable or transient,
                            fatal=exc.kind in _FATAL) from None
        raise _Stop(f"{what}失败：多次重试仍被限流", retryable=True)

    def _wiki_url(self, st: dict[str, Any], node_token: str) -> str | None:
        base = str(self.ctx.settings.get("base_url") or "").strip().rstrip("/") or str(st.get("domain") or "")
        return f"{base}/wiki/{node_token}" if base and node_token else None

    @staticmethod
    def _learn_domain(st: dict[str, Any], url: str) -> None:
        m = re.match(r"^(https://[A-Za-z0-9.-]+\.(?:feishu\.cn|larksuite\.com|larkoffice\.com|feishu\.net))/", url or "")
        if m:
            st["domain"] = m.group(1)

    @staticmethod
    def _doc_of(data: Any) -> tuple[str, str]:
        doc = _find(data, "document")
        doc = doc if isinstance(doc, dict) else {}
        return (str(doc.get("document_id") or _find(data, "document_id") or ""),
                str(doc.get("url") or _find(data, "url") or ""))

    async def _children(self, space_id: str, parent: str | None) -> list[dict[str, Any]]:
        args = ["wiki", "+node-list", "--as", self.identity, "--space-id", space_id, "--page-all"]
        if parent:
            args += ["--parent-node-token", parent]
        data = await self._run(args, write=False, idempotent=True, what="查询知识库节点")
        nodes = data.get("nodes") if isinstance(data, dict) else None
        return [n for n in nodes or [] if isinstance(n, dict) and n.get("node_token")]

    async def _find_child(self, space_id: str, parent: str | None, title: str) -> dict[str, Any] | None:
        return next((n for n in await self._children(space_id, parent)
                     if str(n.get("title") or "").strip() == title), None)

    # ---------------------------------------------------------------- wiki：空间与「每日风向标」
    async def _parent_node(self, st: dict[str, Any]) -> tuple[str, str] | None:
        """设置了 parent_node 时，返回 (space_id, node_token)（查询结果缓存）。"""
        node = _wiki_token(str(self.ctx.settings.get("parent_node") or ""))
        if not node:
            return None
        look = st.get("parent_lookup") or {}
        if look.get("node") == node and look.get("space_id") and look.get("node_token"):
            return str(look["space_id"]), str(look["node_token"])
        data = await self._run(["wiki", "+node-get", "--as", self.identity, "--node-token", node],
                               write=False, idempotent=True, what="查询「每日风向标」节点")
        sid, tok = str(_find(data, "space_id") or ""), str(_find(data, "node_token") or node)
        if not sid:
            raise _Stop("查不到设置里的「每日风向标」节点，请检查链接和访问权限", fatal=True)
        st["parent_lookup"] = {"node": node, "space_id": sid, "node_token": tok}
        self._save_state(st)
        return sid, tok

    async def _ensure_space(self, st: dict[str, Any]) -> str:
        explicit = str(self.ctx.settings.get("space_id") or "").strip()
        if explicit:
            return explicit
        parent = await self._parent_node(st)
        if parent:
            return parent[0]
        if st.get("space_id"):
            return str(st["space_id"])
        data = await self._run(["wiki", "+space-list", "--as", self.identity, "--page-all"],
                               write=False, idempotent=True, what="查询知识空间列表")
        for sp in (data.get("spaces") if isinstance(data, dict) else None) or []:
            if isinstance(sp, dict) and str(sp.get("name") or "").strip() == SPACE_NAME and sp.get("space_id"):
                st["space_id"], st["space_source"] = str(sp["space_id"]), "found"
                self._save_state(st)
                return st["space_id"]
        if self.identity == "bot":
            raise _Stop(f"没有找到名为「{SPACE_NAME}」的知识空间，机器人身份不能自动创建；请改用用户身份，"
                        "或在设置里填写知识空间 ID（并把应用加为该空间的成员）", fatal=True)
        data = await self._run(["wiki", "+space-create", "--as", "user", "--name", SPACE_NAME,
                                "--description", SPACE_DESC], write=True, idempotent=False, what="创建知识空间")
        sid = str(_find(data, "space_id") or "")
        if not sid:
            raise _Stop("创建知识空间后没有拿到 space_id，请到飞书知识库里确认", fatal=True)
        st["space_id"], st["space_source"] = sid, "created"
        self._save_state(st)
        self.ctx.logger.info("[%s] 已创建飞书知识空间「%s」", self.ctx.channel_id, SPACE_NAME)
        return sid

    async def _ensure_root(self, st: dict[str, Any], space_id: str) -> str:
        parent = await self._parent_node(st)
        if parent:
            return parent[1]
        root = st.get("root") or {}
        if root.get("space_id") == space_id and root.get("node_token"):
            return str(root["node_token"])
        found = await self._find_child(space_id, None, ROOT_TITLE)
        if found:
            token = str(found["node_token"])
        else:
            data = await self._run(["wiki", "+node-create", "--as", self.identity, "--space-id", space_id,
                                    "--title", ROOT_TITLE], write=True, idempotent=False, what="创建「每日风向标」节点")
            token = str(_find(data, "node_token") or "")
            if not token:
                raise _Stop("创建「每日风向标」节点后没有拿到 node_token，请到飞书知识库里确认")
        st["root"] = {"space_id": space_id, "node_token": token}
        self._save_state(st)
        return token

    # ---------------------------------------------------------------- wiki：当天总览页
    async def _ensure_day(self, st: dict[str, Any], rec: dict[str, Any], report: ReportPayload, space_id: str,
                          root: str, work: Path) -> dict[str, Any]:
        day = rec.setdefault("day", {})
        if day.get("status") == "done" and day.get("node_token") and day.get("document_id"):
            return day
        if day.get("status") == "doc_created" and day.get("document_id"):
            return await self._finish_day(st, day, space_id, root)
        title = day.get("title") or sanitize_arg(
            f"{_date_of(report)}（今日风向标）" if not report.is_test
            else f"通道测试 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", max_len=100)
        children = await self._children(space_id, root)
        same = [n for n in children if str(n.get("title") or "").strip() == title]
        if same and day.get("status") == "pending":           # 上次创建结果不明，其实已经建好了
            n = same[0]
            day.update(status="done", title=title, node_token=str(n["node_token"]),
                       document_id=str(n.get("obj_token") or ""), url=self._wiki_url(st, str(n["node_token"])))
            self._save_state(st)
            return day
        if same and not day.get("title"):                    # 同一天的另一份报告已经占用了这个标题
            names = {str(n.get("title") or "").strip() for n in children}
            v = 2
            while f"{title}（第 {v} 版）" in names:
                v += 1
            title = f"{title}（第 {v} 版）"
        day.update(status="pending", title=title)
        self._save_state(st)
        (work / "day.md").write_text(escape_lt(overview_markdown(report, {})), encoding="utf-8")
        data = await self._run(["docs", "+create", "--as", self.identity, "--parent-token", root,
                                "--doc-format", "markdown", "--content", "@day.md", "--title", title],
                               cwd=work, write=True, idempotent=False, what="创建当天总览页")
        doc_id, url = self._doc_of(data)
        if not doc_id:
            raise _Stop("创建当天总览页后没有拿到文档 ID，请到飞书知识库里确认", retryable=True, unknown=True)
        self._learn_domain(st, url)
        day.update(status="doc_created", document_id=doc_id, doc_url=url,
                   fp=hashlib.sha256(overview_markdown(report, {}).encode("utf-8")).hexdigest()[:16])
        self._save_state(st)
        return await self._finish_day(st, day, space_id, root)

    async def _finish_day(self, st: dict[str, Any], day: dict[str, Any], space_id: str, root: str) -> dict[str, Any]:
        """总览页文档已建好：查出它在知识库里的 node_token（专题子文档要建在它下面）。"""
        data = await self._run(["wiki", "+node-get", "--as", self.identity, "--node-token", str(day["document_id"])],
                               write=False, idempotent=True, what="查询当天总览页节点")
        token = str(_find(data, "node_token") or "")
        if not token:
            found = await self._find_child(space_id, root, str(day.get("title") or ""))
            token = str((found or {}).get("node_token") or "")
        if not token:
            raise _Stop("总览页已建好，但查不到它的知识库节点，稍后重试", retryable=True)
        day.update(status="done", node_token=token,
                   url=self._wiki_url(st, token) or day.get("doc_url") or None)
        self._save_state(st)
        return day

    # ---------------------------------------------------------------- wiki：专题子文档
    async def _ensure_article(self, st: dict[str, Any], rec: dict[str, Any], report: ReportPayload, a: ArticleBrief,
                              space_id: str, day: dict[str, Any], work: Path) -> tuple[str | None, int]:
        title = sanitize_arg(f"{a.seq:02d}-{a.title}", max_len=100)
        arts = rec.setdefault("articles", {})
        key = f"{a.seq:02d}:{a.id}"
        art = arts.setdefault(key, {"seq": a.seq, "title": title})
        if art.get("status") == "pending":
            found = await self._find_child(space_id, str(day["node_token"]), str(art.get("title") or title))
            if found:
                art.update(status="done", node_token=str(found["node_token"]),
                           document_id=str(found.get("obj_token") or ""),
                           url=art.get("url") or self._wiki_url(st, str(found["node_token"])))
                self._save_state(st)
        if art.get("status") != "done":
            art.update(status="pending", title=title)
            self._save_state(st)
            (work / f"a{a.seq:02d}.md").write_text(escape_lt(article_markdown(a, report.dashboard_url)), encoding="utf-8")
            data = await self._run(["docs", "+create", "--as", self.identity, "--parent-token", str(day["node_token"]),
                                    "--doc-format", "markdown", "--content", f"@a{a.seq:02d}.md", "--title", title],
                                   cwd=work, write=True, idempotent=False, what=f"创建专题 {a.seq:02d}")
            doc_id, url = self._doc_of(data)
            self._learn_domain(st, url)
            if not doc_id:
                raise _Stop(f"创建专题 {a.seq:02d} 后没有拿到文档 ID", retryable=True, unknown=True)
            art.update(status="done", document_id=doc_id, url=url or None, ts=time.time())
            self._save_state(st)
        await self._ensure_images(st, art, report, a, work)
        return art.get("url"), int(art.get("images") or 0)

    def _image_files(self, report: ReportPayload, a: ArticleBrief) -> list[Path]:
        if not report.assets_dir or not a.image_paths:
            return []
        base = Path(report.assets_dir).resolve()
        out = []
        for rel in a.image_paths:
            p = Path(rel)
            p = (p if p.is_absolute() else base / p).resolve()
            if (base in p.parents) and p.suffix.lower() in _IMG_EXT and p.is_file():
                out.append(p)
        return out

    async def _ensure_images(self, st: dict[str, Any], art: dict[str, Any], report: ReportPayload,
                             a: ArticleBrief, work: Path) -> None:
        """图片尽力插入专题文末；失败就写一行「图片见工作台」。追加类操作不幂等，结果不明时不再重试。"""
        if art.get("img") in ("done", "noted", "none", "pending") or not a.image_paths:
            if not a.image_paths:
                art.setdefault("img", "none")
            return
        doc = str(art.get("document_id") or "")
        if not doc:
            return
        files = self._image_files(report, a)[:MAX_IMAGES]
        art["img"] = "pending"
        self._save_state(st)
        lines: list[str] = []
        if files:
            img_dir = work / f"img{a.seq:02d}"
            img_dir.mkdir(exist_ok=True)
            for i, p in enumerate(files, 1):
                name = f"{i:02d}{p.suffix.lower()}"
                shutil.copyfile(p, img_dir / name)
                lines.append(f"![图 {i}](@./{img_dir.name}/{name})")
            more = len(a.image_paths) - len(files)
            tail = f"\n\n另有 {more} 张图片见工作台。" if more > 0 else ""
            (work / f"img{a.seq:02d}.md").write_text("## 图片\n\n" + "\n\n".join(lines) + tail, encoding="utf-8")
            try:
                await self._run(["docs", "+update", "--as", self.identity, "--doc", doc, "--command", "append",
                                 "--doc-format", "markdown", "--content", f"@img{a.seq:02d}.md"],
                                cwd=work, write=True, idempotent=False, what=f"插入专题 {a.seq:02d} 的图片")
                art.update(img="done", images=len(files))
                self._save_state(st)
                return
            except _Stop as exc:
                if exc.unknown:
                    return                     # 可能已经插入，宁可少图也不重复追加
                self.ctx.logger.info("[%s] 专题 %02d 图片插入失败：%s", self.ctx.channel_id, a.seq, exc.message)
        link = f"（[在工作台查看]({report.dashboard_url})）" if report.dashboard_url else ""
        (work / f"note{a.seq:02d}.md").write_text(f"## 图片\n\n图片见工作台{link}。", encoding="utf-8")
        try:
            await self._run(["docs", "+update", "--as", self.identity, "--doc", doc, "--command", "append",
                             "--doc-format", "markdown", "--content", f"@note{a.seq:02d}.md"],
                            cwd=work, write=True, idempotent=False, what=f"补充专题 {a.seq:02d} 的图片说明")
            art["img"] = "noted"
        except _Stop as exc:
            self.ctx.logger.info("[%s] 专题 %02d 图片说明写入失败：%s", self.ctx.channel_id, a.seq, exc.message)
        self._save_state(st)

    # ---------------------------------------------------------------- wiki：总览终稿
    async def _write_overview(self, st: dict[str, Any], day: dict[str, Any], report: ReportPayload,
                              links: dict[int, str], work: Path) -> None:
        md = overview_markdown(report, links)
        fp = hashlib.sha256(md.encode("utf-8")).hexdigest()[:16]
        if day.get("fp") == fp:
            return
        title = str(day.get("title") or "")
        safe_title = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        (work / "overview.md").write_text(f"<title>{safe_title}</title>\n\n" + escape_lt(md), encoding="utf-8")
        await self._run(["docs", "+update", "--as", self.identity, "--doc", str(day["document_id"]),
                         "--command", "overwrite", "--doc-format", "markdown", "--content", "@overview.md"],
                        cwd=work, write=True, idempotent=True, what="更新当天总览页")
        day["fp"] = fp
        self._save_state(st)

    # ---------------------------------------------------------------- wiki：主流程
    async def _send_wiki(self, cli: LarkCli, report: ReportPayload) -> DeliveryResult:
        st = self._load_state()
        key = report.report_id if not report.is_test else f"test-{time.time_ns()}"
        rec = st["reports"].setdefault(key, {})
        rec["ts"] = time.time()
        tmp_root = Path(self.ctx.data_dir) / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="feishu-wiki-", dir=tmp_root))
        links: dict[int, str] = {}
        failed: list[str] = []
        try:
            try:
                space_id = await self._ensure_space(st)
                root = await self._ensure_root(st, space_id)
                day = await self._ensure_day(st, rec, report, space_id, root, work)
            except _Stop as exc:
                self.ctx.logger.warning("[%s] %s", self.ctx.channel_id, exc.message)
                return self.result(False, exc.message, retryable=exc.retryable and not exc.fatal, parts=0)
            for a in sorted(report.articles, key=lambda x: x.seq):
                try:
                    url, _n = await self._ensure_article(st, rec, report, a, space_id, day, work)
                    if url:
                        links[a.seq] = url
                except _Stop as exc:
                    failed.append(f"专题 {a.seq:02d}（{exc.message}）")
                    if exc.fatal:
                        break
            try:
                await self._write_overview(st, day, report, links, work)
            except _Stop as exc:
                detail = f"总览页已建好但更新失败：{exc.message}"
                return self.result(False, detail, retryable=not exc.fatal, url=day.get("url"),
                                   external_id=day.get("url"), parts=1 + len(links))
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self._save_state(st)
        url = day.get("url")
        images = sum(int(x.get("images") or 0) for x in (rec.get("articles") or {}).values())
        done = len(links)
        total = len(report.articles)
        if failed:
            more = f"等 {len(failed)} 篇" if len(failed) > 3 else ""
            detail = (f"今日风向标已写入知识库，专题完成 {done}/{total} 篇；未完成：{'；'.join(failed[:3])}{more}。"
                      "再次投递时只补建未完成的部分")
            return self.result(False, detail, retryable=True, url=url, external_id=url, parts=1 + done)
        detail = f"今日风向标已写入飞书知识库：总览 1 页 + 专题 {done} 篇" + (f"，插入图片 {images} 张" if images else "")
        if url:
            detail += f"；链接：{url}"
        return self.result(True, detail, url=url, external_id=url, parts=1 + done)
