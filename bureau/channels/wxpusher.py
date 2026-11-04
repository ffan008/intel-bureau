"""WxPusher：标准推送（appToken + UID / Topic）或极简推送（SPT）。

按官方文档 https://wxpusher.zjiecode.com/docs/README.md （最后更新 2026-10-10）核实：
- 标准推送：``POST https://wxpusher.zjiecode.com/api/send/message``，JSON：appToken、content、summary（≤100）、
  contentType（1 文字、2 HTML、3 Markdown）、uids[]、topicIds[]、url（≤1000）。
- 极简推送：``POST https://wxpusher.zjiecode.com/api/send/message/simple-push``，JSON：content、summary、
  contentType、spt 或 sptList[]（≤10 个）、url。
- 返回 ``code == 1000`` 表示任务已受理；data 是每个目标的结果数组（各自 code、status、messageContentId）。
  1001 等其它码表示失败（如内容超长）。content 最多 40000 字符且 UTF-8 不超过 65535 字节（转换后的 HTML 也算）。
- 单条请求最多 uids 2000 个、topicIds 5 个。
"""

from __future__ import annotations

import re

from bureau.channels.base import Channel, split_text
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.integrations.push_common import (DeliveryPlan, PartOutcome, SendError, deliver_parts, http_status_error,
                                             post_json, report_markdown)

API_STANDARD = "https://wxpusher.zjiecode.com/api/send/message"
API_SPT = "https://wxpusher.zjiecode.com/api/send/message/simple-push"
CONTENT_BYTES = 30000             # Markdown 转 HTML 后会变长，留出一半余量
SUMMARY_MAX = 95


def _list(value: object) -> list[str]:
    return [x for x in re.split(r"[\s,，;；]+", str(value or "")) if x]


class WxPusherChannel(Channel):
    kind = "wxpusher"
    label = "WxPusher"
    platform_label = "微信"
    transport = None
    retry_base_delay = 2.0
    part_interval = 1.0

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="mode", label="推送方式", type="select", default="spt",
                        options=[{"value": "spt", "label": "极简推送（SPT，推给自己，最简单）"},
                                 {"value": "standard", "label": "标准推送（appToken + UID / Topic）"}]),
            ConfigField(key="spt", label="SPT", type="secret",
                        help="扫描 WxPusher 文档里的「获取 SPT」二维码得到；多个用逗号分隔（最多 10 个）"),
            ConfigField(key="app_token", label="appToken", type="secret",
                        help="标准推送：在 wxpusher.zjiecode.com/admin 创建应用后获得（AT_ 开头）"),
            ConfigField(key="uids", label="UID 列表", type="textarea", placeholder="UID_xxx，多个用逗号或换行分隔",
                        help="标准推送：接收人的 UID"),
            ConfigField(key="topic_ids", label="Topic ID 列表", placeholder="如 123,456",
                        help="标准推送：群发主题 ID（最多 5 个）"),
        ]

    def validate(self) -> list[str]:
        errors = super().validate()
        if str(self.ctx.settings.get("mode") or "spt") == "standard":
            if not str(self.ctx.secrets.get("app_token") or "").strip():
                errors.append("缺少必填项：appToken")
            if not _list(self.ctx.settings.get("uids")) and not _list(self.ctx.settings.get("topic_ids")):
                errors.append("标准推送需要至少一个 UID 或 Topic ID")
        else:
            spts = _list(self.ctx.secrets.get("spt"))
            if not spts:
                errors.append("缺少必填项：SPT")
            elif len(spts) > 10:
                errors.append("SPT 最多 10 个")
        return errors


    async def send(self, report: ReportPayload) -> DeliveryResult:
        errors = self.validate()
        if errors:
            return self.result(False, "；".join(errors))
        standard = str(self.ctx.settings.get("mode") or "spt") == "standard"
        token = str(self.ctx.secrets.get("app_token") or "").strip()
        spts = _list(self.ctx.secrets.get("spt"))
        md = report_markdown(report)
        if not md.lstrip().startswith("#"):
            md = f"# {report.title}\n\n{md}"
        parts = split_text(md, CONTENT_BYTES, measure="bytes")
        total = len(parts)

        async def send_one(i: int, text: str) -> PartOutcome:
            summary = report.title if total == 1 else f"{report.title}（{i + 1}/{total}）"
            payload: dict[str, object] = {"content": text, "summary": summary[:SUMMARY_MAX], "contentType": 3}
            if report.dashboard_url and len(report.dashboard_url) <= 1000:
                payload["url"] = report.dashboard_url
            if standard:
                payload["appToken"] = token
                if _list(self.ctx.settings.get("uids")):
                    payload["uids"] = _list(self.ctx.settings.get("uids"))
                topics = [int(x) for x in _list(self.ctx.settings.get("topic_ids")) if x.isdigit()][:5]
                if topics:
                    payload["topicIds"] = topics
                url = API_STANDARD
            else:
                payload.update({"spt": spts[0]} if len(spts) == 1 else {"sptList": spts})
                url = API_SPT
            status, data = await post_json(url, payload, transport=self.transport, secrets=(token, *spts),
                                           service="WxPusher")
            if not isinstance(data, dict):
                raise http_status_error(status, "WxPusher") if status >= 400 else SendError("WxPusher 返回格式异常")
            if data.get("code") != 1000:
                msg = str(data.get("msg") or "")[:120]
                raise SendError(f"WxPusher 返回错误 {data.get('code')}：{msg or '未知原因'}",
                                retryable=status >= 500, code=data.get("code"))
            items = [x for x in (data.get("data") or []) if isinstance(x, dict)]
            failed = [x for x in items if x.get("code") not in (1000, None)]
            if items and len(failed) == len(items):
                raise SendError(f"WxPusher 所有目标都失败：{str(failed[0].get('status') or '')[:80]}",
                                code=failed[0].get("code"))
            ext = next((str(x.get("messageContentId")) for x in items if x.get("messageContentId")), None)
            note = f"{len(failed)} 个目标未受理" if failed else None
            return PartOutcome(external_id=ext, note=note)

        return await deliver_parts(DeliveryPlan(self, report, parts, unit="条", interval=self.part_interval), send_one)