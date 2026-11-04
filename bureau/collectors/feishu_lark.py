"""飞书采集器：官方 lark-cli（``@larksuite/cli``）。

输出结构按 lark-cli 1.0.97 内置技能（lark-im、lark-im-chat-messages-list、lark-im-chat-list）和
源码 shortcuts/im/convert_lib/content_convert.go 核实：
- ``im +chat-list --as <id> --page-all`` → data.chats[{chat_id, name, description, owner_id, external,
  chat_status, chat_mode}]（无群时 chats 为 null）。
- ``im +chat-messages-list ... --order asc --page-all --page-limit N --no-reactions`` → data:
  {messages:[{message_id, msg_type, content(已转成可读文本), sender:{id, sender_type, name},
  create_time("YYYY-MM-DD HH:MM"，本机时区，精确到分钟), deleted, updated, mentions:[{key,id,name}],
  reply_to?, thread_id?, thread_replies?[...]}], has_more, page_token}，meta.pagination.complete。
  发送者名优先用 sender.name（服务端 sender_name，无需通讯录权限）。
- ``auth status --json`` → identities.bot/user.{status, available, message, tokenStatus, scope}。
"""

from __future__ import annotations

import math
import re
from datetime import datetime, tzinfo
from typing import Any

from bureau.collectors.base import Collector, CollectorContext
from bureau.core.platform_hints import LARK_CLI_INSTALL
from bureau.contracts import (Attachment, ConfigField, FetchResult, GroupInfo, Health, HealthStatus, MessageKind,
                              Platform, RawMessage)
from bureau.integrations.common import as_str, from_timestamp, get_tz, local_tz
from bureau.integrations.lark_cli import LarkCli, LarkCliError, identity_state

_IMG = re.compile(r"!\[Image\]\(([^)\s]+)\)|\[Image: ([^\]\s]+)\]")
_FILE = re.compile(r'<file key="([^"]*)"(?: name="([^"]*)")?\s*/>')
_FOLDER = re.compile(r'<folder key="([^"]*)"(?: name="([^"]*)")?[^>]*/?>')
_AUDIO = re.compile(r'<audio key="([^"]*)"(?: duration="([^"]*)")?\s*/>|\[Voice(?:: ([^\]]*))?\]')
_VIDEO = re.compile(r'<video key="([^"]*)"(?: name="([^"]*)")?[^>]*/>')
_MEDIA = re.compile(r"\[Media(?:: [^\]]*)?\]")
_AT = re.compile(r'<at user_id="[^"]*">([^<]*)</at>')
_MDLINK = re.compile(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)")
_TAG = re.compile(r"</?[a-zA-Z_][\w:-]*(?:\s+[\w:-]+=\"[^\"]*\")*\s*/?>")
_SIMPLE = {"[Sticker]": "[表情]", "[Video call]": "[视频会议]", "[System message]": "[系统消息]",
           "[Rich text message]": "[富文本]", "[Image]": "[图片]", "[File]": "[文件]", "[Video]": "[视频]",
           "[Folder]": "[文件夹]", "[Chat card]": "[群名片]", "[User card]": "[个人名片]", "[Location]": "[位置]"}
_KIND = {"text": MessageKind.TEXT, "post": MessageKind.TEXT, "image": MessageKind.IMAGE, "file": MessageKind.FILE,
         "folder": MessageKind.FILE, "audio": MessageKind.VOICE, "video": MessageKind.VIDEO,
         "media": MessageKind.VIDEO, "sticker": MessageKind.STICKER, "interactive": MessageKind.CARD,
         "share_chat": MessageKind.CARD, "share_user": MessageKind.CARD, "merge_forward": MessageKind.FORWARD,
         "system": MessageKind.SYSTEM, "hongbao": MessageKind.REDPACKET}
_PREFIX = {"interactive": "[卡片] ", "merge_forward": "[合并转发] ", "vote": "[投票] ", "todo": "[任务] ",
           "share_calendar_event": "[日程] ", "calendar": "[日程] ", "general_calendar": "[日程] "}


