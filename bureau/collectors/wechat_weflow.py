"""微信采集器（备选）：WeFlow HTTP API（默认 http://127.0.0.1:5031）。

按 https://raw.githubusercontent.com/hicccc77/WeFlow/main/docs/HTTP-API.md 核实（2026-10-28）：
- 鉴权：除 /health 外都要 ``Authorization: Bearer <token>``（也支持 ?access_token=）。
- ``GET /health`` → {"status":"ok"}；``GET /api/v1/sessions?keyword=&limit=`` →
  {success, count, sessions:[{username, displayName, type, lastTimestamp, unreadCount}]}。
- ``GET /api/v1/sessions/:id/messages?since=&end=&limit=(≤5000)&offset=`` → ChatLab 标准 JSON
  （chatlab/meta/members/messages）外加 ``sync: {hasMore, nextSince, nextOffset, watermark}``。
- ``GET /api/v1/messages?talker=&start=&end=&limit=(≤10000)&offset=`` → {success, hasMore, messages:[
  {localId, serverId, localType, createTime, isSend, senderUsername, content, parsedContent, replyToMessageId, quote…}]}；
  没有发送者昵称，需配合 ``GET /api/v1/group-members?chatroomId=``。
WeFlow 官方说明"不再内置任何读取/解密组件"，需要用户自备解密组件。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote

import httpx

from bureau.collectors.base import Collector, CollectorContext
from bureau.contracts import ConfigField, FetchResult, GroupInfo, Health, HealthStatus, Platform, RawMessage
from bureau.integrations.chat_formats import (StableIdMaker, chatlab_members, chatlab_message_to_raw,
                                              weflow_message_to_raw)
from bureau.integrations.common import as_str, get_tz

DEFAULT_BASE_URL = "http://127.0.0.1:5031"
DECRYPT_NOTE = "WeFlow 官方不再内置读取/解密组件，需要你自备解密组件并在 WeFlow 里完成数据库连接"


def attach_weflow_fetch(raw: RawMessage | None, m: dict[str, Any]) -> None:
    """v2：附件有 WeFlow 给出的本机绝对路径（ChatLab 的 mediaPath、/api/v1/messages 的 mediaLocalPath）时，
    写入 ``extra.fetch = {"type": "local", "path": ...}``。WeFlow 只有在 media=1 导出后才提供媒体，
    本采集器不请求导出，所以多数消息没有路径，此时不写 fetch。"""
    if raw is None:
        return
    path = as_str(m.get("mediaLocalPath")) or as_str(m.get("mediaPath"))
    # 只认本机的绝对路径：Windows 的 C:\… 或 macOS / Linux 的 /Users/…
    is_abs = path.startswith("/") or (len(path) > 2 and path[1] == ":" and path[2] in "\\/")
    if not path or not is_abs:
        return
    for att in raw.attachments:
        if att.kind in ("image", "video", "file"):
            att.extra["fetch"] = {"type": "local", "path": path}


class WeFlowError(RuntimeError):
    def __init__(self, message: str, hint: str | None = None, *, state: Health = Health.DOWN) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.state = state


class WeFlowCollector(Collector):
    key = "wechat.weflow"
    label = "WeFlow HTTP API"
    platforms = (Platform.WECHAT,)
    supports_realtime = False

    def __init__(self, ctx: CollectorContext, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(ctx)
        s = ctx.settings or {}
        self.base_url = (as_str(s.get("base_url")) or DEFAULT_BASE_URL).rstrip("/")
        self.mode = as_str(s.get("mode")) or "chatlab"
        self.token = as_str((ctx.secrets or {}).get("token")) or None
        self.tz = get_tz(ctx.tz)
        self._transport = transport

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="base_url", label="WeFlow 地址", type="url", default=DEFAULT_BASE_URL,
                        help="在 WeFlow 设置里开启「API 服务」后的地址，默认端口 5031"),
            ConfigField(key="token", label="API Token", type="secret", required=True,
                        help="WeFlow 设置页里显示的 API Token"),
            ConfigField(key="mode", label="拉取方式", type="select", default="chatlab",
                        options=[{"value": "chatlab", "label": "ChatLab Pull（推荐，带群昵称）"},
                                 {"value": "messages", "label": "/api/v1/messages（原始字段）"}]),
        ]

    async def _get(self, path: str, params: dict[str, Any] | None = None, *, timeout: float = 60.0,
                   auth: bool = True) -> Any:
        headers = {"Authorization": f"Bearer {self.token}"} if (auth and self.token) else {}
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport, trust_env=False) as client:
                resp = await client.get(f"{self.base_url}{path}", headers=headers,
                                        params={k: v for k, v in (params or {}).items() if v not in (None, "")})
        except httpx.ConnectError:
            raise WeFlowError(f"连不上 WeFlow（{self.base_url}）",
                              "打开 WeFlow，在设置里开启「API 服务」，确认端口是 5031") from None
        except httpx.TimeoutException:
            raise WeFlowError(f"WeFlow 响应超时（{timeout:g} 秒）", "稍后再试") from None
        except httpx.HTTPError as exc:
            raise WeFlowError(f"访问 WeFlow 出错（{type(exc).__name__}）") from None
        if resp.status_code in (401, 403):
            raise WeFlowError("WeFlow 拒绝访问：API Token 不正确", "把 WeFlow 设置页里的 API Token 填到工作台",
                              state=Health.DEGRADED)
        try:
            data = resp.json()
        except ValueError:
            raise WeFlowError(f"WeFlow 返回的不是 JSON（HTTP {resp.status_code}）", state=Health.DEGRADED) from None
        if resp.status_code >= 400 or (isinstance(data, dict) and data.get("success") is False):
            msg = as_str(data.get("error") or data.get("message") or data.get("msg")) if isinstance(data, dict) else ""
            raise WeFlowError(f"WeFlow 返回错误（HTTP {resp.status_code}）：{msg[:160] or '未知原因'}",
                              f"确认已在 WeFlow 里完成数据库连接。{DECRYPT_NOTE}", state=Health.DEGRADED)
        return data


    async def health(self) -> HealthStatus:
        data = {"base_url": self.base_url}
        try:
            await self._get("/health", timeout=3.0, auth=False)
        except WeFlowError as exc:
            return HealthStatus(ok=False, state=exc.state, detail=exc.message,
                                hint=f"{exc.hint or ''}。{DECRYPT_NOTE}".lstrip("。"), data=data)
        if not self.token:
            return HealthStatus(ok=False, state=Health.UNCONFIGURED, detail="WeFlow 已运行，但还没有填写 API Token",
                                hint=f"把 WeFlow 设置页里的 API Token 填到工作台。{DECRYPT_NOTE}", data=data)
        try:
            res = await self._get("/api/v1/sessions", {"limit": 1}, timeout=4.0)
        except WeFlowError as exc:
            return HealthStatus(ok=False, state=exc.state, detail=exc.message,
                                hint=f"{exc.hint or ''}。{DECRYPT_NOTE}".lstrip("。"), data=data)
        data["sessions_ok"] = True
        return HealthStatus(ok=True, state=Health.OK, detail="已连接 WeFlow，API Token 有效",
                            hint=DECRYPT_NOTE, data=data | {"count": (res or {}).get("count")})

    async def list_groups(self) -> list[GroupInfo]:
        try:
            res = await self._get("/api/v1/sessions", {"limit": 5000})
        except WeFlowError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None
        out = []
        for s in (res or {}).get("sessions") or []:
            uname = as_str(s.get("username"))
            if not uname.endswith("@chatroom"):
                continue
            out.append(GroupInfo(platform=Platform.WECHAT, native_id=uname, name=as_str(s.get("displayName")) or uname,
                                 extra={"last_timestamp": s.get("lastTimestamp")}))
        return out

    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        try:
            if self.mode == "messages":
                return await self._fetch_messages_api(group, since, until, limit)
            return await self._fetch_chatlab(group, since, until, limit)
        except WeFlowError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None

    @staticmethod
    def _finish(found: dict[str, RawMessage], limit: int, warnings: list[str], complete: bool) -> FetchResult:
        msgs = sorted(found.values(), key=lambda r: (r.sent_at, r.native_id))
        if len(msgs) > limit:
            msgs, complete = msgs[:limit], False
            warnings.append(f"超过单群上限 {limit} 条，只返回最早的 {limit} 条")
        return FetchResult(messages=msgs, complete=complete, warnings=warnings)


    async def _fetch_chatlab(self, group: GroupInfo, since: datetime, until: datetime, limit: int) -> FetchResult:
        lo, hi = since.timestamp(), until.timestamp()
        params: dict[str, Any] = {"since": max(int(lo) - 1, 0), "end": int(hi), "limit": 5000, "offset": 0}
        path = f"/api/v1/sessions/{quote(group.native_id, safe='')}/messages"
        found: dict[str, RawMessage] = {}
        ids = StableIdMaker()
        warnings: list[str] = []
        complete = True
        seen_cursors: set[tuple[Any, Any]] = set()
        for _ in range(200):
            doc = await self._get(path, params, timeout=120.0)
            if not isinstance(doc, dict):
                break
            members = chatlab_members(doc)
            for m in doc.get("messages") or []:
                if not isinstance(m, dict):
                    continue
                raw = chatlab_message_to_raw(m, platform=Platform.WECHAT, group_id=group.native_id,
                                             group_name=group.name, tz=self.tz, members=members, ids=ids)
                attach_weflow_fetch(raw, m)
                if raw and lo <= raw.sent_at.timestamp() < hi:
                    found.setdefault(raw.native_id, raw)
            sync = doc.get("sync") or {}
            if not sync.get("hasMore"):
                break
            if len(found) >= limit:
                complete = False
                break
            nxt = (sync.get("nextSince", params["since"]), sync.get("nextOffset", params["offset"] + 5000))
            if nxt in seen_cursors:
                warnings.append("WeFlow 返回的分页游标没有前进，已停止翻页")
                complete = False
                break
            seen_cursors.add(nxt)
            params["since"], params["offset"] = nxt
        return self._finish(found, limit, warnings, complete)

    async def _fetch_messages_api(self, group: GroupInfo, since: datetime, until: datetime,
                                  limit: int) -> FetchResult:
        lo, hi = since.timestamp(), until.timestamp()
        names: dict[str, str] = {}
        warnings: list[str] = []
        try:
            mem = await self._get("/api/v1/group-members", {"chatroomId": group.native_id}, timeout=60.0)
            for x in (mem or {}).get("members") or []:
                wxid = as_str(x.get("wxid"))
                if wxid:
                    names[wxid] = as_str(x.get("groupNickname")) or as_str(x.get("displayName")) or wxid
        except WeFlowError as exc:
            warnings.append(f"读取群成员失败，发送者将显示为 wxid：{exc.message}")
        found: dict[str, RawMessage] = {}
        ids = StableIdMaker()
        offset, complete = 0, True
        while True:
            res = await self._get("/api/v1/messages", {"talker": group.native_id, "start": int(lo), "end": int(hi),
                                                       "limit": 1000, "offset": offset}, timeout=120.0)
            page = [m for m in (res or {}).get("messages") or [] if isinstance(m, dict)]
            for m in page:
                raw = weflow_message_to_raw(m, group_id=group.native_id, group_name=group.name, tz=self.tz,
                                            names=names, ids=ids)
                attach_weflow_fetch(raw, m)
                if raw and lo <= raw.sent_at.timestamp() < hi:
                    found.setdefault(raw.native_id, raw)
            if not page or not (res or {}).get("hasMore"):
                break
            if len(found) >= limit:
                complete = False
                break
            offset += len(page)
        return self._finish(found, limit, warnings, complete)