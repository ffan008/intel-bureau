"""QQ 采集器：NapCatQQ 的 OneBot 11 HTTP 服务（默认 http://127.0.0.1:3010）。

- health：``get_login_info``（返回 user_id、nickname）。
- 列群：``get_group_list``（group_id、group_name、member_count、max_member_count、group_remark）。
- 拉消息：``get_group_msg_history``。不带 message_seq 时取最新 count 条；之后把本页最早一条的
  message_id 作为 message_seq 继续向前翻（NapCat 返回的结果包含这条锚点，需去重），直到早于 since。
- 实时：NapCat 的 HTTP 客户端上报到 ``POST /api/ingest/onebot``（由 A 实现路由，调用
  ``bureau.integrations.onebot.verify_onebot_request`` / ``parse_onebot_event``）。
- v2：图片 / 视频 / 文件附件的 ``extra.fetch``（``{"type": "onebot", "action": "get_image"|"get_file",
  "file", "file_id", "group_id", "url"?, "local_hint"?}``）由 ``onebot.message_to_raw`` 写入，
  历史拉取和实时上报共用，本采集器不需要再处理。
"""

from __future__ import annotations

from datetime import datetime

import httpx

from bureau.collectors.base import Collector, CollectorContext
from bureau.contracts import ConfigField, FetchResult, GroupInfo, Health, HealthStatus, Platform, RawMessage
from bureau.integrations.common import as_str
from bureau.integrations.onebot import DEFAULT_BASE_URL, OneBotClient, OneBotError, message_to_raw

PAGE_SIZE = 50
MAX_PAGES = 400
SETUP_HINT = "启动 NapCat 并用小号登录，在 WebUI（http://127.0.0.1:6099）里新建 HTTP 服务端，端口 3010"


def _ts(value: object) -> float:
    try:
        t = float(str(value))
    except (TypeError, ValueError):
        return 0.0
    return t / 1000.0 if t > 1e12 else t


class OneBotCollector(Collector):
    key = "qq.onebot"
    label = "NapCatQQ（OneBot 11）"
    platforms = (Platform.QQ,)
    supports_realtime = True

    def __init__(self, ctx: CollectorContext, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(ctx)
        s = ctx.settings or {}
        self.base_url = (as_str(s.get("base_url")) or DEFAULT_BASE_URL).rstrip("/")
        try:
            self.page_size = max(10, min(int(s.get("page_size") or PAGE_SIZE), 200))
        except (TypeError, ValueError):
            self.page_size = PAGE_SIZE
        self.client = OneBotClient(self.base_url, as_str((ctx.secrets or {}).get("token")) or None,
                                   transport=transport)

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="base_url", label="OneBot HTTP 地址", type="url", default=DEFAULT_BASE_URL,
                        help="NapCat WebUI →「网络配置」→ HTTP 服务端的地址，本项目约定端口 3010"),
            ConfigField(key="token", label="Token", type="secret",
                        help="与 NapCat HTTP 服务端（以及 HTTP 客户端上报）里填写的 token 相同；强烈建议设置"),
            ConfigField(key="report_secret", label="上报签名密钥", type="secret",
                        help="留空时使用上面的 Token 校验 X-Signature；只有上报用了不同密钥时才需要填写"),
            ConfigField(key="page_size", label="每页条数", type="number", default=PAGE_SIZE,
                        help="回溯历史消息时每次请求的条数（10~200）"),
        ]


    async def health(self) -> HealthStatus:
        data = {"base_url": self.base_url}
        try:
            info = await self.client.get_login_info()
        except OneBotError as exc:
            state = Health.DOWN if exc.http_status is None or exc.retryable else Health.DEGRADED
            return HealthStatus(ok=False, state=state, detail=exc.message, hint=exc.hint or SETUP_HINT, data=data)
        uid = as_str((info or {}).get("user_id"))
        nick = as_str((info or {}).get("nickname"))
        if not uid or uid == "0":
            return HealthStatus(ok=False, state=Health.DEGRADED, detail="NapCat 已运行，但 QQ 尚未登录",
                                hint="在 NapCat WebUI 里扫码登录情报员小号", data=data)
        data.update({"self_id": uid, "nickname": nick})
        return HealthStatus(ok=True, state=Health.OK, detail=f"已连接 NapCat，登录账号 {nick or uid}（{uid}）",
                            hint="建议使用情报员小号，主号不要登录 NapCat", data=data)

    async def list_groups(self) -> list[GroupInfo]:
        try:
            groups = await self.client.get_group_list()
        except OneBotError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None
        out = []
        for g in groups:
            gid = as_str(g.get("group_id"))
            if not gid:
                continue
            count = g.get("member_count")
            out.append(GroupInfo(platform=Platform.QQ, native_id=gid, name=as_str(g.get("group_name")) or gid,
                                 member_count=int(count) if isinstance(count, (int, float)) else None,
                                 avatar_url=f"https://p.qlogo.cn/gh/{gid}/{gid}/100",
                                 extra={k: g[k] for k in ("group_remark", "max_member_count") if g.get(k)}))
        return out

    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        try:
            return await self._fetch(group, since, until, limit)
        except OneBotError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None


    async def _fetch(self, group: GroupInfo, since: datetime, until: datetime, limit: int) -> FetchResult:
        lo, hi = since.timestamp(), until.timestamp()
        found: dict[str, RawMessage] = {}
        texts: dict[str, str] = {}
        seen: set[str] = set()
        warnings: list[str] = []
        anchor: str | None = None
        oldest: float | None = None
        complete = True
        for _ in range(MAX_PAGES):
            try:
                page = await self.client.get_group_msg_history(group.native_id, message_seq=anchor,
                                                               count=self.page_size)
            except OneBotError as exc:
                if "不存在" not in exc.message:
                    raise
                if anchor is not None and oldest is not None and oldest > lo:
                    warnings.append("NapCat 找不到更早的消息，可能已到本机 QQ 保存的最早记录")
                break
            new = [m for m in page if as_str(m.get("message_id")) and as_str(m.get("message_id")) not in seen]
            if not new:
                break
            seen.update(as_str(m.get("message_id")) for m in new)
            stamps = [(t, m) for m in new if (t := _ts(m.get("time"))) > 0]
            if not stamps:
                break
            page_oldest, oldest_msg = min(stamps, key=lambda x: x[0])
            if oldest is not None and page_oldest > oldest:
                warnings.append("NapCat 返回的历史消息没有向前推进，已停止翻页")
                complete = False
                break
            oldest = page_oldest
            for ts, m in stamps:
                raw = message_to_raw(m, group_id=group.native_id, group_name=group.name, tz=self.ctx.tz)
                if raw is None:
                    continue
                texts[raw.native_id] = raw.text
                if lo <= ts < hi:
                    found.setdefault(raw.native_id, raw)
            if page_oldest < lo:
                break
            if len(found) >= limit:
                complete = False
                warnings.append(f"超过单群上限 {limit} 条，只保留最近的 {limit} 条")
                break
            anchor = as_str(oldest_msg.get("message_id"))
        else:
            complete = False
            warnings.append(f"翻页次数达到上限（{MAX_PAGES} 页），较早的消息未取回")
        msgs = sorted(found.values(), key=lambda r: (r.sent_at, r.native_id))
        if len(msgs) > limit:
            msgs, complete = msgs[-limit:], False
        for m in msgs:
            if m.reply_to and not m.quote_text and m.reply_to in texts:
                m.quote_text = texts[m.reply_to][:200]
        return FetchResult(messages=msgs, complete=complete, warnings=warnings)