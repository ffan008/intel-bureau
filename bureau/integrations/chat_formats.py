"""微信侧数据格式 → RawMessage 的映射，采集器（实时）和文件导入（导出文件）共用。

字段来源（均已核对源码）：
- WeChatDataAnalysis：``routers/chat.py`` 的 ``/api/chat/messages`` 返回项与 ``chat_export_service.py``
  导出的 messages.json 字段一致（id、localId、serverId/serverIdStr、type、createTime、renderType、isSent、
  senderUsername、senderDisplayName、content、title、url、linkType、from、quote*、fileSize…）。
- ChatLab 标准格式 v0.0.2（hellodigua/ChatLab docs/cn/standard/chatlab-format.md）：消息 type 数字表。
- WeFlow：``docs/HTTP-API.md`` 与 ``electron/services/export/formatters/JsonFormatter.ts``。
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, tzinfo
from typing import Any
from urllib.parse import urlsplit

from bureau.contracts import Attachment, MessageKind, Platform, RawMessage
from bureau.integrations.common import as_str, from_timestamp, stable_id

_URL_RE = re.compile(r"https?://[^\s<>\"'）)】\]]+")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "0.0.0.0"}


def external_url(value: Any) -> str | None:
    """只保留外部 http(s) 链接；指向本机的地址（WDA/WeFlow 的媒体接口）返回 None。"""
    s = as_str(value)
    if not s.lower().startswith(("http://", "https://")):
        return None
    try:
        host = (urlsplit(s).hostname or "").lower()
    except ValueError:
        return None
    return None if host in _LOCAL_HOSTS else s


def urls_in(text: str) -> list[str]:
    return list(dict.fromkeys(_URL_RE.findall(text or "")))


class StableIdMaker:
    """没有平台消息 ID 时，用 群 + 时间 + 发送者 + 正文 生成稳定 ID；同一份数据里重复的内容依次加 -1、-2。"""

    def __init__(self) -> None:
        self._seen: Counter[str] = Counter()

    def make(self, group_id: str, sent_at: datetime, sender: str, text: str) -> str:
        base = stable_id(group_id, int(sent_at.timestamp()), sender, text)
        n = self._seen[base]
        self._seen[base] += 1
        return f"h{base}" if n == 0 else f"h{base}-{n}"


# ---------------------------------------------------------------- WeChatDataAnalysis

def wda_native_id(m: Mapping[str, Any]) -> str | None:
    """WDA 消息的稳定 ID：优先 serverId（全局唯一），没有时退回 本地ID+时间。"""
    sid = as_str(m.get("serverIdStr")) or as_str(m.get("serverId"))
    if sid and sid != "0":
        return sid
    lid = as_str(m.get("localId"))
    ct = as_str(m.get("createTime"))
    if lid and ct:
        return f"l{lid}-{ct}"
    return as_str(m.get("id")) or None


def _wda_sender(m: Mapping[str, Any]) -> tuple[str | None, str]:
    uid = as_str(m.get("senderUsername")) or None
    name = (as_str(m.get("senderDisplayName")) or as_str(m.get("senderGroupNickname"))
            or as_str(m.get("senderName")) or uid or "未知成员")
    return uid, name


def wda_message_to_raw(m: Mapping[str, Any], *, group_id: str, group_name: str | None,
                       tz: tzinfo, native_id: str | None = None) -> RawMessage | None:
    """WDA ``/api/chat/messages`` 返回项（或导出 messages.json 的一项）→ RawMessage。"""
    sent_at = from_timestamp(m.get("createTime"), tz)
    if sent_at is None:
        return None
    rt = as_str(m.get("renderType")) or "text"
    content = as_str(m.get("content"))
    title = as_str(m.get("title"))
    url = external_url(m.get("url"))
    kind = MessageKind.TEXT
    text = content
    atts: list[Attachment] = []
    reply_to = quote_text = None
    if rt == "image":
        kind, text = MessageKind.IMAGE, "[图片]"
        atts.append(Attachment(kind="image", url=external_url(m.get("imageUrl")),
                               extra={k: m[k] for k in ("imageMd5", "imageFileId") if m.get(k)}))
    elif rt == "emoji":
        kind, text = MessageKind.STICKER, "[表情]"
    elif rt == "voice":
        kind = MessageKind.VOICE
        secs = as_str(m.get("voiceLength"))
        text = f"[语音 {secs}秒]" if secs else "[语音]"
        if as_str(m.get("voiceTranscript")):
            text += " " + as_str(m.get("voiceTranscript"))
        atts.append(Attachment(kind="voice"))
    elif rt == "video":
        kind, text = MessageKind.VIDEO, "[视频]"
        atts.append(Attachment(kind="video", url=external_url(m.get("videoUrl"))))
    elif rt == "link":
        link_type = as_str(m.get("linkType"))
        is_card = link_type in ("mini_program", "finder") or not url
        kind = MessageKind.CARD if is_card else MessageKind.LINK
        label = {"mini_program": "[小程序]", "finder": "[视频号]", "music": "[音乐]"}.get(
            link_type, "[卡片]" if is_card else "[链接]")
        desc = content if content and content != title else ""
        src = as_str(m.get("from"))
        text = " ".join(x for x in (label, title or desc, f"（{src}）" if src else "", url or "") if x)
        if desc and title:
            text += f"\n{desc}"
        atts.append(Attachment(kind="card" if is_card else "link", title=title or desc or None, url=url,
                               extra={k: v for k, v in (("linkType", link_type), ("from", src)) if v}))
    elif rt == "file":
        kind = MessageKind.FILE
        text = content or (f"[文件] {title}" if title else "[文件]")
        atts.append(Attachment(kind="file", title=title or None,
                               extra={k: m[k] for k in ("fileSize", "fileMd5") if m.get(k)}))
    elif rt == "quote":
        kind = MessageKind.REPLY
        text = content or "[引用回复]"
        reply_to = as_str(m.get("quoteServerId")) or None
        qt = as_str(m.get("quoteTitle"))
        qc = as_str(m.get("quoteContent"))
        quote_text = (f"{qt}：{qc}" if qt and qc else (qc or qt)) or None
    elif rt == "system":
        kind = MessageKind.RECALL if ("撤回" in content and len(content) < 60) else MessageKind.SYSTEM
        text = content or "[系统消息]"
    elif rt == "chatHistory":
        kind = MessageKind.FORWARD
        text = f"[聊天记录] {title}" if title else "[聊天记录]"
        if content and content not in ("[聊天记录]", title):
            text += f"\n{content}"
    elif rt == "redPacket":
        kind, text = MessageKind.REDPACKET, f"[红包] {content}".strip()
    elif rt == "transfer":
        kind = MessageKind.OTHER
        text = " ".join(x for x in ("[转账]", as_str(m.get("amount")), content) if x)
    elif rt == "location":
        kind = MessageKind.OTHER
        text = "[位置] " + (as_str(m.get("locationPoiname")) or as_str(m.get("locationLabel")) or content)
    elif rt == "voip":
        kind, text = MessageKind.OTHER, f"[通话] {content}".strip()
    elif rt != "text":
        kind = MessageKind.OTHER if not content else MessageKind.TEXT
    uid, name = _wda_sender(m)
    mentions = [as_str(x) for x in (m.get("atUsernames") or []) if as_str(x)]
    nid = native_id or wda_native_id(m)
    if not nid:
        return None
    return RawMessage(
        platform=Platform.WECHAT, group_native_id=group_id, group_name=group_name, native_id=nid,
        sender_id=uid, sender_name=name, sent_at=sent_at, kind=kind, text=(text or "").strip(),
        reply_to=reply_to, quote_text=quote_text, mentions=mentions, attachments=atts,
        is_self=bool(m.get("isSent")),
        raw={k: m.get(k) for k in ("localId", "type", "renderType") if m.get(k) is not None} or None,
    )


# ---------------------------------------------------------------- ChatLab 标准格式（WeFlow ChatLab Pull 同此）

CHATLAB_KIND: dict[int, MessageKind] = {
    0: MessageKind.TEXT, 1: MessageKind.IMAGE, 2: MessageKind.VOICE, 3: MessageKind.VIDEO,
    4: MessageKind.FILE, 5: MessageKind.STICKER, 7: MessageKind.LINK, 8: MessageKind.OTHER,
    20: MessageKind.REDPACKET, 21: MessageKind.OTHER, 22: MessageKind.SYSTEM, 23: MessageKind.OTHER,
    24: MessageKind.CARD, 25: MessageKind.REPLY, 26: MessageKind.FORWARD, 27: MessageKind.CARD,
    80: MessageKind.SYSTEM, 81: MessageKind.RECALL, 99: MessageKind.OTHER,
}
CHATLAB_PLACEHOLDER: dict[int, str] = {
    1: "[图片]", 2: "[语音]", 3: "[视频]", 4: "[文件]", 5: "[表情]", 7: "[链接]", 8: "[位置]",
    20: "[红包]", 21: "[转账]", 22: "[拍一拍]", 23: "[通话]", 24: "[分享]", 26: "[合并转发]",
    27: "[名片]", 80: "[系统消息]", 81: "[撤回了一条消息]",
}
_ATT_KIND = {MessageKind.IMAGE: "image", MessageKind.VOICE: "voice", MessageKind.VIDEO: "video",
             MessageKind.FILE: "file", MessageKind.LINK: "link", MessageKind.CARD: "card"}


def chatlab_members(doc: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for mem in doc.get("members") or []:
        if isinstance(mem, Mapping) and as_str(mem.get("platformId")):
            out[as_str(mem.get("platformId"))] = dict(mem)
    return out


def chatlab_message_to_raw(m: Mapping[str, Any], *, platform: Platform, group_id: str, group_name: str | None,
                           tz: tzinfo, members: Mapping[str, Mapping[str, Any]] | None = None,
                           ids: StableIdMaker | None = None) -> RawMessage | None:
    sent_at = from_timestamp(m.get("timestamp"), tz)
    if sent_at is None:
        return None
    try:
        t = int(m.get("type") or 0)
    except (TypeError, ValueError):
        t = 99
    kind = CHATLAB_KIND.get(t, MessageKind.OTHER)
    content = as_str(m.get("content"))
    placeholder = CHATLAB_PLACEHOLDER.get(t, "")
    if not content:
        text = placeholder
    elif placeholder and t in (1, 2, 3, 5) and not content.startswith("["):
        text = f"{placeholder} {content}"
    else:
        text = content
    sender = as_str(m.get("sender")) or None
    mem = (members or {}).get(sender or "") or {}
    name = (as_str(m.get("groupNickname")) or as_str(mem.get("groupNickname")) or as_str(m.get("accountName"))
            or as_str(mem.get("accountName")) or sender or "未知成员")
    atts = []
    if kind in _ATT_KIND:
        found = urls_in(content)
        atts.append(Attachment(kind=_ATT_KIND[kind], url=external_url(found[0]) if found else None,
                               extra={"mediaPath": m["mediaPath"]} if m.get("mediaPath") else {}))
    nid = as_str(m.get("platformMessageId"))
    if not nid:
        nid = (ids or StableIdMaker()).make(group_id, sent_at, sender or name, text)
    return RawMessage(
        platform=platform, group_native_id=group_id, group_name=group_name, native_id=nid,
        sender_id=sender, sender_name=name, sent_at=sent_at, kind=kind, text=text,
        reply_to=as_str(m.get("replyToMessageId")) or None, attachments=atts,
    )


# ---------------------------------------------------------------- WeFlow（导出 JSON 与 /api/v1/messages）

WEFLOW_TYPE_NAME: dict[str, MessageKind] = {
    "文本消息": MessageKind.TEXT, "图片消息": MessageKind.IMAGE, "语音消息": MessageKind.VOICE,
    "视频消息": MessageKind.VIDEO, "动画表情": MessageKind.STICKER, "位置消息": MessageKind.OTHER,
    "名片消息": MessageKind.CARD, "链接消息": MessageKind.LINK, "文件消息": MessageKind.FILE,
    "聊天记录": MessageKind.FORWARD, "小程序消息": MessageKind.CARD, "引用消息": MessageKind.REPLY,
    "音乐消息": MessageKind.LINK, "转账消息": MessageKind.OTHER, "群公告": MessageKind.SYSTEM,
    "通话消息": MessageKind.OTHER, "系统消息": MessageKind.SYSTEM, "其他消息": MessageKind.OTHER,
}
_WX_BASE_KIND = {1: MessageKind.TEXT, 3: MessageKind.IMAGE, 34: MessageKind.VOICE, 43: MessageKind.VIDEO,
                 47: MessageKind.STICKER, 48: MessageKind.OTHER, 42: MessageKind.CARD, 50: MessageKind.OTHER,
                 10000: MessageKind.SYSTEM}
_WX_APP_SUB_KIND = {5: MessageKind.LINK, 4: MessageKind.LINK, 68: MessageKind.LINK, 3: MessageKind.LINK,
                    6: MessageKind.FILE, 74: MessageKind.FILE, 19: MessageKind.FORWARD, 33: MessageKind.CARD,
                    36: MessageKind.CARD, 51: MessageKind.CARD, 57: MessageKind.REPLY, 2000: MessageKind.OTHER,
                    2001: MessageKind.REDPACKET, 2003: MessageKind.REDPACKET}
_KIND_PLACEHOLDER = {MessageKind.IMAGE: "[图片]", MessageKind.VOICE: "[语音]", MessageKind.VIDEO: "[视频]",
                     MessageKind.STICKER: "[表情]", MessageKind.FILE: "[文件]"}


def wechat_local_type_kind(local_type: Any) -> MessageKind:
    """微信 4.x 的 local_type：低 32 位是基础类型，type=49 时高 32 位是 appmsg 子类型。"""
    try:
        lt = int(local_type)
    except (TypeError, ValueError):
        return MessageKind.OTHER
    base, sub = lt & 0xFFFFFFFF, lt >> 32
    if base == 49:
        return _WX_APP_SUB_KIND.get(sub, MessageKind.LINK)
    return _WX_BASE_KIND.get(base, MessageKind.OTHER)


def weflow_message_to_raw(m: Mapping[str, Any], *, group_id: str, group_name: str | None, tz: tzinfo,
                          names: Mapping[str, str] | None = None, ids: StableIdMaker | None = None
                          ) -> RawMessage | None:
    sent_at = from_timestamp(m.get("createTime"), tz)
    if sent_at is None:
        return None
    tname = as_str(m.get("type"))
    kind = WEFLOW_TYPE_NAME.get(tname) or wechat_local_type_kind(m.get("localType"))
    text = as_str(m.get("parsedContent")) or as_str(m.get("content"))
    if text.startswith("<") and kind is not MessageKind.TEXT:
        text = ""
    text = text or _KIND_PLACEHOLDER.get(kind, "")
    uid = as_str(m.get("senderUsername")) or None
    name = (as_str(m.get("senderDisplayName")) or (names or {}).get(uid or "", "") or as_str(m.get("senderNickname"))
            or uid or "未知成员")
    quote = m.get("quote") if isinstance(m.get("quote"), Mapping) else {}
    reply_to = as_str(m.get("replyToMessageId")) or as_str(quote.get("platformMessageId")) or None
    q_sender = as_str(m.get("quotedSender")) or as_str(quote.get("accountName"))
    q_body = as_str(m.get("quotedContent")) or as_str(quote.get("content"))
    quote_text = (f"{q_sender}：{q_body}" if q_sender and q_body else q_body) or None
    if reply_to and kind is MessageKind.TEXT:
        kind = MessageKind.REPLY
    atts: list[Attachment] = []
    link_url = external_url(m.get("linkUrl")) or external_url(m.get("url"))
    if kind in (MessageKind.LINK, MessageKind.CARD):
        title = as_str(m.get("linkTitle")) or as_str(m.get("appMsgDesc"))
        found = urls_in(text)
        link_url = link_url or (found[0] if found else None)
        atts.append(Attachment(kind="link" if kind is MessageKind.LINK else "card", title=title or None, url=link_url))
        if link_url and link_url not in text:
            text = f"{text} {link_url}".strip()
    elif kind in _ATT_KIND:
        atts.append(Attachment(kind=_ATT_KIND[kind], url=external_url(m.get("mediaUrl")),
                               title=as_str(m.get("mediaFileName")) or None))
    nid = as_str(m.get("platformMessageId")) or as_str(m.get("serverId"))
    if not nid or nid == "0":
        nid = (ids or StableIdMaker()).make(group_id, sent_at, uid or name, text)
    return RawMessage(
        platform=Platform.WECHAT, group_native_id=group_id, group_name=group_name, native_id=nid,
        sender_id=uid, sender_name=name, sent_at=sent_at, kind=kind, text=text, reply_to=reply_to,
        quote_text=quote_text, attachments=atts, is_self=bool(m.get("isSend")),
    )