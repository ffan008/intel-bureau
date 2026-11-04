"""PushPlus（推送加）。

按官方文档核实（2026-10-28）：
- 消息接口 https://www.pushplus.plus/doc/guide/api.html ：``POST /send``，JSON 参数 token、title、content、
  template（这里用 markdown）、topic（群组编码）、channel（wechat/webhook/cp/mail/app/extension/clawbot/qq…）、
  option（渠道配置编码）。返回 ``code == 200`` 只表示收到请求（异步发送），data 是消息流水号。
- 接口同时支持 http 和 https（常见问题「接口是否支持https请求」），这里用 https，避免 token 明文传输。
- 返回码（/doc/guide/code.html）：900 账号受限、903 token 无效、905 未实名、999 服务端验证错误、500 系统异常。
- 限制（/doc/help/limit.html）：实名用户标题 100 字、内容 2 万字；1 分钟 5 次；相同内容 1 小时 3 条；
  未实名用户无法调用发送接口。
"""

from __future__ import annotations

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, http_status_error,
                                             post_json, report_markdown)

API = "https://www.pushplus.plus/send"
TITLE_MAX = 100
CONTENT_MAX = 18000
_CODES = {
    900: ("账号已被限制推送（请求次数过多），今天别再重试", False),
    903: ("token 无效，请检查是否复制完整", False),
    905: ("账号未实名认证，PushPlus 要求实名后才能发送", False),
    999: ("服务端校验未通过", False),
    500: ("PushPlus 系统异常", True),
    600: ("数据异常", False),
}
CHANNEL_OPTIONS = [("wechat", "微信公众号（默认）"), ("webhook", "第三方 Webhook"), ("cp", "企业微信应用"),
                   ("mail", "邮箱"), ("app", "PushPlus App"), ("extension", "浏览器插件 / 桌面端"),
                   ("clawbot", "微信 ClawBot"), ("qq", "QQ 机器人")]


class PushPlusChannel(Channel):
    kind = "pushplus"
    label = "PushPlus（推送加）"
    platform_label = "微信"
    transport = None
    retry_base_delay = 2.0
    part_interval = 13.0          # 1 分钟 5 次：多段时间隔 13 秒

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="token", label="Token", type="secret", required=True,
                        help="pushplus.plus 微信扫码登录后，在「一对一推送」或个人中心复制用户 token（需实名认证）"),
            ConfigField(key="topic", label="群组编码", placeholder="留空只推给自己",
                        help="一对多推送时填写群组编码"),
            ConfigField(key="channel", label="发送渠道", type="select", default="wechat",
                        options=[{"value": v, "label": l} for v, l in CHANNEL_OPTIONS]),
            ConfigField(key="option", label="渠道配置编码", placeholder="webhook / 企业微信 / 邮箱等渠道需要",
                        help="在 PushPlus 个人中心 → 渠道配置里新增后得到的编码"),
        ]

    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        token = str(self.ctx.secrets["token"]).strip()
        parts = split_text(report_markdown(report), CONTENT_MAX)
        total = len(parts)
        s = self.ctx.settings

        async def send_one(i: int, text: str) -> PartOutcome:
            title = report.title if total == 1 else f"{report.title}（{i + 1}/{total}）"
            payload = {"token": token, "title": title[:TITLE_MAX], "content": text, "template": "markdown"}
            for k in ("topic", "channel", "option"):
                if str(s.get(k) or "").strip():
                    payload[k] = str(s[k]).strip()
            status, data = await post_json(API, payload, transport=self.transport, secrets=(token,), service="PushPlus")
            if not isinstance(data, dict):
                raise http_status_error(status, "PushPlus") if status >= 400 else SendError("PushPlus 返回格式异常")
            code = data.get("code")
            if code == 200:
                return PartOutcome(external_id=str(data.get("data") or "") or None,
                                   note="PushPlus 已受理（异步发送，可用流水号在官网查询结果）")
            msg, retry = _CODES.get(code, (None, False))
            raw = str(data.get("msg") or "")[:120]
            raise SendError(f"PushPlus 返回错误 {code}：{msg or raw or '未知原因'}", retryable=retry, code=code)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条", interval=self.part_interval), send_one)