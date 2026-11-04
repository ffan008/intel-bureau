"""QQ 推送：通过 NapCat（OneBot 11）用情报员小号发私聊或群消息。

- 私聊 ``send_private_msg``（user_id），群 ``send_group_msg``（group_id），消息用数组格式的 text 段，
  不会被当作 CQ 码解析。参数名按 NapCat 源码 OB11PostSendMsgSchema 核实。
- 内容用 ``summary_text``（纯文本）；每段不超过 1500 字，段间隔 1.5 秒，最多 6 段；
  超出时在最后一段末尾提示"完整内容请在工作台查看"。
"""

from __future__ import annotations

import httpx

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.onebot import DEFAULT_BASE_URL, OneBotClient, OneBotError
from bureau.integrations.push_common import DeliveryPlan, PartOutcome, SendError, deliver_parts, report_text

PART_CHARS = 1500
MAX_PARTS = 6
TAG_RESERVE = 8                  # "[6/6] " 的长度余量
MORE_NOTE = "……（完整内容请在工作台查看）"


def plan_qq_parts(text: str, dashboard_url: str | None = None) -> list[str]:
    """按 1500 字分段，最多 6 段；超出时截断并在最后一段提示去工作台查看。"""
    body = PART_CHARS - TAG_RESERVE
    parts = split_text(text, body)
    if len(parts) <= MAX_PARTS:
        return parts
    note = MORE_NOTE + (f"\n{dashboard_url}" if dashboard_url else "")
    parts = parts[:MAX_PARTS]
    last = parts[-1]
    if len(last) + len(note) + 1 > body:
        last = last[: body - len(note) - 1].rstrip()
    parts[-1] = f"{last}\n{note}"
    return parts


class QQOneBotChannel(Channel):
    kind = "qq_onebot"
    label = "QQ（NapCat OneBot）"
    platform_label = "QQ"
    transport: httpx.AsyncBaseTransport | None = None
    retry_base_delay = 1.0
    part_interval = 1.5

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="base_url", label="OneBot HTTP 地址", type="url", default=DEFAULT_BASE_URL,
                        help="与 QQ 采集器相同的 NapCat HTTP 服务端地址"),
            ConfigField(key="token", label="Token", type="secret", help="NapCat HTTP 服务端的 token"),
            ConfigField(key="target_type", label="发送到", type="select", default="private",
                        options=[{"value": "private", "label": "私聊（推荐：小号私聊主号）"},
                                 {"value": "group", "label": "群聊"}]),
            ConfigField(key="target_id", label="QQ 号 / 群号", required=True,
                        help="私聊填主号 QQ 号（需先和小号互为好友），群聊填群号"),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        tid = str(self.ctx.settings.get("target_id") or "").strip()
        if tid and not tid.isdigit():
            errors.append("QQ 号 / 群号只能是数字")
        return errors


    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        s = self.ctx.settings
        client = OneBotClient(str(s.get("base_url") or DEFAULT_BASE_URL),
                              str(self.ctx.secrets.get("token") or "") or None, transport=self.transport)
        target = str(s["target_id"]).strip()
        group = str(s.get("target_type") or "private") == "group"
        text = report_text(report)
        if report.title and not text.startswith(report.title):
            text = f"{report.title}\n\n{text}"
        parts = plan_qq_parts(text, report.dashboard_url)
        total = len(parts)

        async def send_one(i: int, body: str) -> PartOutcome:
            msg = body if total == 1 else f"[{i + 1}/{total}] {body}"
            try:
                data = await (client.send_group_msg(target, msg) if group else client.send_private_msg(target, msg))
            except OneBotError as exc:
                hint = exc.hint or ("确认小号和接收方互为好友" if not group else "确认小号在该群里且没有被禁言")
                raise SendError(f"{exc.message}（{hint}）", retryable=exc.retryable, code=exc.retcode) from None
            mid = (data or {}).get("message_id") if isinstance(data, dict) else None
            return PartOutcome(external_id=str(mid) if mid is not None else None)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条消息", interval=self.part_interval),
                                   send_one)