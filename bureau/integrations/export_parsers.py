"""聊天记录导出文件 / 粘贴文本的解析（``bureau.collectors.file_import.parse_export`` 的实现）。

支持的格式（自动识别）：
- ``wda_json`` / ``wda_zip``：WeChatDataAnalysis 导出的 messages.json（或整个导出 zip）。
- ``weflow_json``：WeFlow 导出的 JSON（含 arkme-json 精简格式）。
- ``chatlab``：ChatLab 标准格式 JSON / JSONL（WeFlow 的 ChatLab 导出同此）。
- ``csv``：通用 CSV，中英文表头都认（时间/time、发送者/sender、内容/content、群/group…）。
- ``pasted_text``：复制粘贴的聊天文本，"昵称 / 时间 / 正文" 三段式，或 "[时间] 昵称：正文" 单行式。

消息 ID：文件里有平台消息 ID（WDA serverId、ChatLab platformMessageId）时直接使用，这样与实时
采集器的 ID 一致；没有时用 群 + 时间 + 发送者 + 正文 的稳定哈希，同一份文件重复导入不会产生重复消息。
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from collections.abc import Mapping
from datetime import date, datetime, time, timedelta, tzinfo
from pathlib import PurePath
from typing import Any

from bureau.contracts import GroupInfo, MessageKind, ParsedImport, Platform, RawMessage
from bureau.integrations.chat_formats import (StableIdMaker, chatlab_members, chatlab_message_to_raw,
                                              wda_message_to_raw, weflow_message_to_raw)
from bureau.integrations.common import DEFAULT_TZ, as_str, from_timestamp, get_tz, stable_id

MAX_ZIP_MEMBER = 200 * 1024 * 1024
SUPPORTED_HINT = ("支持：WeChatDataAnalysis 导出 JSON/zip、WeFlow JSON、ChatLab JSON/JSONL、"
                  "CSV（含时间/发送者/内容列）、粘贴的「昵称 / 时间 / 正文」文本")


class ImportFormatError(ValueError):
    """无法识别或解析的导入内容。message 是中文。"""


def import_group_id(platform: Platform, name: str) -> str:
    """不知道平台群 ID 时，用群名生成稳定的 ID。"""
    return "import-" + stable_id(platform.value, name.strip(), length=16)


def _group(platform: Platform, native_id: str | None, name: str | None, *, fallback: str) -> GroupInfo:
    gname = (name or "").strip() or fallback
    return GroupInfo(platform=platform, native_id=(native_id or "").strip() or import_group_id(platform, gname),
                     name=gname, extra={"imported": True})


# ---------------------------------------------------------------- 时间解析

_PERIOD = r"(?P<period>凌晨|早上|上午|中午|下午|晚上|傍晚)?\s*"
_CLOCK = r"(?P<h>\d{1,2})[:：](?P<mi>\d{2})(?:[:：](?P<s>\d{2}))?"
_TIME_RE = re.compile(
    r"^\s*(?:"
    r"(?P<y>\d{4})\s*[年\-/.]\s*(?P<mo>\d{1,2})\s*[月\-/.]\s*(?P<d>\d{1,2})\s*日?"
    r"|(?P<mo2>\d{1,2})\s*[月\-/]\s*(?P<d2>\d{1,2})\s*日?"
    r"|(?P<rel>今天|昨天|前天)"
    r"|(?P<wk>(?:星期|周)[一二三四五六日天])"
    r")?\s*(?:[T ]\s*)?" + _PERIOD + _CLOCK + r"\s*$")
_WEEK = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6}


def _hour24(h: int, period: str | None) -> int:
    if period in ("下午", "晚上", "傍晚") and h < 12:
        return h + 12
    if period == "中午" and h < 11:
        return h + 12
    if period == "凌晨" and h == 12:
        return 0
    return h


def parse_time_token(s: str, ref: date) -> tuple[str, Any] | None:
    """把时间文字解析成 token：("full", datetime 无时区) / ("md", (月, 日, time)) / ("t", time)。

    支持 2026年10月25日 18:14、2026-10-25 18:14:05、2026/10/25 18:14、10-25 18:14、10月25日 下午6:14、
    昨天 18:14、星期三 18:14、18:14。不是时间时返回 None。
    """
    m = _TIME_RE.match(s or "")
    if not m:
        return None
    try:
        h = _hour24(int(m["h"]), m["period"])
        t = time(h, int(m["mi"]), int(m["s"] or 0))
    except ValueError:
        return None
    try:
        if m["y"]:
            return "full", datetime.combine(date(int(m["y"]), int(m["mo"]), int(m["d"])), t)
        if m["mo2"]:
            mo, d = int(m["mo2"]), int(m["d2"])
            date(2000, mo, d)                    # 校验月日
            return "md", (mo, d, t)
    except ValueError:
        return None
    if m["rel"]:
        return "full", datetime.combine(ref - timedelta(days={"今天": 0, "昨天": 1, "前天": 2}[m["rel"]]), t)
    if m["wk"]:
        back = (ref.weekday() - _WEEK[m["wk"][-1]]) % 7 or 7
        return "full", datetime.combine(ref - timedelta(days=back), t)
    return "t", t


def resolve_tokens(tokens: list[tuple[str, Any] | None], tz: tzinfo, ref: date) -> tuple[list[datetime | None], bool]:
    """按上下文补全缺失的日期，返回 (带时区的时间列表, 是否用到了推断)。

    - 只有时间：沿用前面最近出现的日期；时间比上一条早 10 分钟以上视为跨过了零点，日期加一天。
      开头几条没有日期时，用后面第一条带日期的；全篇都没有日期时用今天。
    - 只有月日：年份沿用前面出现过的年份，否则用今年。
    """
    first_date = next((v.date() for k, v in (t for t in tokens if t) if k == "full"), None)
    cur_date: date | None = None
    cur_year = first_date.year if first_date else ref.year
    prev: datetime | None = None
    inferred = False
    out: list[datetime | None] = []
    for tok in tokens:
        if tok is None:
            out.append(None)
            continue
        kind, val = tok
        if kind == "full":
            dt = val
            cur_year = dt.year
        elif kind == "md":
            mo, d, t = val
            dt = datetime.combine(date(cur_year, mo, d), t)
            inferred = inferred or first_date is None
        else:
            inferred = True
            base = cur_date or first_date or ref
            dt = datetime.combine(base, val)
            if prev is not None and dt < prev - timedelta(minutes=10):
                dt += timedelta(days=1)
        cur_date = dt.date()
        prev = dt
        out.append(dt.replace(tzinfo=tz))
    return out, inferred


def parse_datetime_value(value: Any, tz: tzinfo, ref: date) -> datetime | tuple[str, Any] | None:
    """CSV 单元格等：数字时间戳 / ISO 8601 / 中文时间文字。无日期的结果以 token 返回，交给 resolve_tokens。"""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return from_timestamp(value, tz)
    s = str(value).strip()
    if not s:
        return None
    if re.fullmatch(r"\d{10}(\d{3})?(\.\d+)?", s):
        return from_timestamp(s, tz)
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=tz)
    except ValueError:
        pass
    tok = parse_time_token(s, ref)
    if tok and tok[0] == "full":
        return tok[1].replace(tzinfo=tz)
    return tok


# ---------------------------------------------------------------- 粘贴文本

_DATE_PART = r"\d{4}\s*[年\-/.]\s*\d{1,2}\s*[月\-/.]\s*\d{1,2}\s*日?|\d{1,2}\s*[月\-/]\s*\d{1,2}\s*日?|昨天|前天|今天"
_TIME_PART = r"(?:凌晨|早上|上午|中午|下午|晚上|傍晚)?\s*\d{1,2}[:：]\d{2}(?:[:：]\d{2})?"
_INLINE_NAME_TIME = re.compile(rf"^(?P<name>.{{1,40}}?)\s+(?P<ts>(?:{_DATE_PART})\s*{_TIME_PART})\s*$")
_INLINE_TIME_NAME = re.compile(rf"^(?P<ts>(?:{_DATE_PART})\s*{_TIME_PART})\s+(?P<name>.{{1,40}}?)\s*$")
_BRACKET_LINE = re.compile(rf"^\[(?P<ts>(?:(?:{_DATE_PART})\s*)?{_TIME_PART})\]\s*(?P<name>[^:：\n]{{1,40}})[:：]\s*(?P<body>.*)$")


def _looks_like_name(s: str) -> bool:
    s = s.strip()
    return (0 < len(s) <= 40 and "://" not in s and not s.startswith(("http", "#", ">", "-", "*"))
            and parse_time_token(s, date.today()) is None)


def parse_pasted_text(text: str, *, platform: Platform, group_name: str | None, tz: tzinfo,
                      ref: date) -> ParsedImport:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[dict[str, Any]] = []
    orphan = 0
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        nxt_idx = i + 1
        while nxt_idx < len(lines) and not lines[nxt_idx].strip():
            nxt_idx += 1
        nxt = lines[nxt_idx].strip() if nxt_idx < len(lines) else ""
        header = None
        if line:
            mb = _BRACKET_LINE.match(line)
            if mb:
                blocks.append({"name": mb["name"].strip(), "tok": parse_time_token(mb["ts"], ref),
                               "body": [mb["body"]] if mb["body"] else []})
                i += 1
                continue
            if _looks_like_name(line) and nxt and parse_time_token(nxt, ref) and nxt_idx == i + 1:
                header = (line.rstrip(":："), parse_time_token(nxt, ref), nxt_idx + 1)
            else:
                mi = _INLINE_NAME_TIME.match(line) or _INLINE_TIME_NAME.match(line)
                if mi and _looks_like_name(mi["name"]):
                    header = (mi["name"].strip().rstrip(":："), parse_time_token(mi["ts"], ref), i + 1)
        if header:
            blocks.append({"name": header[0], "tok": header[1], "body": []})
            i = header[2]
            continue
        if blocks:
            blocks[-1]["body"].append(lines[i].rstrip())
        elif line:
            orphan += 1
        i += 1
    if not blocks:
        raise ImportFormatError("没有识别出任何消息。" + SUPPORTED_HINT)
    stamps, inferred = resolve_tokens([b["tok"] for b in blocks], tz, ref)
    gname = (group_name or "").strip() or "粘贴导入"
    group = _group(platform, None, gname, fallback="粘贴导入")
    ids = StableIdMaker()
    msgs: list[RawMessage] = []
    for b, ts in zip(blocks, stamps):
        body = "\n".join(b["body"]).strip()
        if ts is None or not body:
            continue
        msgs.append(RawMessage(platform=platform, group_native_id=group.native_id, group_name=group.name,
                               native_id=ids.make(group.native_id, ts, b["name"], body), sender_name=b["name"],
                               sent_at=ts, kind=MessageKind.TEXT, text=body))
    warnings = []
    if orphan:
        warnings.append(f"开头有 {orphan} 行不属于任何消息，已忽略")
    if inferred:
        warnings.append("部分消息只有时间没有日期，已按上下文推断日期，请核对")
    if not group_name:
        warnings.append("没有指定群名，已归入「粘贴导入」")
    return ParsedImport(group=group, messages=msgs, format="pasted_text", warnings=warnings)


# ---------------------------------------------------------------- CSV

_CSV_COLS: dict[str, set[str]] = {
    "time": {"时间", "发送时间", "消息时间", "时间戳", "日期时间", "time", "timestamp", "datetime", "date_time",
             "createtime", "create_time", "sent_at", "senttime", "msgtime"},
    "date": {"日期", "date"},
    "clock": {"时刻", "clock", "hour"},
    "sender": {"发送者", "发送人", "发言人", "昵称", "群昵称", "用户", "用户名", "姓名", "成员", "sender", "from",
               "name", "nickname", "user", "author", "speaker", "sender_name", "sendername", "senderdisplayname"},
    "content": {"内容", "消息", "消息内容", "正文", "文本", "聊天内容", "content", "message", "text", "msg", "body"},
    "group": {"群", "群名", "群聊", "群名称", "会话", "会话名称", "聊天", "group", "group_name", "groupname",
              "chat", "chat_name", "room", "conversation", "talker"},
    "type": {"类型", "消息类型", "type", "msg_type", "msgtype", "kind"},
    "id": {"消息id", "id", "message_id", "msgid", "msg_id", "serverid", "platformmessageid"},
    "sender_id": {"发送者id", "用户id", "wxid", "qq", "qq号", "sender_id", "senderid", "user_id", "uid",
                  "senderusername"},
}
_TYPE_WORDS: list[tuple[tuple[str, ...], MessageKind]] = [
    (("图片", "image", "photo", "picture"), MessageKind.IMAGE), (("语音", "voice", "audio"), MessageKind.VOICE),
    (("视频", "video"), MessageKind.VIDEO), (("文件", "file"), MessageKind.FILE),
    (("表情", "sticker", "emoji"), MessageKind.STICKER), (("链接", "link", "url"), MessageKind.LINK),
    (("小程序", "名片", "卡片", "card"), MessageKind.CARD), (("聊天记录", "合并转发", "forward"), MessageKind.FORWARD),
    (("引用", "回复", "reply", "quote"), MessageKind.REPLY), (("撤回", "recall"), MessageKind.RECALL),
    (("系统", "system"), MessageKind.SYSTEM), (("红包", "redpacket"), MessageKind.REDPACKET),
    (("文本", "text"), MessageKind.TEXT),
]


def _norm_header(h: str) -> str:
    return re.sub(r"[\s﻿_\-]|[（(][^）)]*[）)]", "", (h or "").strip().lower())


def _map_columns(headers: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    norm_sets = {k: {_norm_header(x) for x in v} for k, v in _CSV_COLS.items()}
    for h in headers:
        nh = _norm_header(h)
        for field_name, names in norm_sets.items():
            if nh in names and field_name not in out:
                out[field_name] = h
                break
    return out


def _csv_kind(value: str) -> MessageKind:
    v = (value or "").strip().lower()
    if not v:
        return MessageKind.TEXT
    for words, kind in _TYPE_WORDS:
        if any(w in v for w in words):
            return kind
    return MessageKind.OTHER


def looks_like_csv(text: str) -> bool:
    first = next((ln for ln in text.splitlines() if ln.strip()), "")
    if not any(sep in first for sep in (",", "\t", ";")):
        return False
    try:
        dialect = csv.Sniffer().sniff(first, delimiters=",\t;")
        headers = next(csv.reader([first], dialect))
    except (csv.Error, StopIteration):
        headers = re.split(r"[,\t;]", first)
    cols = _map_columns(headers)
    return ("time" in cols or "date" in cols) and "content" in cols


def parse_csv_rows(text: str, *, platform: Platform, group_name: str | None, filename: str | None,
                   tz: tzinfo, ref: date) -> list[ParsedImport]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample.splitlines()[0] if sample else ",", delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    cols = _map_columns(reader.fieldnames or [])
    if not (("time" in cols or "date" in cols) and "content" in cols):
        raise ImportFormatError("CSV 至少需要「时间」和「内容」两列（表头可以是中文或英文）")
    rows, toks = [], []
    bad = 0
    for row in reader:
        t_raw = (row.get(cols["time"]) if "time" in cols else "") or ""
        if "date" in cols and ("time" not in cols or not re.search(r"\d{4}|[年月/-]", t_raw)):
            t_raw = f"{row.get(cols['date']) or ''} {t_raw or row.get(cols.get('clock', ''), '') or ''}".strip()
        val = parse_datetime_value(t_raw, tz, ref)
        if val is None:
            bad += 1
            continue
        rows.append(row)
        toks.append(("full", val.astimezone(tz).replace(tzinfo=None)) if isinstance(val, datetime) else val)
    stamps, inferred = resolve_tokens(toks, tz, ref)
    fallback = group_name or (PurePath(filename).stem if filename else "") or "CSV 导入"
    by_group: dict[str, list[tuple[dict[str, Any], datetime]]] = {}
    for row, ts in zip(rows, stamps):
        row_group = as_str(row.get(cols["group"])) if "group" in cols else ""
        g = group_name or row_group or fallback
        by_group.setdefault(g, []).append((row, ts))
    results = []
    for gname, items in by_group.items():
        group = _group(platform, None, gname, fallback=fallback)
        ids = StableIdMaker()
        msgs = []
        for row, ts in items:
            body = as_str(row.get(cols["content"]))
            sender = as_str(row.get(cols["sender"])) if "sender" in cols else ""
            sender = sender or "未知成员"
            kind = _csv_kind(as_str(row.get(cols["type"]))) if "type" in cols else MessageKind.TEXT
            if not body:
                continue
            nid = as_str(row.get(cols["id"])) if "id" in cols else ""
            msgs.append(RawMessage(
                platform=platform, group_native_id=group.native_id, group_name=group.name,
                native_id=nid or ids.make(group.native_id, ts, sender, body), sender_name=sender,
                sender_id=(as_str(row.get(cols["sender_id"])) or None) if "sender_id" in cols else None,
                sent_at=ts, kind=kind, text=body))
        warnings = []
        if bad:
            warnings.append(f"有 {bad} 行时间无法识别，已跳过")
        if inferred:
            warnings.append("部分行只有时间没有日期，已按上下文推断日期")
        results.append(ParsedImport(group=group, messages=msgs, format="csv", warnings=warnings))
    if not results:
        raise ImportFormatError("CSV 里没有可导入的消息行")
    return results


# ---------------------------------------------------------------- JSON 系

def _sorted(msgs: list[RawMessage]) -> list[RawMessage]:
    uniq: dict[str, RawMessage] = {}
    for m in msgs:
        uniq.setdefault(m.native_id, m)
    return sorted(uniq.values(), key=lambda r: (r.sent_at, r.native_id))


def parse_wda_doc(doc: Mapping[str, Any], *, platform: Platform, group_name: str | None, tz: tzinfo,
                  fmt: str = "wda_json") -> ParsedImport:
    conv = doc.get("conversation") if isinstance(doc.get("conversation"), Mapping) else {}
    uname = as_str(conv.get("username"))
    name = group_name or as_str(conv.get("displayName"))
    if name == "已隐藏":
        name = group_name or ""
    group = _group(platform, uname, name, fallback="WDA 导入")
    msgs, skipped = [], 0
    for m in doc.get("messages") or []:
        raw = wda_message_to_raw(m, group_id=group.native_id, group_name=group.name, tz=tz) if isinstance(m, Mapping) else None
        if raw is None:
            skipped += 1
            continue
        msgs.append(raw.model_copy(update={"platform": platform}))
    warnings = [f"有 {skipped} 条消息缺少时间或 ID，已跳过"] if skipped else []
    if conv and not conv.get("isGroup", True):
        warnings.append("这份导出是私聊记录")
    return ParsedImport(group=group, messages=_sorted(msgs), format=fmt, warnings=warnings)


def parse_wda_zip(content: bytes, *, platform: Platform, group_name: str | None, tz: tzinfo) -> list[ParsedImport]:
    out = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile:
        raise ImportFormatError("zip 文件已损坏或不是 zip") from None
    with zf:
        for info in zf.infolist():
            if not info.filename.endswith("messages.json") or info.file_size > MAX_ZIP_MEMBER:
                continue
            try:
                doc = json.loads(zf.read(info).decode("utf-8-sig"))
            except (ValueError, UnicodeDecodeError):
                continue
            if isinstance(doc, Mapping) and "messages" in doc:
                out.append(parse_wda_doc(doc, platform=platform, group_name=group_name, tz=tz, fmt="wda_zip"))
    if not out:
        raise ImportFormatError("zip 里没有找到 WeChatDataAnalysis 导出的 messages.json")
    return out


def parse_weflow_doc(doc: Mapping[str, Any], *, platform: Platform, group_name: str | None,
                     tz: tzinfo) -> ParsedImport:
    sess = doc.get("session") if isinstance(doc.get("session"), Mapping) else {}
    group = _group(platform, as_str(sess.get("accountId")),
                   group_name or as_str(sess.get("displayName")) or as_str(sess.get("nickname")), fallback="WeFlow 导入")
    senders = {}
    for s in doc.get("senders") or []:         # arkme-json：消息里只有 senderID
        if isinstance(s, Mapping):
            senders[s.get("senderID")] = s
    names = {as_str(s.get("accountId")): as_str(s.get("groupNickname")) or as_str(s.get("displayName"))
             for s in senders.values()}
    ids = StableIdMaker()
    msgs = []
    for m in doc.get("messages") or []:
        if not isinstance(m, Mapping):
            continue
        if "senderID" in m and "senderUsername" not in m:
            s = senders.get(m.get("senderID")) or {}
            m = {**m, "senderUsername": s.get("accountId"),
                 "senderDisplayName": as_str(s.get("groupNickname")) or as_str(s.get("displayName"))}
        raw = weflow_message_to_raw(m, group_id=group.native_id, group_name=group.name, tz=tz, names=names, ids=ids)
        if raw:
            msgs.append(raw.model_copy(update={"platform": platform}))
    return ParsedImport(group=group, messages=_sorted(msgs), format="weflow_json")


def parse_chatlab_doc(doc: Mapping[str, Any], *, platform: Platform, group_name: str | None,
                      tz: tzinfo) -> ParsedImport:
    meta = doc.get("meta") if isinstance(doc.get("meta"), Mapping) else {}
    group = _group(platform, as_str(meta.get("groupId")), group_name or as_str(meta.get("name")),
                   fallback="ChatLab 导入")
    members = chatlab_members(doc)
    ids = StableIdMaker()
    msgs = [raw for m in doc.get("messages") or [] if isinstance(m, Mapping)
            and (raw := chatlab_message_to_raw(m, platform=platform, group_id=group.native_id,
                                                group_name=group.name, tz=tz, members=members, ids=ids))]
    warnings = ["这份 ChatLab 记录是私聊"] if as_str(meta.get("type")) == "private" else []
    return ParsedImport(group=group, messages=_sorted(msgs), format="chatlab", warnings=warnings)


def _jsonl_to_chatlab(text: str) -> dict[str, Any] | None:
    doc: dict[str, Any] = {"members": [], "messages": []}
    bad = 0
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#"):
            continue
        try:
            row = json.loads(ln)
        except ValueError:
            bad += 1
            continue
        t = row.get("_type") if isinstance(row, dict) else None
        if t == "header":
            doc["chatlab"], doc["meta"] = row.get("chatlab"), row.get("meta")
        elif t == "member":
            doc["members"].append(row)
        elif t == "message":
            doc["messages"].append(row)
    return doc if ("meta" in doc and doc["messages"]) else None


def sniff_json(doc: Any) -> str | None:
    """判断 JSON 文档属于哪种导出格式。"""
    if isinstance(doc, Mapping):
        if "chatlab" in doc and "messages" in doc:
            return "chatlab"
        if "weflow" in doc and "messages" in doc:
            return "weflow_json"
        if "messages" in doc and ("conversation" in doc or "schemaVersion" in doc):
            return "wda_json"
        first = next((m for m in doc.get("messages") or [] if isinstance(m, Mapping)), None)
        if first is not None:
            if "renderType" in first:
                return "wda_json"
            if "localType" in first or "senderUsername" in first:
                return "weflow_json"
            if "timestamp" in first and "sender" in first:
                return "chatlab"
    return None


# ---------------------------------------------------------------- 入口

def decode_text(content: bytes) -> tuple[str, list[str]]:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16"), []
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return content.decode(enc), ([] if enc == "utf-8-sig" else ["文件不是 UTF-8 编码，已按 GB18030 读取"])
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace"), ["文件编码无法识别，部分字符可能显示为乱码"]


def parse_export_all(content: bytes, *, filename: str | None, platform: Platform | str,
                     group_name: str | None, tz: str = DEFAULT_TZ) -> list[ParsedImport]:
    """解析一份导出内容，返回其中的每个群（CSV / WDA zip 可能包含多个群）。"""
    plat = Platform(platform)
    zone = get_tz(tz)
    ref = datetime.now(zone).date()
    if not content or not content.strip():
        raise ImportFormatError("内容为空")
    if content[:4] == b"PK\x03\x04":
        return parse_wda_zip(content, platform=plat, group_name=group_name, tz=zone)
    text, enc_warn = decode_text(content)
    stripped = text.lstrip()
    results: list[ParsedImport] | None = None
    if (filename or "").lower().endswith(".jsonl") or re.search(r'^\s*\{"_type"\s*:', text, re.M):
        jdoc = _jsonl_to_chatlab(text)          # ChatLab JSONL（允许 # 开头的注释行）
        if jdoc is not None:
            results = [parse_chatlab_doc(jdoc, platform=plat, group_name=group_name, tz=zone)]
    if results is None and stripped[:1] in ("{", "["):
        doc: Any = None
        try:
            doc = json.loads(stripped)
        except ValueError:
            doc = _jsonl_to_chatlab(stripped)
        if isinstance(doc, list):
            doc = {"messages": doc}
        kind = sniff_json(doc)
        if kind == "chatlab":
            results = [parse_chatlab_doc(doc, platform=plat, group_name=group_name, tz=zone)]
        elif kind == "weflow_json":
            results = [parse_weflow_doc(doc, platform=plat, group_name=group_name, tz=zone)]
        elif kind == "wda_json":
            results = [parse_wda_doc(doc, platform=plat, group_name=group_name, tz=zone)]
        elif doc is not None and not (filename or "").lower().endswith((".txt", ".md", ".log")):
            raise ImportFormatError("这份 JSON 不是已知的聊天导出格式。" + SUPPORTED_HINT)
    if results is None and ((filename or "").lower().endswith((".csv", ".tsv")) or looks_like_csv(text)):
        results = parse_csv_rows(text, platform=plat, group_name=group_name, filename=filename, tz=zone, ref=ref)
    if results is None:
        gname = group_name or (PurePath(filename).stem if filename else None)
        results = [parse_pasted_text(text, platform=plat, group_name=gname, tz=zone, ref=ref)]
    for r in results:
        r.warnings[:0] = enc_warn
    return results


def parse_export(content: bytes, *, filename: str | None, platform: Platform,
                 group_name: str | None, tz: str = "Asia/Shanghai") -> ParsedImport:
    """解析导出文件或粘贴文本（签名见 ARCHITECTURE §5）。内容包含多个群时返回消息最多的那个并给出提示。"""
    results = parse_export_all(content, filename=filename, platform=platform, group_name=group_name, tz=tz)
    if len(results) == 1:
        return results[0]
    best = max(results, key=lambda r: len(r.messages))
    others = "、".join(r.group.name for r in results if r is not best)[:200]
    best.warnings.append(f"文件里有 {len(results)} 个群，本次只导入消息最多的「{best.group.name}」；"
                         f"其余（{others}）请分别导入，或放进 data/inbox 让定时任务处理")
    return best