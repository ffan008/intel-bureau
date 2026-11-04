"""演示数据生成器：9 个群 × 7 天，固定随机种子；同一 anchor 与 scale 生成的数据完全一致。"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

from bureau.contracts import Attachment, GroupInfo, MessageKind, Platform, RawMessage
from bureau.demo import noise
from bureau.demo.model import DEMO_GROUPS, GROUP_BY_SHORT, SEED, DemoGroup, T
from bureau.demo.people import FEISHU_NAMES, NICKNAMES
from bureau.demo.threads_biz import BIZ_THREADS
from bureau.demo.threads_create import CREATE_THREADS
from bureau.demo.threads_tech import TECH_THREADS
from bureau.demo.threads_v2 import V2_THREADS
from bureau.demo.media import fetch_desc

ALL_THREADS: list[T] = [*CREATE_THREADS, *TECH_THREADS, *BIZ_THREADS, *V2_THREADS]

# 24 小时活跃度（昼夜节律）
PROFILES: dict[Platform, list[float]] = {
    Platform.WECHAT: [3, 1.5, .8, .4, .3, .4, 1, 2.5, 5, 6, 6.5, 6, 7, 5.5, 5, 5, 5, 5.5, 6, 7, 8.5, 9.5, 9, 6],
    Platform.QQ: [5, 3.5, 2, 1, .5, .4, .6, 1.5, 3, 4, 4.5, 5, 6, 5, 4.5, 4.5, 5, 5, 6, 7, 8.5, 10, 10, 8],
    Platform.FEISHU: [.3, .1, .1, .1, .1, .2, .5, 1.5, 4, 9, 10, 9, 4, 6, 9, 10, 9.5, 8, 5, 3, 2, 1.5, 1, .5],
}
BASE_PER_DAY = 150


@dataclass
class _Draft:
    group: DemoGroup
    ts: datetime
    sender: str
    kind: MessageKind
    text: str
    uid: int
    reply_uid: int | None = None
    want_reply: bool = False
    attachments: list[Attachment] = field(default_factory=list)


@dataclass
class GeneratedDemo:
    anchor: datetime
    groups: list[GroupInfo]
    messages: list[RawMessage]
    family_days: dict[str, list[tuple[int, list[str]]]]   # family -> [(day, 线程文本)]


class _Gen:
    def __init__(self, anchor: datetime, scale: float, media_dir: str = "") -> None:
        self.anchor = anchor
        self.scale = scale
        self.media_dir = media_dir
        self.rng = random.Random(SEED)
        self.drafts: list[_Draft] = []
        self.uid = 0
        self.family_days: dict[str, list[tuple[int, list[str]]]] = {}
        self.members: dict[str, list[str]] = {}
        for g in DEMO_GROUPS:
            pool = FEISHU_NAMES if g.platform is Platform.FEISHU else NICKNAMES
            k = min(len(pool), 16 + int(g.activity * 14)) if g.platform is not Platform.FEISHU else min(len(pool), 12 + int(g.activity * 6))
            self.members[g.short] = self.rng.sample(pool, k)

    # ---------- 工具 ----------
    def day_window(self, day: int) -> tuple[datetime, datetime]:
        end = self.anchor + timedelta(days=day)
        return end - timedelta(hours=24), end

    def sample_time(self, g: DemoGroup, start: datetime, end: datetime) -> datetime:
        prof = PROFILES[g.platform]
        peak = max(prof)
        span = (end - start).total_seconds()
        while True:
            ts = start + timedelta(seconds=self.rng.random() * span)
            if self.rng.random() * peak <= prof[ts.hour]:
                return ts.replace(microsecond=0)

    def sender(self, g: DemoGroup) -> str:
        m = self.members[g.short]
        weights = [1 / (i + 1) ** 0.8 for i in range(len(m))]
        return self.rng.choices(m, weights)[0]

    def add(self, g: DemoGroup, ts: datetime, sender: str, kind: MessageKind, text: str, **kw: object) -> _Draft:
        self.uid += 1
        d = _Draft(group=g, ts=ts, sender=sender, kind=kind, text=text, uid=self.uid, **kw)  # type: ignore[arg-type]
        self.drafts.append(d)
        return d

    # ---------- 线程 ----------
    def thread_start(self, t: T, g: DemoGroup, day: int, total: timedelta) -> datetime:
        start, end = self.day_window(day)
        latest = end - total - timedelta(minutes=2)
        if t.hours:
            h0, h1 = t.hours
            spans = []
            for base in {start.date(), end.date()}:
                a = start.replace(year=base.year, month=base.month, day=base.day, hour=h0, minute=0, second=0)
                b = a.replace(hour=h1)
                a, b = max(a, start), min(b, latest)
                if b > a:
                    spans.append((a, b))
            if spans:
                spans.sort()
                a, b = self.rng.choice(spans)
                return (a + timedelta(seconds=self.rng.random() * (b - a).total_seconds())).replace(microsecond=0)
        ts = self.sample_time(g, start, end)
        return min(ts, latest)

    def emit_thread(self, t: T, g: DemoGroup, day: int) -> None:
        gaps = [timedelta(seconds=int(self.rng.uniform(25, 330))) for _ in t.lines[1:]]
        ts = self.thread_start(t, g, day, sum(gaps, timedelta()))
        roles = sorted({ln.role for ln in t.lines})
        people = dict(zip(roles, self.rng.sample(self.members[g.short], len(roles))))
        made: list[_Draft] = []
        for i, ln in enumerate(t.lines):
            if i:
                ts = ts + gaps[i - 1]
            kind, text, atts = MessageKind.TEXT, ln.text, []
            if ln.kind in ("image", "file") and ln.media:          # v2：演示图片和文档（本地素材）
                extra = {"fetch": fetch_desc(self.media_dir, ln.media), "demo_media": ln.media}
                if ln.kind == "image":
                    kind, text = MessageKind.IMAGE, "[图片]"
                    atts = [Attachment(kind="image", extra=extra)]
                else:
                    kind, text = MessageKind.FILE, f"[文件] {ln.media}"
                    atts = [Attachment(kind="file", title=ln.media, extra=extra)]
            elif ln.kind == "link":
                url = ln.url or ln.text
                kind, text = MessageKind.LINK, f"[链接] {ln.title or url}"
                atts = [Attachment(kind="link", title=ln.title, url=url)]
            elif ln.text.startswith("[文件]"):
                kind = MessageKind.FILE
                atts = [Attachment(kind="file", title=ln.text.removeprefix("[文件]").strip())]
            reply_uid = None
            if ln.reply is not None and ln.reply < len(made):
                reply_uid = made[ln.reply].uid
                if kind is MessageKind.TEXT:
                    kind = MessageKind.REPLY
            made.append(self.add(g, ts, people[ln.role], kind, text, reply_uid=reply_uid, attachments=atts))
        self.family_days.setdefault(t.family, []).append((day, [ln.text for ln in t.lines]))
        for short in t.forward:
            tg = GROUP_BY_SHORT[short]
            fts = made[0].ts + timedelta(minutes=self.rng.randint(6, 45))
            _, end = self.day_window(day)
            if fts < end:
                self.add(tg, fts, self.sender(tg), MessageKind.TEXT, t.lines[0].text)

    # ---------- 噪声 ----------
    def emit_noise(self, g: DemoGroup, day: int) -> None:
        start, end = self.day_window(day)
        mid = start + timedelta(hours=12)
        weekend = mid.weekday() >= 5
        factor = (0.25 if g.platform is Platform.FEISHU else 1.15) if weekend else 1.0
        n = int(BASE_PER_DAY * g.activity * self.scale * factor * self.rng.uniform(0.8, 1.2))
        for _ in range(n):
            ts = self.sample_time(g, start, end)
            who = self.sender(g)
            r = self.rng.random()
            if r < 0.30:
                self.add(g, ts, who, MessageKind.TEXT, self.rng.choice(noise.LOW_INFO))
            elif r < 0.38:
                self.add(g, ts, who, MessageKind.STICKER, "[动画表情]")
            elif r < 0.48:
                self.add(g, ts, who, MessageKind.IMAGE, "[图片]", attachments=[Attachment(kind="image")])
            elif r < 0.51:
                other = self.rng.choice(NICKNAMES)
                self.add(g, ts, "系统", MessageKind.SYSTEM, noise.SYSTEM_JOIN.format(a=who, b=other))
            elif r < 0.53:
                self.add(g, ts, "系统", MessageKind.SYSTEM, noise.SYSTEM_PAT.format(a=who, b=self.sender(g)))
            elif r < 0.55:
                self.add(g, ts, "系统", MessageKind.RECALL, noise.SYSTEM_RECALL.format(a=who))
            elif r < 0.57:
                self.add(g, ts, who, MessageKind.REDPACKET, noise.REDPACKET)
            elif r < 0.58:
                self.add(g, ts, who, MessageKind.VOICE, f"[语音] {self.rng.randint(3, 50)}″",
                         attachments=[Attachment(kind="voice")])
            else:
                tools = list(g.tools)
                tool = self.rng.choice(tools)
                tool2 = self.rng.choice([x for x in tools if x != tool] or tools)
                text = self.rng.choice(noise.CHAT_TEMPLATES).format(
                    tool=tool, tool2=tool2, topic=self.rng.choice(g.topics), n=self.rng.randint(8, 10))
                self.add(g, ts, who, MessageKind.TEXT, text, want_reply=self.rng.random() < 0.08)

    def emit_surge(self) -> None:
        used: set[str] = set()
        for short in noise.SURGE_GROUPS:
            g = GROUP_BY_SHORT[short]
            start, end = self.day_window(0)
            for _ in range(self.rng.randint(5, 8)):
                for _attempt in range(20):
                    text = self.rng.choice(noise.SURGE_PREFIX) + self.rng.choice(noise.SURGE_CORE)
                    if text not in used:
                        used.add(text)
                        break
                self.add(g, self.sample_time(g, start + timedelta(hours=6), end), self.sender(g), MessageKind.TEXT, text)
        for i, day in enumerate((-4, -3, -2, -1)):
            g = GROUP_BY_SHORT["qq_manju" if i % 2 else "wx_shouhui8"]
            start, end = self.day_window(day)
            self.add(g, self.sample_time(g, start, end), self.sender(g), MessageKind.TEXT, noise.PRE_SURGE[i])

    # ---------- 组装 ----------
    def build(self) -> GeneratedDemo:
        for t in ALL_THREADS:
            for day in t.days:
                for short in t.groups:
                    self.emit_thread(t, GROUP_BY_SHORT[short], day)
        for g in DEMO_GROUPS:
            for day in range(-6, 1):
                self.emit_noise(g, day)
        self.emit_surge()
        lo = self.anchor - timedelta(days=7)
        drafts = [d for d in self.drafts if lo <= d.ts < self.anchor]
        native: dict[int, str] = {}
        messages: list[RawMessage] = []
        by_uid = {d.uid: d for d in drafts}
        for g in DEMO_GROUPS:
            mine = sorted((d for d in drafts if d.group.short == g.short), key=lambda d: (d.ts, d.uid))
            for seq, d in enumerate(mine):
                native[d.uid] = f"{g.short}-{seq:05d}"
            for idx, d in enumerate(mine):
                if d.want_reply and idx > 3:
                    cand = [x for x in mine[max(0, idx - 15):idx] if x.kind in (MessageKind.TEXT, MessageKind.REPLY)
                            and len(x.text) >= 8]
                    if cand:
                        d.reply_uid = self.rng.choice(cand).uid
                        d.kind = MessageKind.REPLY
        for d in sorted(drafts, key=lambda d: (d.ts, d.uid)):
            target = by_uid.get(d.reply_uid) if d.reply_uid else None
            messages.append(RawMessage(
                platform=d.group.platform, group_native_id=d.group.native_id, group_name=d.group.name,
                native_id=native[d.uid], sender_id=f"u-{abs(hash_name(d.sender)) % 10_000_000}", sender_name=d.sender,
                sent_at=d.ts, kind=d.kind, text=d.text, attachments=d.attachments,
                reply_to=native.get(target.uid) if target else None,
                quote_text=target.text[:30] if target else None,
            ))
        groups = [GroupInfo(platform=g.platform, native_id=g.native_id, name=g.name, member_count=g.members,
                            extra={"demo": True}) for g in DEMO_GROUPS]
        return GeneratedDemo(anchor=self.anchor, groups=groups, messages=messages, family_days=self.family_days)


def hash_name(name: str) -> int:
    """稳定的字符串哈希（不受 PYTHONHASHSEED 影响）。"""
    h = 2166136261
    for ch in name.encode("utf-8"):
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h


@lru_cache(maxsize=4)
def generate(anchor: datetime, scale: float = 1.0, media_dir: str = "") -> GeneratedDemo:
    """media_dir：演示素材目录（data_dir/demo_media），写进附件的 extra.fetch.path。"""
    return _Gen(anchor, float(scale), str(media_dir or "")).build()
