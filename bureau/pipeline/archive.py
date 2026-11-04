"""阶段 12 archive：写知识库（v2，§3.3）、保存报告，更新 topic_memory 与 keyword_daily，按保留期清理原始消息。

知识库：每篇专题按话题指纹（话题名 / 标题归一化后的哈希）或核心词重叠、共享链接匹配已有条目；
相同话题合并更新（追加「{日期} 更新」、来源合并、记版本），新话题新建。仅预览（dry_run）的运行也写知识库
（知识库是报告存档的一部分，同一天重跑只刷新当天内容），只有话题记忆仍然只在正式运行时更新。
"""

from __future__ import annotations

import asyncio
import hashlib
from datetime import timedelta
from typing import Any

from bureau.core.dto import report_summary_dto
from bureau.core.nlp import overlap
from bureau.core.textutil import norm_url
from bureau.pipeline.merge import norm_topic
from bureau.pipeline.models import RunContext, StageResult
from bureau.pipeline.score import report_day


def fingerprint(topic: str, title: str) -> str:
    base = norm_topic(topic) or norm_topic(title)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:16] if base else ""


def write_kb(rc: RunContext) -> tuple[int, int]:
    store = rc.app.store
    day = report_day(rc)
    report_id = rc.report["id"]
    articles = {a["item_id"]: a for a in (rc.report.get("v2_data") or {}).get("articles", [])}
    claimed: set[str] = set()
    created = merged = 0
    for it in sorted((x for x in rc.items if x.is_feature and x.id in articles), key=lambda x: x.seq):
        a = articles[it.id]
        art = {"title": a["title"], "category": it.category, "tags": list(dict.fromkeys([*it.tags, *it.tools]))[:10],
               "hook": a["hook"], "risk_flags": list(it.risk_flags), "fingerprint": fingerprint(it.topic, a["title"]),
               "keywords": list(it.core)[:40], "links": [x["url"] for x in it.links], "body_md": a["body_md"],
               "sources": a["sources"]}
        kb_id, status = store.kb_upsert(rc.scope, art, day=day, report_id=report_id, claimed=claimed)
        it.kb_id = kb_id
        a["kb_id"] = kb_id
        created += status == "created"
        merged += status == "merged"
    return created, merged


def update_memory(rc: RunContext) -> tuple[int, int]:
    store = rc.app.store
    day = report_day(rc)
    since = (rc.end - timedelta(days=int(rc.cfg("pipeline.memory_days", 14)))).strftime("%Y-%m-%d")
    recent = store.memory_recent(rc.scope, since)
    created = touched = 0
    for it in rc.items:
        kws = list(it.core)[:40]
        links = [norm_url(x["url"]) for x in it.links]
        heat = it.scores.get("heat", 0.0)
        target = it.memory_id
        if target is None:      # 同一天重跑：并入当天已建的话题，避免重复
            same_day = [m for m in recent if m["last_seen"] == day and overlap(set(it.core), set(m["keywords"])) >= 0.6]
            target = same_day[0]["id"] if same_day else None
        if target is not None:
            store.memory_touch(target, title=it.title, keywords=kws, links=links, day=day, item_id=it.id, heat=heat)
            touched += 1
        else:
            store.memory_insert(rc.scope, title=it.title, category=it.category, keywords=kws, links=links, day=day,
                                item_id=it.id, heat=heat)
            created += 1
    return created, touched


async def run(rc: RunContext) -> StageResult:
    app = rc.app
    kb_new = kb_merged = 0
    try:
        kb_new, kb_merged = await asyncio.to_thread(write_kb, rc)
    except Exception as exc:                                         # noqa: BLE001  知识库失败不影响报告归档
        rc.log.warn("COURIER", f"写知识库失败：{exc}", "archive")
    by_item = {it.id: it.kb_id for it in rc.items if it.kb_id}
    for d in rc.report.get("items", []):
        if d["id"] in by_item:
            d["kb_id"] = by_item[d["id"]]
    report = {k: v for k, v in rc.report.items() if k != "items"}
    items = rc.report.get("items", [])
    await asyncio.to_thread(app.store.save_report, report, items)
    app.store.update_run(rc.run_id, report_id=report["id"])
    metrics: dict[str, Any] = {"report_id": report["id"], "items": len(items), "kb_new": kb_new, "kb_merged": kb_merged}
    if rc.dry_run:
        rc.log.info("COURIER", "仅预览：不更新话题记忆", "archive")
        created = touched = 0
    else:
        created, touched = await asyncio.to_thread(update_memory, rc)
    app.store.keyword_daily_upsert(rc.scope, report_day(rc), rc.stats_internal.get("archive_counts", {}),
                                   rc.stats_internal.get("archive_groups", {}))
    purged = 0
    if not rc.demo:
        days = int(rc.cfg("privacy.retention_days", 30) or 30)
        purged = await asyncio.to_thread(app.store.purge_messages_before, rc.end - timedelta(days=max(1, days)))
    metrics.update({"memory_new": created, "memory_updated": touched, "purged": purged})
    app.bus.publish("report.created", report_summary_dto(app.store.get_report(report["id"]) or report,
                                                         app.store.deliveries_for(report["id"])))
    app.bus.publish("overview.dirty", {})
    app.overview_cache.clear()
    rc.log.info("COURIER", f"已归档报告 {report['id']}；知识库 新建 {kb_new} · 合并更新 {kb_merged}；"
                           f"话题记忆 新增 {created} · 更新 {touched}"
                + (f"；按保留期清理 {purged} 条旧消息" if purged else ""), "archive")
    return StageResult(metrics=metrics, message=report["id"])
