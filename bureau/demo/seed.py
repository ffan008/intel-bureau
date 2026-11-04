"""写入 / 清除演示数据。"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timedelta
from typing import Any

from bureau.core.nlp import NLP_INSTANCE
from bureau.core.textutil import extract_urls
from bureau.core.timeutil import iso, now, parse_iso
from bureau.demo.generator import GeneratedDemo, generate
from bureau.demo.media import ensure_demo_media
from bureau.demo.model import DEMO_GROUPS, FAMILY_TITLES

log = logging.getLogger("bureau.demo")


def default_anchor(tz: str) -> datetime:
    return now(tz).replace(minute=0, second=0, microsecond=0)


def current_anchor(app: Any) -> datetime | None:
    return parse_iso(app.store.kv_get("demo.anchor"), app.tz)


def current_scale(app: Any) -> float:
    return float(app.store.kv_get("demo.scale", app.config.get("sources.demo.synthetic.scale", 1.0)) or 1.0)


def seed_demo(app: Any, *, reset: bool = True, scale: float | None = None) -> dict[str, int]:
    """写入 9 个群 × 7 天的演示数据。reset=False 且已有演示数据时沿用原来的时间锚点。"""
    anchor = current_anchor(app)
    if reset or anchor is None:
        if anchor is not None:
            clear_demo(app)
        anchor = default_anchor(app.tz)
        scale = float(scale if scale is not None else app.config.get("sources.demo.synthetic.scale", 1.0) or 1.0)
    else:
        scale = current_scale(app)
    # v2：演示图片和文档。getattr 兜底：升级后重启前，正在运行的 v1 服务可能用新的 seed 模块配旧的 Paths
    media_dir = getattr(app.paths, "demo_media", app.paths.data / "demo_media")
    ensure_demo_media(media_dir)
    data = generate(anchor, scale, str(media_dir))
    for g in data.groups:
        app.store.upsert_group(g, is_demo=True, whitelisted=True)
    inserted, _ = app.store.insert_messages(data.messages, source="demo")
    app.store.kv_set("demo.anchor", iso(anchor))
    app.store.kv_set("demo.scale", scale)
    seed_memory(app, data)
    app.overview_cache.clear()
    total = int(app.db.scalar("SELECT COUNT(*) FROM messages m JOIN groups g ON g.key=m.group_key WHERE g.is_demo=1",
                              (), 0))
    log.info("演示数据已写入：%s 个群，新增 %s 条消息（共 %s 条）", len(data.groups), inserted, total)
    return {"groups": len(data.groups), "messages": total, "inserted": inserted}


def seed_memory(app: Any, data: GeneratedDemo) -> None:
    """把窗口之前已经出现过的话题写进 demo 话题记忆，让报告能区分新出现 / 持续发酵 / 重复。"""
    app.store.clear_memory("demo")
    for family, entries in data.family_days.items():
        earlier = sorted((d, texts) for d, texts in entries if d < 0)
        if not earlier:
            continue
        texts = [t for _, ts in earlier for t in ts]
        kws = [w.lower() for w in NLP_INSTANCE.extract_keywords(texts, top_k=24)]
        links = list(dict.fromkeys(u for t in texts for u in extract_urls(t)))
        days = sorted({(data.anchor + timedelta(days=d)).strftime("%Y-%m-%d") for d, _ in earlier})
        title = FAMILY_TITLES.get(family, family)
        hist = [{"day": d, "title": title, "item_id": None} for d in days]
        app.store.memory_insert("demo", title=title, category="", keywords=kws, links=links, day=days[-1],
                                item_id=None, heat=1.0, history=hist, first_seen=days[0])


def clear_demo(app: Any) -> dict[str, int]:
    """删除所有演示群、消息、运行、报告（含 data/reports 下的文件）与 demo 话题记忆。"""
    from pathlib import Path

    reports, _ = app.store.list_reports(limit=10_000, is_demo=True)
    root = app.paths.reports.resolve()
    for r in reports:
        for p in (r.get("files") or {}).values():
            try:
                fp = Path(p)
                if fp.exists() and root in fp.resolve().parents:
                    if fp.suffix == ".html":                   # v2：同目录下的 <report_id>_assets/
                        assets = fp.parent / f"{r['id']}_assets"
                        if assets.is_dir() and root in assets.resolve().parents:
                            shutil.rmtree(assets, ignore_errors=True)
                    fp.unlink()
                    parent = fp.parent
                    if parent != app.paths.reports and not any(parent.iterdir()):
                        shutil.rmtree(parent, ignore_errors=True)
            except OSError as exc:
                log.warning("删除演示报告文件失败：%s", exc)
    n_reports = app.store.delete_demo_reports()
    app.store.delete_demo_runs()
    n_groups = app.store.delete_demo_groups()
    app.store.clear_memory("demo")
    if hasattr(app.store, "kb_clear"):                    # v1 的 Store 没有知识库（升级后重启前）
        app.store.kb_clear("demo")
    for k in ("demo.anchor", "demo.scale"):
        app.store.kv_delete(k)
    app.overview_cache.clear()
    log.info("演示数据已清除：%s 个群，%s 份报告", n_groups, n_reports)
    return {"groups": n_groups, "reports": n_reports}


DEMO_KEYS = [g.key for g in DEMO_GROUPS]
