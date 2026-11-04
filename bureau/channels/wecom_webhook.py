"""企业微信群机器人（消息推送 Webhook）。

按企业微信开发者文档 https://developer.work.weixin.qq.com/document/path/91770 （2026-10-28 读取）核实：
- ``POST https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=KEY``，JSON。
- ``{"msgtype": "markdown", "markdown": {"content": "..."}}`` 或 ``markdown_v2``（支持表格、列表、
  标准链接；不支持字体颜色和 <@userid>）；content 最长 4096 字节，UTF-8。
- 每个机器人每分钟最多 20 条。返回 ``errcode == 0`` 为成功。
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, http_status_error,
                                             post_json, report_markdown)

API = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send"
MAX_BYTES = 4096
PREFIX_RESERVE = 24              # "（12/12）\n" 的字节数余量


class WecomWebhookChannel(Channel):
    kind = "wecom_webhook"
    label = "企业微信群机器人"
    platform_label = "微信"
    transport = None
    retry_base_delay = 1.0
    part_interval = 1.0

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="webhook", label="Webhook 地址或 key", type="secret", required=True,
                        placeholder="https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=…",
                        help="企业微信群 → 群设置 → 消息推送（群机器人）→ 添加，复制 Webhook 地址"),
            ConfigField(key="msgtype", label="消息格式", type="select", default="markdown_v2",
                        options=[{"value": "markdown_v2", "label": "markdown_v2（推荐，支持列表和链接）"},
                                 {"value": "markdown", "label": "markdown（旧版，兼容性更好）"}]),
        ]

    def _url(self) -> str | None:
        raw = str(self.ctx.secrets.get("webhook") or "").strip()
        if not raw:
            return None
        if raw.startswith("https://"):
            parts = urlsplit(raw)
            if parts.hostname != "qyapi.weixin.qq.com" or not parse_qs(parts.query).get("key"):
                return None
            return raw
        return f"{API}?key={raw}" if all(c.isalnum() or c == "-" for c in raw) else None

    def validate(self) -> list[str]:
        errors = super().validate()
        if self.ctx.secrets.get("webhook") and not self._url():
            errors.append("Webhook 地址应为 https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=… 或单独的 key")
        return errors


    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        url = self._url() or ""
        key = parse_qs(urlsplit(url).query).get("key", [""])[0]
        msgtype = "markdown" if self.ctx.settings.get("msgtype") == "markdown" else "markdown_v2"
        md = report_markdown(report)
        if not md.lstrip().startswith("#"):
            md = f"# {report.title}\n\n{md}"
        parts = split_text(md, MAX_BYTES, measure="bytes")
        if len(parts) > 1:
            parts = split_text(md, MAX_BYTES - PREFIX_RESERVE, measure="bytes")
        total = len(parts)

        async def send_one(i: int, text: str) -> PartOutcome:
            content = text if total == 1 else f"（{i + 1}/{total}）\n{text}"
            status, data = await post_json(url, {"msgtype": msgtype, msgtype: {"content": content}},
                                           transport=self.transport, secrets=(url, key), service="企业微信")
            if not isinstance(data, dict):
                raise http_status_error(status, "企业微信") if status >= 400 else SendError("企业微信返回格式异常")
            code = data.get("errcode")
            if code == 0:
                return PartOutcome()
            msg = str(data.get("errmsg") or "")[:120]
            if code == 45009 or "freq" in msg.lower():
                raise SendError("发送过于频繁（企业微信机器人每分钟最多 20 条）", retryable=True, code=code)
            if code in (93000, 40008) or "invalid webhook" in msg.lower():
                raise SendError(f"Webhook 地址无效或机器人已被移除（errcode {code}）", code=code)
            raise SendError(f"企业微信返回错误 {code}：{msg or '未知原因'}", code=code)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条消息", interval=self.part_interval),
                                   send_one)