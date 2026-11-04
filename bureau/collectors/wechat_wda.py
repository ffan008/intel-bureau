"""微信采集器：WeChatDataAnalysis 本地 API（默认 http://127.0.0.1:10392）。

接口与字段按 third_party/refs/WeChatDataAnalysis/src/wechat_decrypt_tool/routers/chat.py 核对：
- ``GET /api/chat/accounts`` → {status, accounts, default_account, default_switchable_account, accountInfos[...]}；
  没有账号时 status="error"、message 为英文说明。accountInfos 里有 realtimeAvailable、dataSourceStatus。
- ``GET /api/chat/sessions?account=&limit=(≤2000)&include_hidden=&preview=none`` →
  {status, sessions:[{id, username, name, avatar, isGroup, ...}]}；群聊 username 以 @chatroom 结尾。
- ``GET /api/chat/messages?username=&account=&limit=(≤500)&offset=&order=desc&source=`` →
  {status, total, hasMore, messages:[...]}。order=desc 时从最新开始按 offset 翻页；字段见 chat_formats。
  source 缺省为 auto：有实时条件时直接读微信本地数据库（WCDB），否则读解密快照。
- ``POST /api/chat/realtime/sync?username=&account=&max_scan=`` 只把实时库的新消息写进 WDA 自己的
  解密快照（output/databases），不影响微信本身。读实时库（source=auto/realtime）时不需要它；
  只有固定读解密快照（source=decrypted）时才有意义，所以 sync_before_fetch 默认关闭。

鉴权：2.x 桌面版（含高级版）给本地 API 加了 Token 校验，业务接口不带
``Authorization: Bearer <API Token>`` 会返回 401 ``external_token_required``。Token 可以手填，
留空时由 ``bureau.integrations.wda_auth`` 自动读应用自己的 ``runtime_settings.json``
（macOS 在 ``~/Library/Application Support/wechat-data-analysis-desktop/output/``）。
源码版 / 开源版没有这道鉴权，读不到 Token 时不带鉴权头，行为与以前一致。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import httpx

from bureau.collectors.base import Collector, CollectorContext
from bureau.contracts import ConfigField, FetchResult, GroupInfo, Health, HealthStatus, Platform, RawMessage
from bureau.integrations.chat_formats import external_url, wda_message_to_raw
from bureau.integrations.common import as_str, get_tz
from bureau.integrations.wda_auth import is_loopback_url, resolve_token

log = logging.getLogger("bureau.collector.wda")

DEFAULT_BASE_URL = "http://127.0.0.1:10392"
SECURITY_NOTE = "本地 API 的 Token 明文存在本机配置里、CORS 为 *，不用时请关闭"
PAGE_SIZE = 500                 # /api/chat/messages 的上限
_KNOWN_ERRORS = {
    "No chat accounts found": "WeChatDataAnalysis 里还没有可用的账号：请先在 WDA 里获取密钥并解密",
    "Account not found": "找不到设置里的微信账号，请留空让程序自动选择，或填写 WDA 账号列表里的名字",
    "No message databases found": "该账号还没有解密出消息数据库，请先在 WDA 里完成解密",
    "Invalid source": "source 参数不正确，可选 auto / realtime / decrypted",
}


def wda_fetch_spec(m: dict[str, Any], kind: str, *, account: str | None, username: str) -> dict[str, Any] | None:
    """v2：bureau.media.fetch_media 取回附件用的描述（字段按 WDA routers/chat_media.py 的接口参数）。

    图片 → /api/chat/media/image（md5 / file_id / server_id），视频 → /api/chat/media/video（md5 / file_id），
    文件 → WDA 没有下载接口，记下文件名、大小、MD5、时间，取回时到 wxidDir/msg/file/<YYYY-MM>/ 里找。
    """
    base: dict[str, Any] = {"type": "wda", "kind": kind, "account": account or None, "username": username}
    if kind == "image":
        sid = as_str(m.get("serverIdStr")) or as_str(m.get("serverId"))
        spec = base | {"md5": as_str(m.get("imageMd5")) or None, "file_id": as_str(m.get("imageFileId")) or None,
                       "server_id": int(sid) if sid.isdigit() and sid != "0" else None}
        if not (spec["md5"] or spec["file_id"] or spec["server_id"]):
            return None
    elif kind == "video":
        spec = base | {"md5": as_str(m.get("videoMd5")) or None, "file_id": as_str(m.get("videoFileId")) or None}
        if not (spec["md5"] or spec["file_id"]):
            return None
    elif kind == "file":
        title = as_str(m.get("title"))
        if not title:
            return None
        spec = base | {"title": title, "file_size": as_str(m.get("fileSize")) or None,
                       "md5": as_str(m.get("fileMd5")) or None, "create_time": m.get("createTime")}
    else:
        return None
    return {k: v for k, v in spec.items() if v is not None}


def attach_wda_fetch(raw: RawMessage, m: dict[str, Any], *, account: str | None, username: str) -> None:
    for att in raw.attachments:
        if att.kind in ("image", "video", "file"):
            spec = wda_fetch_spec(m, att.kind, account=account, username=username)
            if spec:
                att.extra["fetch"] = spec


class WdaError(RuntimeError):
    def __init__(self, message: str, hint: str | None = None, *, down: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.down = down


def _cn(detail: str) -> str:
    for en, cn in _KNOWN_ERRORS.items():
        if en.lower() in (detail or "").lower():
            return cn
    return detail


class WdaCollector(Collector):
    key = "wechat.wda"
    label = "WeChatDataAnalysis 本地 API"
    platforms = (Platform.WECHAT,)
    supports_realtime = False

    def __init__(self, ctx: CollectorContext, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        super().__init__(ctx)
        s = ctx.settings or {}
        self.base_url = (as_str(s.get("base_url")) or DEFAULT_BASE_URL).rstrip("/")
        self.account_setting = as_str(s.get("account")) or None
        self.token_setting = as_str((ctx.secrets or {}).get("token")) or ""
        self.token = self.token_setting
        self.sync_before_fetch = bool(s.get("sync_before_fetch", False))
        self.source = as_str(s.get("source")) or None
        self.tz = get_tz(ctx.tz)
        self._transport = transport
        self._account: str | None = None

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="base_url", label="WDA 地址", type="url", default=DEFAULT_BASE_URL,
                        help="WeChatDataAnalysis 桌面版或源码版启动后的本地 API 地址，默认端口 10392"),
            ConfigField(key="token", label="API Token", type="secret",
                        placeholder="留空自动读取本机应用的 Token",
                        help="桌面版 2.x 的接口鉴权用。在 WDA「设置 → 接口与 MCP」里能看到；"
                             "同一台电脑上留空即可，程序会自动从应用的运行配置里读。"),
            ConfigField(key="account", label="微信账号", placeholder="留空自动使用默认账号",
                        help="WDA 账号列表里的名字（通常是 wxid 目录名）；只登录一个号时留空即可"),
            ConfigField(key="source", label="数据来源", type="select", default="",
                        options=[{"value": "", "label": "自动（优先实时读取）"},
                                 {"value": "realtime", "label": "只读实时库"},
                                 {"value": "decrypted", "label": "只读解密快照"}],
                        help="一般保持自动。实时读取需要在 WDA 里开启实时模式"),
            ConfigField(key="sync_before_fetch", label="拉取前先同步到解密快照", type="bool", default=False,
                        help="只在数据来源为「只读解密快照」时有用：先调用 WDA 的实时同步再读取"),
        ]

    def _headers(self) -> dict[str, str]:
        """2.x 桌面版要 ``Authorization: Bearer <API Token>``。

        设置的 Token 一律携带；自动读到的本地 Token 只在地址是本机时才发，
        避免把别人的本机凭据送到远端地址去。
        """
        if not self.token:
            self.token = resolve_token(None)
        if not self.token:
            return {}
        if not self.token_setting and not is_loopback_url(self.base_url):
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def _token_hint(self) -> str:
        if self.token_setting:
            return ("设置里的 API Token 无效或已更换：到 WDA「设置 → 接口与 MCP」重新复制，"
                    "或清空该项让程序自动读取")
        return "在 WDA「设置 → 接口与 MCP」里复制 API Token，填到本采集器的「API Token」一项"

    async def _get(self, path: str, params: dict[str, Any] | None = None, *, timeout: float = 30.0,
                   method: str = "GET") -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=self._transport, trust_env=False) as client:
                resp = await client.request(method, url, headers=self._headers(),
                                            params={k: v for k, v in (params or {}).items()
                                                    if v not in (None, "")})
        except httpx.ConnectError:
            raise WdaError(f"连不上 WeChatDataAnalysis（{self.base_url}）",
                           "启动 WeChatDataAnalysis 桌面版（或运行 uv run main.py），确认端口是 10392", down=True) from None
        except httpx.TimeoutException:
            raise WdaError(f"WeChatDataAnalysis 响应超时（{timeout:g} 秒）",
                           "WDA 可能正在解密或建索引，稍后再试", down=True) from None
        except httpx.HTTPError as exc:
            raise WdaError(f"访问 WeChatDataAnalysis 出错（{type(exc).__name__}）", down=True) from None
        try:
            data = resp.json()
        except ValueError:
            raise WdaError(f"WeChatDataAnalysis 返回的不是 JSON（HTTP {resp.status_code}），请确认地址正确") from None
        if resp.status_code >= 400:
            detail = data.get("detail") if isinstance(data, dict) else None
            code = ""
            if isinstance(detail, dict):
                code = as_str(detail.get("code"))
                detail = detail.get("message") or detail.get("code")
            if resp.status_code == 401 or code == "external_token_required":
                if not self.token_setting:
                    self.token = ""          # 应用可能重启换了 Token，下次重新读一遍
                raise WdaError("WeChatDataAnalysis 要求有效的 API Token（HTTP 401）", self._token_hint())
            raise WdaError(f"WeChatDataAnalysis 返回错误（HTTP {resp.status_code}）：{_cn(as_str(detail))[:200]}",
                           "在 WDA 界面里确认账号已解密、实时模式正常")
        if not isinstance(data, dict):
            raise WdaError("WeChatDataAnalysis 返回格式不正确")
        return data


    async def _accounts(self, timeout: float = 5.0) -> dict[str, Any]:
        return await self._get("/api/chat/accounts", timeout=timeout)

    async def _resolve_account(self) -> str | None:
        if self.account_setting:
            return self.account_setting
        if self._account is None:
            data = await self._accounts(timeout=15.0)
            if data.get("status") != "success":
                raise WdaError(_cn(as_str(data.get("message"))) or "WeChatDataAnalysis 里没有可用账号",
                               "在 WDA 里获取密钥并解密后再试")
            self._account = (as_str(data.get("default_switchable_account"))
                             or as_str(data.get("default_account")) or None)
        return self._account

    async def health(self) -> HealthStatus:
        try:
            data = await self._accounts(timeout=5.0)
        except WdaError as exc:
            return HealthStatus(ok=False, state=Health.DOWN, detail=exc.message,
                                hint=f"{exc.hint or ''}。{SECURITY_NOTE}".lstrip("。"),
                                data={"base_url": self.base_url})
        accounts = [as_str(a) for a in data.get("accounts") or [] if as_str(a)]
        if data.get("status") != "success" or not accounts:
            return HealthStatus(ok=False, state=Health.DEGRADED,
                                detail=_cn(as_str(data.get("message"))) or "WeChatDataAnalysis 已运行，但还没有可用账号",
                                hint=f"在 WDA 里获取密钥并解密，然后开启实时模式。{SECURITY_NOTE}",
                                data={"base_url": self.base_url})
        account = self.account_setting or as_str(data.get("default_switchable_account")) or accounts[0]
        if self.account_setting and self.account_setting not in accounts:
            return HealthStatus(ok=False, state=Health.DEGRADED,
                                detail=f"设置里的账号 {self.account_setting} 不在 WDA 账号列表中",
                                hint=f"清空「微信账号」让程序自动选择。{SECURITY_NOTE}",
                                data={"base_url": self.base_url, "accounts": len(accounts)})
        info = next((i for i in data.get("accountInfos") or [] if isinstance(i, dict)
                     and as_str(i.get("account")) == account), {})
        src = info.get("dataSourceStatus") or {}
        active = as_str(src.get("activeSource")) or as_str(info.get("defaultSource"))
        # 2.x 桌面版的「直连」模式不落解密快照：realtimeAvailable 和 hasDecryptedDbs 都是 false，
        # 但 activeSource=realtime 表示能直接读微信的实时库，属于正常可用状态，不能当成降级。
        direct_live = as_str(info.get("mode")) == "direct" and active == "realtime"
        realtime = bool(info.get("realtimeAvailable")) or direct_live
        fallback = as_str(src.get("message")) or as_str(src.get("reason"))
        detail = f"已连接 WeChatDataAnalysis，账号 {account}（共 {len(accounts)} 个），" + (
            "实时读取可用" if realtime else "实时读取不可用，将读取解密快照")
        state = Health.OK if realtime or info.get("hasDecryptedDbs") else Health.DEGRADED
        hint = SECURITY_NOTE if realtime else f"在 WDA 里开启实时模式以读取最新消息{('（' + fallback[:60] + '）') if fallback else ''}。{SECURITY_NOTE}"
        return HealthStatus(ok=state is Health.OK, state=state, detail=detail, hint=hint,
                            data={"base_url": self.base_url, "account": account, "accounts": len(accounts),
                                  "realtime": realtime})

    async def list_groups(self) -> list[GroupInfo]:
        account = await self._resolve_account()
        data = await self._get("/api/chat/sessions", {"account": account, "limit": 2000, "include_hidden": "true",
                                                       "preview": "none", "source": self.source}, timeout=60.0)
        if data.get("status") != "success":
            raise WdaError(_cn(as_str(data.get("message"))) or "读取会话列表失败")
        groups: list[GroupInfo] = []
        for s in data.get("sessions") or []:
            uname = as_str(s.get("username")) or as_str(s.get("id"))
            if not uname.endswith("@chatroom"):
                continue
            groups.append(GroupInfo(platform=Platform.WECHAT, native_id=uname, name=as_str(s.get("name")) or uname,
                                    avatar_url=external_url(s.get("avatar")),
                                    extra={k: s.get(k) for k in ("isTop", "isEnterpriseGroup", "lastMessageTime")
                                           if s.get(k) not in (None, "")}))
        return groups


    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        try:
            return await self._fetch(group, since, until, limit)
        except WdaError as exc:
            raise RuntimeError(f"{exc.message}" + (f"（{exc.hint}）" if exc.hint else "")) from None

    async def _fetch(self, group: GroupInfo, since: datetime, until: datetime, limit: int) -> FetchResult:
        account = await self._resolve_account()
        warnings: list[str] = []
        if self.sync_before_fetch:
            try:
                await self._get("/api/chat/realtime/sync", {"username": group.native_id, "account": account,
                                                            "max_scan": 2000}, timeout=120.0, method="POST")
            except WdaError as exc:
                warnings.append(f"拉取前同步失败，继续读取已有数据：{exc.message}")
        lo, hi = since.timestamp(), until.timestamp()
        collected: dict[str, RawMessage] = {}
        offset = 0
        complete = True
        while True:
            data = await self._get("/api/chat/messages", {
                "username": group.native_id, "account": account, "limit": PAGE_SIZE, "offset": offset,
                "order": "desc", "source": self.source}, timeout=90.0)
            if data.get("status") != "success":
                raise WdaError(_cn(as_str(data.get("message"))) or "读取消息失败")
            page = [m for m in data.get("messages") or [] if isinstance(m, dict)]
            reached_start = False
            for m in page:
                ct = m.get("createTime")
                try:
                    ts = float(ct)
                except (TypeError, ValueError):
                    continue
                if ts < lo:
                    reached_start = True
                    continue
                if ts >= hi:
                    continue
                raw = wda_message_to_raw(m, group_id=group.native_id, group_name=group.name, tz=self.tz)
                if raw is not None:
                    attach_wda_fetch(raw, m, account=account, username=group.native_id)
                    collected.setdefault(raw.native_id, raw)
            if reached_start or not page or not data.get("hasMore"):
                break
            if len(collected) >= limit:
                complete = False
                warnings.append(f"超过单群上限 {limit} 条，只保留最近的 {limit} 条")
                break
            offset += len(page)
        msgs = sorted(collected.values(), key=lambda r: (r.sent_at, r.native_id))
        if len(msgs) > limit:
            msgs = msgs[-limit:]
            complete = False
        by_id = {m.native_id: m for m in msgs}
        for m in msgs:
            if m.reply_to and not m.quote_text and m.reply_to in by_id:
                m.quote_text = by_id[m.reply_to].text[:200]
        return FetchResult(messages=msgs, complete=complete, warnings=warnings)