def normalize_content(msg_type: str, content: str) -> tuple[str, list[Attachment]]:
    """把 lark-cli 的可读内容（含 ![Image](img_x)、<file .../> 等标记）转成中文占位文本和附件。"""
    atts: list[Attachment] = []
    s = content or ""

    def img(m: re.Match[str]) -> str:
        atts.append(Attachment(kind="image", extra={"image_key": m.group(1) or m.group(2)}))
        return "[图片]"

    def file(m: re.Match[str], folder: bool = False) -> str:
        name = m.group(2) or ""
        atts.append(Attachment(kind="file", title=name or None, extra={"file_key": m.group(1), "folder": folder}))
        return f"[{'文件夹' if folder else '文件'}] {name}".strip()

    def audio(m: re.Match[str]) -> str:
        atts.append(Attachment(kind="voice", extra={"file_key": m.group(1)} if m.group(1) else {}))
        dur = m.group(2) or m.group(3) or ""
        return f"[语音 {dur}]" if dur else "[语音]"

    def video(m: re.Match[str]) -> str:
        atts.append(Attachment(kind="video", title=m.group(2) or None, extra={"file_key": m.group(1)}))
        return "[视频]"

    s = _IMG.sub(img, s)
    s = _FILE.sub(file, s)
    s = _FOLDER.sub(lambda m: file(m, True), s)
    s = _AUDIO.sub(audio, s)
    s = _VIDEO.sub(video, s)
    s = _MEDIA.sub("[视频]", s)
    s = _AT.sub(lambda m: f"@{m.group(1)}", s)
    for m in _MDLINK.finditer(s):
        atts.append(Attachment(kind="link", title=m.group(1), url=m.group(2)))
    s = re.sub(r"\[Location: ([^\]]+)\]", r"[位置] \1", s)
    s = re.sub(r"\[(?:Chat|User) card: ([^\]]+)\]", r"[名片] \1", s)
    for en, cn in _SIMPLE.items():
        s = s.replace(en, cn)
    if msg_type in ("interactive", "merge_forward", "vote", "todo", "share_calendar_event", "calendar",
                    "general_calendar", "hongbao", "folder"):
        s = _TAG.sub(" ", s)
    s = re.sub(r"[ \t]{2,}", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return _PREFIX.get(msg_type, "") + s, atts


def parse_create_time(value: Any, tz: tzinfo) -> datetime | None:
    """lark-cli 的 create_time："YYYY-MM-DD HH:MM[:SS]"（本机时区）或 Unix 时间戳。"""
    s = as_str(value)
    if not s:
        return None
    if s.isdigit():
        return from_timestamp(s, tz)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=tz)
        except ValueError:
            continue
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=tz)


def attach_lark_fetch(atts: list[Attachment], message_id: str) -> None:
    """v2：写入 ``extra.fetch = {"type": "lark", "message_id", "file_key", "resource_type", "identity": "user"}``，
    供 ``lark-cli im +messages-resources-download --as user`` 取回。按该命令的参考文档：图片 img_xxx 用
    ``--type image``；文件、音频、视频的 file_xxx 用 ``--type file``；文件夹不能下载，不写 fetch。"""
    for att in atts:
        extra = att.extra
        if att.kind == "image" and extra.get("image_key"):
            key, rtype = as_str(extra.get("image_key")), "image"
        elif att.kind in ("file", "video", "voice") and extra.get("file_key") and not extra.get("folder"):
            key, rtype = as_str(extra.get("file_key")), "file"
        else:
            continue
        if key:
            extra["fetch"] = {"type": "lark", "message_id": message_id, "file_key": key, "resource_type": rtype,
                              "identity": "user"}


