"""Server酱（Turbo 与 Server酱³）。

按官方文档核实（2026-10-28）：
- Server酱³ API（https://doc.sc3.ft07.com/serverchan3/server/api）：``https://<uid>.push.ft07.com/send/<sendkey>.send``，
  uid 从 SendKey 中解析，正则 ``^sctp(\\d+)t``；参数 title（或 text）、desp（Markdown）、tags（竖线分隔）、short。
- Server酱 Turbo（https://sct.ftqq.com/docs/getting-started/sendkey/）：``https://sctapi.ftqq.com/<SendKey>.send``，
  参数 title、desp，可选 channel；官方 SDK（easychen/serverchan-sdk）按前缀 sctp 自动选择两种地址。
- 返回 JSON 的 ``code == 0`` 为成功；HTTP 429 表示该 IP 24 小时内调用超限。title 不能含换行。
- 额度（常见问题页）：Turbo 免费每天 5 条、会员每天 1000 条，每分钟最多 50 条；Server³ 正文换行需要两个换行。
未核实：title / desp 的长度上限（官方页面没有给出数字），这里保守地把标题截到 32 字、正文按 30000 字节分段。
"""

from __future__ import annotations

import re

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, http_status_error,
                                             post_json, report_markdown)

SC3_RE = re.compile(r"^sctp(\d+)t")
TITLE_MAX = 32
DESP_BYTES = 30000


def serverchan_url(sendkey: str) -> str:
    key = sendkey.strip()
    m = SC3_RE.match(key)
    if key.startswith("sctp"):
        if not m:
            raise ValueError("Server酱³ 的 SendKey 格式不对（应形如 sctp123tXXXX）")
        return f"https://{m.group(1)}.push.ft07.com/send/{key}.send"
    return f"https://sctapi.ftqq.com/{key}.send"


class ServerChanChannel(Channel):
    kind = "serverchan"
    label = "Server酱"
    platform_label = "微信"
    transport = None
    retry_base_delay = 2.0
    part_interval = 1.5

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="sendkey", label="SendKey", type="secret", required=True,
                        help="Turbo 版在 sct.ftqq.com 的 SendKey 页复制（SCT 开头）；Server酱³ 在 sc3.ft07.com 复制（sctp 开头）"),
            ConfigField(key="channel", label="消息通道（仅 Turbo）", placeholder="留空用默认通道，如 9|66",
                        help="多个通道用竖线分隔；Server酱³ 忽略此项"),
            ConfigField(key="tags", label="标签（仅 Server酱³）", default="情报局",
                        help="多个标签用竖线分隔"),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        key = str(self.ctx.secrets.get("sendkey") or "").strip()
        if key:
            try:
                serverchan_url(key)
            except ValueError as exc:
                errors.append(str(exc))
        return errors

    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        key = str(self.ctx.secrets["sendkey"]).strip()
        url = serverchan_url(key)
        sc3 = key.startswith("sctp")
        md = report_markdown(report)
        if sc3:
            md = re.sub(r"(?<!\n)\n(?!\n)", "\n\n", md)      # Server酱³ 需要两个换行才换行
        parts = split_text(md, DESP_BYTES, measure="bytes")
        total = len(parts)
        title = re.sub(r"\s+", " ", report.title).strip()

        async def send_one(i: int, text: str) -> PartOutcome:
            t = title if total == 1 else f"({i + 1}/{total}){title}"
            payload: dict[str, str] = {"title": t[:TITLE_MAX], "desp": text}
            if sc3 and self.ctx.settings.get("tags"):
                payload["tags"] = str(self.ctx.settings["tags"])
            if not sc3 and self.ctx.settings.get("channel"):
                payload["channel"] = str(self.ctx.settings["channel"])
            status, data = await post_json(url, payload, transport=self.transport, secrets=(key,), service="Server酱")
            if status == 429:
                raise SendError("Server酱返回 429：本机 IP 24 小时内调用次数超限，停止调用 24 小时后恢复", code=429)
            if not isinstance(data, dict):
                raise http_status_error(status, "Server酱") if status >= 400 else SendError("Server酱返回格式异常")
            if data.get("code") == 0:
                inner = data.get("data") if isinstance(data.get("data"), dict) else {}
                return PartOutcome(external_id=str(inner.get("pushid") or inner.get("pushId") or "") or None)
            msg = str(data.get("message") or data.get("info") or "")[:120]
            quota = "（Turbo 免费版每天只有 5 条额度）" if any(w in msg for w in ("额度", "次数", "超过", "limit")) else ""
            raise SendError(f"Server酱返回错误 {data.get('code')}：{msg or '未知原因'}{quota}",
                            retryable=status >= 500, code=data.get("code"))

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条", interval=self.part_interval), send_one)