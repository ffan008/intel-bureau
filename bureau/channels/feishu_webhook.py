"""飞书自定义群机器人（Webhook）。

按飞书开放平台文档《自定义机器人使用指南》（/client-docs/bot-v3/add-custom-bot，2026-10-28 读取）核实：
- 请求体不超过 20 KB；频率限制单机器人 100 次/分钟、5 次/秒（11232 为限流）。
- 签名：把 ``timestamp + "\\n" + 密钥`` 作为 HmacSHA256 的 key，对空字符串签名后 Base64；
  请求体带 ``timestamp``（秒，1 小时内有效）和 ``sign``。
- 交互卡片：``{"msg_type": "interactive", "card": {"schema": "2.0", "header": {...},
  "body": {"elements": [{"tag": "markdown", "content": "..."}]}}}``。
- 返回体：成功 ``code == 0``；19021 签名失败，19022 IP 不在白名单，19024 关键词校验失败，9499 请求体格式错误。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, http_status_error,
                                             post_json, report_markdown)

MAX_BODY_BYTES = 20 * 1024
CARD_MD_BYTES = 15000            # 单张卡片 markdown 的字节预算（JSON 转义后仍在 20 KB 内）
_ERRORS = {
    19021: ("签名校验失败：签名密钥不对，或本机时间偏差超过 1 小时", False),
    19022: ("IP 不在机器人的白名单里", False),
    19024: ("关键词校验失败：请在机器人安全设置里加入关键词「情报局」，或改用签名校验", False),
    9499: ("请求体格式错误", False),
    11232: ("发送过于频繁（飞书限流）", True),
}


def gen_sign(timestamp: int, secret: str) -> str:
    """飞书自定义机器人签名：key = f"{timestamp}\\n{secret}"，HMAC-SHA256(空消息) 再 Base64。"""
    key = f"{timestamp}\n{secret}".encode("utf-8")
    return base64.b64encode(hmac.new(key, b"", digestmod=hashlib.sha256).digest()).decode("ascii")


class FeishuWebhookChannel(Channel):
    kind = "feishu_webhook"
    label = "飞书群机器人（Webhook）"
    platform_label = "飞书"
    transport = None             # 测试时注入 httpx.MockTransport
    retry_base_delay = 1.0
    part_interval = 0.5

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="webhook_url", label="Webhook 地址", type="secret", required=True,
                        placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/…",
                        help="群设置 → 群机器人 → 添加机器人 → 自定义机器人，复制 Webhook 地址"),
            ConfigField(key="sign_secret", label="签名密钥", type="secret",
                        help="机器人安全设置里开启「签名校验」后显示的密钥；未开启可留空"),
            ConfigField(key="header_color", label="卡片标题颜色", type="select", default="blue",
                        options=[{"value": v, "label": l} for v, l in
                                 (("blue", "蓝"), ("wathet", "浅蓝"), ("turquoise", "青"), ("green", "绿"),
                                  ("orange", "橙"), ("red", "红"), ("purple", "紫"), ("grey", "灰"))]),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        url = str(self.ctx.secrets.get("webhook_url") or "").strip()
        if url and not url.startswith(("https://open.feishu.cn/", "https://open.larksuite.com/")):
            errors.append("Webhook 地址应以 https://open.feishu.cn/open-apis/bot/v2/hook/ 开头")
        return errors

    def _card(self, title: str, md: str) -> dict[str, Any]:
        return {"msg_type": "interactive", "card": {
            "schema": "2.0",
            "header": {"title": {"tag": "plain_text", "content": title[:100]},
                       "template": str(self.ctx.settings.get("header_color") or "blue")},
            "body": {"elements": [{"tag": "markdown", "content": md}]}}}

    def _payload(self, title: str, md: str) -> dict[str, Any]:
        body = self._card(title, md)
        secret = str(self.ctx.secrets.get("sign_secret") or "").strip()
        if secret:
            ts = int(time.time())
            body = {"timestamp": str(ts), "sign": gen_sign(ts, secret), **body}
        return body

    def _split(self, title: str, md: str) -> list[str]:
        budget = CARD_MD_BYTES
        while True:
            parts = split_text(md, budget, measure="bytes")
            sizes = [len(json.dumps(self._payload(title, p), ensure_ascii=False).encode("utf-8")) for p in parts]
            if max(sizes) <= MAX_BODY_BYTES - 200 or budget < 2000:
                return parts
            budget = int(budget * 0.8)


    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        url = str(self.ctx.secrets["webhook_url"]).strip()
        secret = str(self.ctx.secrets.get("sign_secret") or "").strip()
        md = report_markdown(report)
        parts = self._split(report.title, md)
        total = len(parts)

        async def send_one(i: int, text: str) -> PartOutcome:
            title = report.title if total == 1 else f"{report.title}（{i + 1}/{total}）"
            status, data = await post_json(url, self._payload(title, text), transport=self.transport,
                                           secrets=(url, secret), service="飞书")
            code = data.get("code") if isinstance(data, dict) else None
            if code is None and isinstance(data, dict):
                code = data.get("StatusCode")
            if status >= 400 and code is None:
                raise http_status_error(status, "飞书")
            if code == 0:
                return PartOutcome()
            msg, retry = _ERRORS.get(code, (None, False))
            raw = str((data or {}).get("msg") or "")[:120] if isinstance(data, dict) else ""
            raise SendError(f"飞书返回错误 {code}：{msg or raw or '未知原因'}", retryable=retry, code=code)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="张卡片", interval=self.part_interval),
                                   send_one)