def lark_message_to_raw(m: dict[str, Any], *, group: GroupInfo, tz: tzinfo,
                        parent_id: str | None = None) -> RawMessage | None:
    mid = as_str(m.get("message_id"))
    sent_at = parse_create_time(m.get("create_time"), tz)
    if not mid or sent_at is None:
        return None
    msg_type = as_str(m.get("msg_type")) or "text"
    sender = m.get("sender") if isinstance(m.get("sender"), dict) else {}
    sid = as_str(sender.get("id")) or None
    is_bot = as_str(sender.get("sender_type")) == "app"
    name = as_str(sender.get("name")) or ("机器人" if is_bot else "") or sid or ("系统" if msg_type == "system" else "未知成员")
    text, atts = normalize_content(msg_type, as_str(m.get("content")))
    kind = _KIND.get(msg_type, MessageKind.OTHER)
    if m.get("deleted"):
        kind, text, atts = MessageKind.RECALL, "[已撤回]", []
    reply_to = as_str(m.get("reply_to")) or parent_id or None
    if reply_to and kind is MessageKind.TEXT:
        kind = MessageKind.REPLY
    if kind is MessageKind.TEXT and re.fullmatch(r"\s*(https?://\S+|\[[^\]\n]+\]\(https?://[^\s)]+\))\s*", text):
        kind = MessageKind.LINK          # 只发了一个链接
    mentions = [as_str(x.get("id")) or as_str(x.get("name")) for x in m.get("mentions") or []
                if isinstance(x, dict) and (x.get("id") or x.get("name"))]
    attach_lark_fetch(atts, mid)
    raw = {k: m[k] for k in ("msg_type", "thread_id") if m.get(k)}
    return RawMessage(platform=Platform.FEISHU, group_native_id=group.native_id, group_name=group.name,
                      native_id=mid, sender_id=sid, sender_name=name, sent_at=sent_at, kind=kind,
                      text=text or f"[{msg_type}]", reply_to=reply_to, mentions=mentions, attachments=atts,
                      raw=raw or None)


