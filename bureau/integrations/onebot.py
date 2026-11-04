"""OneBot 11（NapCatQQ）HTTP 客户端、消息段转文本、上报验签与解析。

已按 NapCatQQ 源码核实（packages/napcat-onebot，main 分支，2026-10-28）：
- HTTP 服务端：``POST http://<host>:<port>/<action>``，JSON 参数；token 用
  ``Authorization: Bearer <token>`` 或 ``?access_token=`` 传入，不匹配时返回 HTTP 403。
- 返回体：``{"status": "ok"|"failed", "retcode": 0|..., "data": ..., "message": "...", "wording": "..."}``。
- HTTP 客户端（事件上报）：配置了 token 时请求头带 ``x-signature: sha1=<HMAC-SHA1(token, body)>``
  和 ``x-self-id``，不带 Authorization。
- ``get_group_msg_history``：group_id(str)、message_seq(str，可选，填某条消息的 message_id)、
  count、reverse_order、disable_get_url、parse_mult_msg、quick_reply；返回 ``{"messages": [...]}``，
  按时间从旧到新，并包含 message_seq 指定的那一条。不传 message_seq 时取最新 count 条。
- 消息里 ``message_id == message_seq``（NapCat 由哈希生成的短 ID）；``real_seq`` 才是群内真实序号。
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
from collections.abc import Mapping
from typing import Any

import httpx

from bureau.contracts import Attachment, MessageKind, Platform, RawMessage
from bureau.integrations.common import DEFAULT_TZ, as_str, clip, from_timestamp, get_tz

log = logging.getLogger("bureau.integrations.onebot")

DEFAULT_BASE_URL = "http://127.0.0.1:3010"

RETCODE_MESSAGES: dict[int, str] = {
    100: "参数缺失或无效",
    102: "没有可用的数据",
    103: "操作失败",
    104: "QQ 登录状态失效，请重新登录",
    200: "NapCat 执行出错",
    201: "NapCat 执行超时",
    400: "请求参数错误",
    1400: "请求参数错误或业务执行失败",
    1401: "权限不足",
    1403: "token 校验失败",
    1404: "资源不存在或接口不支持",
}


class OneBotError(Exception):
    """调用 OneBot 接口失败。message 是中文，hint 是修复建议。"""

    def __init__(self, message: str, *, hint: str | None = None, retcode: int | None = None,
                 http_status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.retcode = retcode
        self.http_status = http_status
        self.retryable = retryable


def _describe_retcode(retcode: int, raw: str) -> str:
    base = RETCODE_MESSAGES.get(retcode, f"错误码 {retcode}")
    first = (raw or "").strip().splitlines()[0] if (raw or "").strip() else ""
    return f"{base}：{clip(first, 120)}" if first and first not in base else base


class OneBotClient:
    """异步 OneBot 11 HTTP 客户端。``call`` 成功时返回 data 字段，失败抛 OneBotError（中文）。"""

    def __init__(self, base_url: str | None = None, token: str | None = None, *,
                 timeout: float = 15.0, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.base_url = (base_url or DEFAULT_BASE_URL).rstrip("/")
        self.token = (token or "").strip() or None
        self.timeout = timeout
        self._transport = transport

    async def call(self, action: str, *, timeout: float | None = None, **params: Any) -> Any:
        headers = {"Content-Type": "application/json; charset=utf-8"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        body = json.dumps(params, ensure_ascii=False).encode("utf-8")
        url = f"{self.base_url}/{action}"
        try:
            async with httpx.AsyncClient(timeout=timeout or self.timeout, transport=self._transport,
                                         trust_env=False) as client:
                resp = await client.post(url, content=body, headers=headers)
        except httpx.ConnectError:
            raise OneBotError(
                f"连不上 NapCat 的 OneBot HTTP 服务（{self.base_url}）",
                hint="确认 NapCat 已启动并登录，且在 WebUI（http://127.0.0.1:6099）里启用了 HTTP 服务端、端口与这里一致",
                retryable=True) from None
        except httpx.TimeoutException:
            raise OneBotError(f"调用 {action} 超时（{timeout or self.timeout:g} 秒）",
                              hint="NapCat 可能正忙或 QQ 已掉线，稍后重试", retryable=True) from None
        except httpx.HTTPError as exc:
            raise OneBotError(f"调用 {action} 时网络出错（{type(exc).__name__}）", retryable=True) from None

        if resp.status_code in (401, 403):
            raise OneBotError("NapCat 拒绝访问：token 不正确", http_status=resp.status_code,
                              hint="在工作台填写与 NapCat WebUI「HTTP 服务端」里相同的 token")
        if resp.status_code == 404:
            raise OneBotError(f"NapCat 不支持接口 {action}（HTTP 404）", http_status=404)
        if resp.status_code >= 500:
            raise OneBotError(f"NapCat 内部错误（HTTP {resp.status_code}）", http_status=resp.status_code,
                              retryable=True)
        try:
            payload = resp.json()
        except ValueError:
            raise OneBotError(f"NapCat 返回的不是 JSON（HTTP {resp.status_code}），请确认地址指向 OneBot HTTP 服务端",
                              http_status=resp.status_code) from None
        if not isinstance(payload, dict):
            return payload
        status = str(payload.get("status") or "").lower()
        try:
            retcode = int(payload.get("retcode") or 0)
        except (TypeError, ValueError):
            retcode = -1
        if status in ("ok", "async") and retcode in (0, 1):
            return payload.get("data")
        raw = str(payload.get("wording") or payload.get("message") or payload.get("msg") or "")
        hint = None
        if retcode in (1403,) or "token" in raw.lower():
            hint = "检查 token 是否与 NapCat 配置一致"
        elif "不支持" in raw:
            hint = "升级 NapCat 到最新版本"
        raise OneBotError(f"{action} 调用失败：{_describe_retcode(retcode, raw)}", retcode=retcode, hint=hint,
                          retryable=retcode in (200, 201))

    # 常用接口的薄封装（参数名以 NapCat 源码为准）
    async def get_login_info(self) -> dict[str, Any]:
        return await self.call("get_login_info", timeout=5.0) or {}

    async def get_group_list(self, *, no_cache: bool = False) -> list[dict[str, Any]]:
        data = await self.call("get_group_list", no_cache=no_cache)
        return data if isinstance(data, list) else []

    async def get_group_msg_history(self, group_id: str | int, *, message_seq: str | int | None = None,
                                    count: int = 50, parse_mult_msg: bool = False,
                                    disable_get_url: bool = True) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"group_id": str(group_id), "count": int(count), "reverse_order": False,
                                  "parse_mult_msg": parse_mult_msg, "disable_get_url": disable_get_url}
        if message_seq not in (None, "", 0, "0"):
            params["message_seq"] = str(message_seq)
        data = await self.call("get_group_msg_history", timeout=30.0, **params)
        msgs = (data or {}).get("messages") if isinstance(data, dict) else data
        return [m for m in (msgs or []) if isinstance(m, dict)]

    async def send_private_msg(self, user_id: str | int, text: str) -> dict[str, Any]:
        return await self.call("send_private_msg", user_id=str(user_id),
                               message=[{"type": "text", "data": {"text": text}}]) or {}

    async def send_group_msg(self, group_id: str | int, text: str) -> dict[str, Any]:
        return await self.call("send_group_msg", group_id=str(group_id),
                               message=[{"type": "text", "data": {"text": text}}]) or {}


# ---------------------------------------------------------------- 消息段

_CQ_RE = re.compile(r"\[CQ:([A-Za-z0-9_.-]+)((?:,[^\]]*)?)\]")


def _cq_unescape(s: str) -> str:
    return s.replace("&#44;", ",").replace("&#91;", "[").replace("&#93;", "]").replace("&amp;", "&")


def parse_cq_string(raw: str) -> list[dict[str, Any]]:
    """把 CQ 码字符串（messagePostFormat=string 时）转成消息段数组。"""
    segs: list[dict[str, Any]] = []
    pos = 0
    for m in _CQ_RE.finditer(raw or ""):
        if m.start() > pos:
            segs.append({"type": "text", "data": {"text": _cq_unescape(raw[pos:m.start()])}})
        data: dict[str, Any] = {}
        for kv in (m.group(2) or "").lstrip(",").split(","):
            if "=" in kv:
                k, _, v = kv.partition("=")
                data[k.strip()] = _cq_unescape(v)
        segs.append({"type": m.group(1), "data": data})
        pos = m.end()
    if pos < len(raw or ""):
        segs.append({"type": "text", "data": {"text": _cq_unescape(raw[pos:])}})
    return segs


def normalize_segments(segments: Any) -> list[dict[str, Any]]:
    """接受段数组、单个段或 CQ 码字符串，统一成 [{"type":..., "data": {...}}]。"""
    if segments is None:
        return []
    if isinstance(segments, str):
        return parse_cq_string(segments)
    if isinstance(segments, Mapping):
        segments = [segments]
    out: list[dict[str, Any]] = []
    for seg in segments if isinstance(segments, list) else []:
        if isinstance(seg, str):
            out.extend(parse_cq_string(seg))
        elif isinstance(seg, Mapping):
            data = seg.get("data")
            out.append({"type": str(seg.get("type") or ""), "data": dict(data) if isinstance(data, Mapping) else {}})
    return out


def _http_url(value: Any) -> str | None:
    s = as_str(value)
    if s.startswith("//"):
        s = "https:" + s
    return s if s.lower().startswith(("http://", "https://")) else None


def parse_json_card(data: Any) -> tuple[str, str | None, str]:
    """解析 json 卡片段，返回 (标题, 链接, 类别 "link"|"card")。

    QQ 的 ark 卡片结构多样：常见的有 ``meta.news``（链接分享）、``meta.detail_1``（小程序）、
    ``meta.contact``（名片）等；这里按通用规则在 meta 的各子对象里找 title/desc/jumpUrl。
    """
    obj: Any = data
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except ValueError:
            return "", None, "card"
    if not isinstance(obj, Mapping):
        return "", None, "card"
    app = as_str(obj.get("app"))
    title = ""
    url: str | None = None
    meta = obj.get("meta")
    if isinstance(meta, Mapping):
        for sub in meta.values():
            if not isinstance(sub, Mapping):
                continue
            title = title or as_str(sub.get("title")) or as_str(sub.get("desc"))
            url = url or _http_url(sub.get("jumpUrl")) or _http_url(sub.get("qqdocurl")) or _http_url(sub.get("url"))
            if title and url:
                break
    if not title:
        title = re.sub(r"^\[[^\]]{1,8}\]\s*", "", as_str(obj.get("prompt"))) or as_str(obj.get("desc"))
    kind = "link"
    if "miniapp" in app or "contact" in app or "qun" in app or not url:
        kind = "card"
    return title, url, kind


def _face_text(data: Mapping[str, Any]) -> str:
    raw = data.get("raw")
    label = as_str(raw.get("faceText")) if isinstance(raw, Mapping) else ""
    label = label.lstrip("/")
    return f"[{label}]" if label else "[表情]"


def _forward_preview(data: Mapping[str, Any]) -> str:
    content = data.get("content")
    if not isinstance(content, list) or not content:
        return "[合并转发]"
    items = []
    for node in content[:3]:
        if not isinstance(node, Mapping):
            continue
        sender = node.get("sender") if isinstance(node.get("sender"), Mapping) else {}
        name = as_str(sender.get("card")) or as_str(sender.get("nickname")) or as_str(node.get("nickname")) or "?"
        text, *_ = segments_to_text(node.get("message") if "message" in node else node.get("content"))
        items.append(f"{name}：{clip(text, 30)}")
    head = f"[合并转发] 共 {len(content)} 条"
    return head + ("：" + "；".join(items) if items else "")


def _fetch_spec(action: str, d: Mapping[str, Any]) -> dict[str, Any] | None:
    """v2：bureau.media.fetch_media 用的取回描述（按 NapCat 源码：get_image / get_file 接受 ``file`` 或
    ``file_id``，返回本地路径 / url / base64；群文件可再用 get_group_file_url(group_id, file_id)）。
    group_id 由 message_to_raw 补上。历史消息用 disable_get_url 拉取时 url 是 NapCat 本机路径，记为 local_hint。"""
    file_ref = as_str(d.get("file"))
    file_id = as_str(d.get("file_id"))
    if not (file_ref or file_id):
        return None
    spec: dict[str, Any] = {"type": "onebot", "action": action}
    if file_ref:
        spec["file"] = file_ref
    if file_id:
        spec["file_id"] = file_id
    if action == "get_file" and file_ref:
        spec["name"] = file_ref
    raw_url = as_str(d.get("url"))
    if _http_url(raw_url):
        spec["url"] = _http_url(raw_url)
    elif raw_url and len(raw_url) > 2 and raw_url[1] == ":":
        spec["local_hint"] = raw_url
    return spec


_KIND_PRIORITY: list[tuple[str, MessageKind]] = [
    ("forward", MessageKind.FORWARD), ("reply", MessageKind.REPLY), ("file", MessageKind.FILE),
    ("video", MessageKind.VIDEO), ("voice", MessageKind.VOICE), ("link", MessageKind.LINK),
    ("card", MessageKind.CARD), ("text", MessageKind.TEXT), ("image", MessageKind.IMAGE),
    ("sticker", MessageKind.STICKER), ("system", MessageKind.SYSTEM), ("other", MessageKind.OTHER),
]


def segments_to_text(segments: Any) -> tuple[str, MessageKind, list[Attachment], list[str], str | None]:
    """OneBot 消息段 → (可读文本, 消息类型, 附件, @列表, 被回复的消息 ID)。

    支持 text、at、reply、face、mface、image、record、video、file、onlinefile、flashtransfer、
    json（卡片：解析标题和链接）、xml、markdown、forward、node、music、contact、location、
    poke、dice、rps，以及 CQ 码字符串。
    """
    pieces: list[str] = []
    cats: set[str] = set()
    attachments: list[Attachment] = []
    mentions: list[str] = []
    reply_to: str | None = None

    for seg in normalize_segments(segments):
        t, d = seg["type"], seg["data"]
        if t == "text":
            txt = str(d.get("text") or "")
            if txt.strip():
                cats.add("text")
            pieces.append(txt)
        elif t == "at":
            qq = as_str(d.get("qq"))
            name = as_str(d.get("name"))
            pieces.append("@全体成员 " if qq == "all" else f"@{name or qq} ")
            if qq:
                mentions.append(qq)
            cats.add("text")
        elif t == "reply":
            reply_to = reply_to or (as_str(d.get("id")) or as_str(d.get("seq")) or None)
            cats.add("reply")
        elif t == "face":
            pieces.append(_face_text(d))
            cats.add("sticker")
        elif t in ("mface", "dice", "rps"):
            label = as_str(d.get("summary")) or {"dice": "骰子", "rps": "猜拳"}.get(t, "")
            pieces.append(f"[{label}]" if label else "[表情]")
            cats.add("sticker")
        elif t == "image":
            summary = as_str(d.get("summary"))
            is_sticker = bool(d.get("emoji_id")) or str(d.get("sub_type")) == "1"
            label = summary if summary and summary not in ("[图片]", "[动画表情]") else ""
            if is_sticker:
                pieces.append(f"[{label.strip('[]')}]" if label else "[表情]")
                cats.add("sticker")
            else:
                pieces.append(f"[图片{'：' + label.strip('[]') if label else ''}]")
                cats.add("image")
                extra = {k: d[k] for k in ("file", "file_size") if d.get(k)}
                fetch = _fetch_spec("get_image", d)
                if fetch:
                    extra["fetch"] = fetch
                attachments.append(Attachment(kind="image", title=label or None, url=_http_url(d.get("url")),
                                              extra=extra))
        elif t in ("record", "voice"):
            pieces.append("[语音]")
            cats.add("voice")
            attachments.append(Attachment(kind="voice", url=_http_url(d.get("url"))))
        elif t == "video":
            pieces.append("[视频]")
            cats.add("video")
            extra = {k: d[k] for k in ("file", "file_size") if d.get(k)}
            fetch = _fetch_spec("get_file", d)
            if fetch:
                extra["fetch"] = fetch
            attachments.append(Attachment(kind="video", url=_http_url(d.get("url")), extra=extra))
        elif t in ("file", "onlinefile", "flashtransfer"):
            name = as_str(d.get("file")) if t == "file" else as_str(d.get("fileName"))
            label = name or ("QQ 闪传" if t == "flashtransfer" else "")
            pieces.append(f"[文件] {label}".strip())
            cats.add("file")
            extra = {k: d[k] for k in ("file_id", "file_size", "fileSize") if d.get(k)}
            fetch = _fetch_spec("get_file", d) if t == "file" else None
            if fetch:
                extra["fetch"] = fetch
            attachments.append(Attachment(kind="file", title=name or None, url=_http_url(d.get("url")), extra=extra))
        elif t == "json":
            title, url, kind = parse_json_card(d.get("data"))
            tag = "[链接]" if kind == "link" else "[卡片]"
            pieces.append(" ".join(x for x in (tag, title, url) if x))
            cats.add(kind)
            attachments.append(Attachment(kind="link" if kind == "link" else "card", title=title or None, url=url))
        elif t == "xml":
            m = re.search(r'(?:url|actionData)="(https?://[^"]+)"', as_str(d.get("data")))
            title_m = re.search(r"<title>([^<]{1,80})</title>", as_str(d.get("data")))
            title = title_m.group(1) if title_m else ""
            url = m.group(1) if m else None
            pieces.append(" ".join(x for x in ("[卡片]", title, url) if x))
            cats.add("link" if url else "card")
            attachments.append(Attachment(kind="link" if url else "card", title=title or None, url=url))
        elif t == "music":
            url = _http_url(d.get("url"))
            title = as_str(d.get("title")) or "音乐分享"
            pieces.append(" ".join(x for x in ("[音乐]", title, url) if x))
            cats.add("link" if url else "card")
            attachments.append(Attachment(kind="link" if url else "card", title=title, url=url))
        elif t == "markdown":
            pieces.append(str(d.get("content") or ""))
            cats.add("text")
        elif t in ("forward", "node"):
            pieces.append(_forward_preview(d))
            cats.add("forward")
        elif t == "contact":
            pieces.append(f"[名片] {as_str(d.get('type'))} {as_str(d.get('id'))}".strip())
            cats.add("card")
        elif t == "location":
            title = as_str(d.get("title")) or as_str(d.get("content"))
            pieces.append(f"[位置] {title}".strip())
            cats.add("card")
        elif t == "poke":
            pieces.append("[戳一戳]")
            cats.add("system")
        elif t:
            pieces.append(f"[{t}]")
            cats.add("other")

    text = re.sub(r"[ \t]+\n", "\n", "".join(pieces)).strip()
    kind = next((k for c, k in _KIND_PRIORITY if c in cats), MessageKind.TEXT)
    if kind is MessageKind.REPLY and not text:
        text = "[引用回复]"
    return text, kind, attachments, list(dict.fromkeys(mentions)), reply_to


# ---------------------------------------------------------------- 消息 → RawMessage

def message_to_raw(msg: Mapping[str, Any], *, group_id: str | None = None, group_name: str | None = None,
                   tz: str = DEFAULT_TZ) -> RawMessage | None:
    """OneBot 群消息对象（上报事件或 get_group_msg_history 的元素）→ RawMessage。"""
    gid = as_str(msg.get("group_id")) or as_str(group_id)
    mid = as_str(msg.get("message_id")) or as_str(msg.get("message_seq"))
    if not gid or not mid:
        return None
    sent_at = from_timestamp(msg.get("time"), get_tz(tz))
    if sent_at is None:
        return None
    sender = msg.get("sender") if isinstance(msg.get("sender"), Mapping) else {}
    uid = as_str(sender.get("user_id")) or as_str(msg.get("user_id"))
    name = as_str(sender.get("card")) or as_str(sender.get("nickname")) or uid or "未知成员"
    segments = msg.get("message")
    if segments in (None, "", []) and msg.get("raw_message"):
        segments = msg.get("raw_message")
    text, kind, attachments, mentions, reply_to = segments_to_text(segments)
    for att in attachments:
        if isinstance(att.extra.get("fetch"), dict):
            att.extra["fetch"]["group_id"] = gid
    is_self =(as_str(msg.get("post_type")) == "message_sent" or as_str(msg.get("message_sent_type")) == "self"
               or (bool(uid) and uid == as_str(msg.get("self_id"))))
    raw = {k: msg.get(k) for k in ("message_id", "message_seq", "real_seq", "real_id") if msg.get(k) is not None}
    return RawMessage(
        platform=Platform.QQ, group_native_id=gid, group_name=as_str(msg.get("group_name")) or group_name or None,
        native_id=mid, sender_id=uid or None, sender_name=name, sent_at=sent_at, kind=kind,
        text=text, reply_to=reply_to, mentions=mentions, attachments=attachments, is_self=is_self, raw=raw or None,
    )


def parse_onebot_event(event: dict) -> RawMessage | None:
    """解析 OneBot 上报事件。只处理群消息（含自己发出的 message_sent），其它事件返回 None。"""
    if not isinstance(event, Mapping):
        return None
    if as_str(event.get("post_type")) not in ("message", "message_sent"):
        return None
    if as_str(event.get("message_type")) != "group":
        return None
    try:
        return message_to_raw(event)
    except Exception:  # noqa: BLE001 — 上报内容不可信，解析失败只记日志
        log.warning("OneBot 上报事件解析失败，已忽略", exc_info=True)
        return None


# ---------------------------------------------------------------- 上报验签

def _header(headers: Mapping[str, str], name: str) -> str:
    getter = getattr(headers, "get", None)
    if getter is not None:
        val = getter(name)
        if val is None:
            val = getter(name.lower())
        if val is not None:
            return str(val)
    lname = name.lower()
    for k, v in dict(headers).items():
        if str(k).lower() == lname:
            return str(v)
    return ""


def _hmac_sha1(key: str, body: bytes) -> str:
    return hmac.new(key.encode("utf-8"), body, hashlib.sha1).hexdigest()


def verify_onebot_request(headers: Mapping[str, str], body: bytes, *, secret: str | None, token: str | None) -> bool:
    """校验 OneBot HTTP 上报请求。

    - ``X-Signature: sha1=<hex>``：hex 为 HMAC-SHA1(key, body)。key 依次尝试 secret、token
      （NapCat 的 HTTP 客户端把配置里的 token 当作签名密钥，见 network/http-client.ts）。
    - ``Authorization: Bearer <token>``（也接受 ``Token <token>``）：与 token 比对。
    - secret 和 token 都没配置时返回 True，由 A 的回环地址限制兜底。
    所有比较都用 hmac.compare_digest，防计时攻击。
    """
    secret = (secret or "").strip() or None
    token = (token or "").strip() or None
    if not secret and not token:
        return True
    body = body or b""

    sig = _header(headers, "X-Signature").strip()
    if sig:
        algo, _, digest = sig.partition("=")
        if algo.strip().lower() == "sha1" and digest:
            got = digest.strip().lower().encode("ascii", "ignore")
            for key in dict.fromkeys(k for k in (secret, token) if k):
                if hmac.compare_digest(got, _hmac_sha1(key, body).encode("ascii")):
                    return True

    auth = _header(headers, "Authorization").strip()
    if auth and token:
        scheme, _, value = auth.partition(" ")
        if scheme.lower() in ("bearer", "token") and value.strip():
            if hmac.compare_digest(value.strip().encode("utf-8"), token.encode("utf-8")):
                return True
    return False


def onebot_credentials(secrets: Mapping[str, Any] | None) -> tuple[str | None, str | None]:
    """从采集器密钥里取 (secret, token)，供 A 调用 verify_onebot_request 时使用。

    token：NapCat「HTTP 服务端」的 token（主动调用接口用，也是 HTTP 客户端上报的签名密钥）；
    report_secret：上报签名密钥，留空时等于 token。
    """
    s = secrets or {}
    token = as_str(s.get("token")) or as_str(s.get("access_token")) or None
    secret = as_str(s.get("report_secret")) or as_str(s.get("secret")) or None
    return secret, token