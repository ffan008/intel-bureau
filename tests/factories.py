"""测试数据构造。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from bureau.core.timeutil import epoch
from bureau.pipeline.models import Candidate, CleanMsg, Item

TZ = ZoneInfo("Asia/Shanghai")
T0 = datetime(2026, 10, 28, 10, 0, tzinfo=TZ)


def row(i: int, text: str, *, group: str = "qq:g1", kind: str = "text", sender: str | None = None,
        minutes: float | None = None, reply_to: str | None = None, attachments: list[dict[str, Any]] | None = None,
        platform: str | None = None) -> dict[str, Any]:
    ts = T0 + timedelta(minutes=minutes if minutes is not None else i)
    return {"id": i, "group_key": group, "group_name": f"群{group[-1]}", "platform": platform or group.split(":")[0],
            "native_id": f"n{i}", "sender_name": sender or f"用户{i % 4}", "sent_at": ts.isoformat(), "ts": epoch(ts),
            "kind": kind, "text": text, "reply_to": reply_to, "attachments": attachments or [], "group_weight": 1.0}


def msg(i: int, text: str, *, group: str = "qq:g1", sender: str | None = None, minutes: float | None = None,
        reply_ref: str | None = None, urls: list[str] | None = None) -> CleanMsg:
    ts = T0 + timedelta(minutes=minutes if minutes is not None else i)
    return CleanMsg(id=i, ref=f"m{i}", group_key=group, group_name=f"群{group[-1]}", platform=group.split(":")[0],
                    native_id=f"n{i}", sender=sender or f"用户{i % 4}", sent_at=ts.isoformat(), ts=epoch(ts), kind="text",
                    text=text, urls=urls or [], reply_ref=reply_ref)


def cand(title: str, *, tags: list[str] | None = None, links: list[str] | None = None, evidence: list[dict] | None = None,
         refs: list[str] | None = None, group: str = "qq:g1", scores: dict | None = None,
         risks: list[str] | None = None) -> Candidate:
    return Candidate(chunk_id="c1", group_key=group, title=title, hook=title, summary=title, category="99 其他",
                     kind="观点判断", steps=[], tools=[], links=[{"url": u, "title": ""} for u in links or []],
                     evidence=evidence or [], participants=["用户1"],
                     scores=scores or {"novelty": 3, "actionability": 3, "credibility": 3},
                     risk_flags=risks or [], tags=tags or [], refs=refs or [])


def item(title: str = "测试情报", **kw: Any) -> Item:
    base: dict[str, Any] = dict(id="i1", title=title, hook=kw.pop("hook", title), summary=kw.pop("summary", title),
                                category="02 提示词与工作流", kind="教程方法", steps=kw.pop("steps", []),
                                tools=kw.pop("tools", []), links=kw.pop("links", []), evidence=kw.pop("evidence", []),
                                participants=["用户1"], llm_scores={"novelty": 3, "actionability": 3, "credibility": 3},
                                risk_flags=kw.pop("risk_flags", []), tags=kw.pop("tags", []))
    it = Item(**base)
    for k, v in kw.items():
        setattr(it, k, v)
    return it