class LarkCliCollector(Collector):
    key = "feishu.lark_cli"
    label = "飞书官方 lark-cli"
    platforms = (Platform.FEISHU,)
    supports_realtime = False

    def __init__(self, ctx: CollectorContext, *, cli: LarkCli | None = None) -> None:
        super().__init__(ctx)
        s = ctx.settings or {}
        self.identity = as_str(s.get("identity")) or "user"
        if self.identity not in ("user", "bot"):
            self.identity = "user"
        try:
            self.timeout = float(s.get("timeout_sec") or 120)
        except (TypeError, ValueError):
            self.timeout = 120.0
        cli_tz = as_str(s.get("cli_timezone"))
        self.cli_tz = get_tz(cli_tz) if cli_tz else local_tz()
        self.cli = cli or LarkCli(cli_path=as_str(s.get("cli_path")) or None, timeout=self.timeout)

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [
            ConfigField(key="identity", label="读取身份", type="select", default="user",
                        options=[{"value": "user", "label": "用户身份（推荐，能读你所在的全部群）"},
                                 {"value": "bot", "label": "机器人身份（只能读机器人所在的群）"}],
                        help="用户身份需要先在终端运行 lark-cli auth login 授权"),
            ConfigField(key="cli_path", label="lark-cli 路径", placeholder="留空自动查找",
                        help="自动查找顺序：PATH → third_party/tools/lark-cli → WorkBuddy 自带"),
            ConfigField(key="timeout_sec", label="单次命令超时（秒）", type="number", default=120),
        ]

    def _cli_missing(self) -> HealthStatus:
        note = "；".join(self.cli.notes)
        return HealthStatus(ok=False, state=Health.UNCONFIGURED, detail="没有找到 lark-cli" + (f"（{note}）" if note else ""),
                            hint=f"{LARK_CLI_INSTALL}，或在设置里填写 lark-cli 路径")

    async def _bot_chat_count(self) -> int:
        data = await self.cli.run(["im", "+chat-list", "--as", "bot", "--page-size", "100", "--format", "json"],
                                  timeout=8.0, identity="bot")
        return len((data or {}).get("chats") or [])


    async def health(self) -> HealthStatus:
        if not self.cli.available:
            return self._cli_missing()
        try:
            status = await self.cli.auth_status(timeout=4.0)
        except LarkCliError as exc:
            return HealthStatus(ok=False, state=Health.DOWN, detail=exc.message, hint=exc.hint)
        data: dict[str, Any] = {"cli_path": self.cli.path, "app_id": status.get("appId"), "identity": self.identity}
        user, bot = identity_state(status, "user"), identity_state(status, "bot")
        data.update({"user_ready": user.available, "bot_ready": bot.available})
        if self.identity == "user":
            if user.available:
                missing = {"im:chat:read", "im:message.group_msg:get_as_user"} - user.scopes if user.scopes else set()
                if missing:
                    return HealthStatus(ok=False, state=Health.DEGRADED, data=data,
                                        detail=f"用户身份可用，但缺少权限：{'、'.join(sorted(missing))}",
                                        hint="在终端运行 `lark-cli auth login --domain im` 补充授权")
                note = "，令牌已到期，读取时会自动刷新" if user.stale else ""
                return HealthStatus(ok=True, state=Health.OK, data=data,
                                    detail=f"lark-cli 用户身份可用（{user.user_name or '已登录'}）{note}")
            alt = "；也可以在设置里改用机器人身份" if bot.available else ""
            return HealthStatus(ok=False, state=Health.DOWN, data=data, detail=f"lark-cli {user.detail}",
                                hint=f"在终端运行 `lark-cli auth login` 重新授权{alt}")
        if not bot.available:
            return HealthStatus(ok=False, state=Health.DOWN, data=data, detail=f"lark-cli {bot.detail}",
                                hint="运行 `lark-cli config init` 检查应用配置，或改用用户身份")
        try:
            count = await self._bot_chat_count()
        except LarkCliError as exc:
            return HealthStatus(ok=False, state=Health.DEGRADED, data=data,
                                detail=f"机器人身份可用，但读取群列表失败：{exc.message}", hint=exc.hint)
        data["bot_chats"] = count
        if count == 0:
            return HealthStatus(ok=False, state=Health.DEGRADED, data=data,
                                detail="机器人身份可用，但机器人不在任何群里",
                                hint="把机器人拉进要监控的群，或改用用户身份")
        note = "，令牌已到期，读取时会自动刷新" if bot.stale else ""
        return HealthStatus(ok=True, state=Health.OK, data=data,
                            detail=f"lark-cli 机器人身份可用，机器人在 {count} 个群里{note}")

    async def list_groups(self) -> list[GroupInfo]:
        if not self.cli.available:
            raise RuntimeError(f"没有找到 lark-cli（{LARK_CLI_INSTALL}）")
        try:
            data = await self.cli.run(["im", "+chat-list", "--as", self.identity, "--page-all", "--page-limit", "50",
                                       "--format", "json"], identity=self.identity)
        except LarkCliError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None
        out = []
        for c in (data or {}).get("chats") or []:
            cid = as_str(c.get("chat_id"))
            if not cid or as_str(c.get("chat_status")) in ("dissolved", "dissolved_save"):
                continue
            out.append(GroupInfo(platform=Platform.FEISHU, native_id=cid, name=as_str(c.get("name")) or cid,
                                 extra={k: c[k] for k in ("chat_mode", "external", "description") if c.get(k) not in (None, "")}))
        return out


    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        if not self.cli.available:
            raise RuntimeError("没有找到 lark-cli（运行 scripts\\tools\\get-lark-cli.ps1 安装）")
        pages = max(1, min(math.ceil(limit / 50), 1000))
        args = ["im", "+chat-messages-list", "--chat-id", group.native_id,
                "--start", since.isoformat(timespec="seconds"), "--end", until.isoformat(timespec="seconds"),
                "--order", "asc", "--page-size", "50", "--page-all", "--page-limit", str(pages),
                "--no-reactions", "--as", self.identity, "--format", "json"]
        if cursor:
            args += ["--page-token", cursor]
        try:
            data = await self.cli.run(args, timeout=max(self.timeout, 30.0 + pages * 3.0), identity=self.identity)
        except LarkCliError as exc:
            raise RuntimeError(exc.message + (f"（{exc.hint}）" if exc.hint else "")) from None
        data = data or {}
        # lark-cli 的 create_time 只精确到分钟：下界按分钟取整，避免丢掉窗口起点所在那一分钟的消息
        lo = since.astimezone(self.cli_tz).replace(second=0, microsecond=0)
        hi = until
        msgs: list[RawMessage] = []
        for m in data.get("messages") or []:
            if not isinstance(m, dict):
                continue
            items = [(m, None)] + [(r, as_str(m.get("message_id"))) for r in m.get("thread_replies") or []
                                   if isinstance(r, dict)]
            for item, parent in items:
                raw = lark_message_to_raw(item, group=group, tz=self.cli_tz, parent_id=parent)
                if raw and lo <= raw.sent_at < hi:
                    msgs.append(raw)
        uniq = {m.native_id: m for m in msgs}
        out = sorted(uniq.values(), key=lambda r: (r.sent_at, r.native_id))
        complete = not data.get("has_more")
        warnings = [] if complete else [f"消息较多，本次只取回前 {len(out)} 条，下次运行会继续"]
        if len(out) > limit:
            out, complete = out[:limit], False
        return FetchResult(messages=out, complete=complete, warnings=warnings,
                           next_cursor=(as_str(data.get("page_token")) or None) if not complete else None)