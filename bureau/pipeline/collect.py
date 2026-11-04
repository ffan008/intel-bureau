"""阶段 1 collect：按任务的平台与群范围调用采集器（每平台 1~2 并发），再合并实时上报已入库的消息。"""

from __future__ import annotations

import asyncio
from collections import Counter
from datetime import timedelta
from typing import Any

from bureau.collectors import CollectorUnavailable, create_collector
from bureau.collectors.base import CollectorContext
from bureau.contracts import GroupInfo, Platform
from bureau.core.platforms import create_collector as create_platform_collector
from bureau.core.timeutil import iso, parse_iso
from bureau.pipeline.models import RunContext, StageResult, StopPipeline


def _info(g: dict[str, Any]) -> GroupInfo:
    return GroupInfo(platform=Platform(g["platform"]), native_id=g["native_id"], name=g.get("name") or g["native_id"],
                     member_count=g.get("member_count"), extra=g.get("extra") or {})


async def _fetch_group(rc: RunContext, collector: Any, g: dict[str, Any], sem: asyncio.Semaphore) -> int:
    store = rc.app.store
    since = rc.start
    cur = store.get_cursor(g["key"])
    # 手动运行按指定窗口完整重拉（不走游标），已入库的消息靠去重跳过，同时能补上 v2 的附件取回信息
    use_cursor = bool(cur and cur.get("last_ts")) and not rc.demo and rc.trigger != "manual"
    if use_cursor:
        last = parse_iso(cur["last_ts"], rc.tz)
        if last and rc.start < last < rc.end:
            since = max(rc.start, last - timedelta(minutes=5))       # 留 5 分钟重叠，靠去重兜底
    async with sem:
        res = await collector.fetch_messages(_info(g), since, rc.end,
                                             cursor=(cur or {}).get("collector_cursor") if use_cursor else None,
                                             limit=int(rc.cfg("sources.collect.per_group_limit", 5000)))
    inserted, _ = await asyncio.to_thread(store.insert_messages, res.messages, source="collect")
    last_msg = res.messages[-1] if res.messages else None
    store.set_cursor(g["key"], last_ts=iso(rc.end), last_native_id=last_msg.native_id if last_msg else None,
                     collector_cursor=res.next_cursor)
    store.touch_group_collected(g["key"], store.now_iso())
    if not res.complete or res.warnings:
        rc.log.warn("SCOUT", f"群「{g['name']}」只拿到部分消息：{'；'.join(res.warnings) or '达到上限'}", "collect")
    return inserted


async def _collect_platform(rc: RunContext, platform: str, groups: list[dict[str, Any]], collector: Any) -> dict[str, int]:
    sem = asyncio.Semaphore(max(1, min(2, int(rc.cfg("sources.collect.concurrency_per_platform", 2)))))
    out = {"inserted": 0, "failed": 0}

    async def one(g: dict[str, Any]) -> None:
        try:
            # 必须先把 await 的结果落到局部变量再累加：写成 out["inserted"] += await ... 时，
            # 旧值在挂起前就被读出，并发跑的其它群会把结果互相覆盖（最后只剩一个群的值，常常是 0）。
            n = await _fetch_group(rc, collector, g, sem)
            out["inserted"] += n
            rc.log.info("SCOUT", f"已采集群「{g['name']}」", "collect")
        except Exception as exc:                                     # noqa: BLE001  单群失败不中断
            out["failed"] += 1
            rc.failed_groups.append(g["key"])
            rc.log.warn("SCOUT", f"群「{g['name']}」采集失败：{exc}", "collect")

    try:
        await asyncio.gather(*(one(g) for g in groups))
    finally:
        try:
            await collector.aclose()
        except Exception:                                            # noqa: BLE001
            pass
    return out


async def _demo_groups(rc: RunContext) -> tuple[list[dict[str, Any]], Any]:
    from bureau.demo import current_anchor, current_scale, seed_demo

    app = rc.app
    if current_anchor(app) is None:
        rc.log.info("SCOUT", "还没有演示数据，先生成 9 个群 × 7 天的合成消息", "collect")
        await asyncio.to_thread(seed_demo, app, reset=False)
    settings = {"anchor": app.store.kv_get("demo.anchor"), "scale": current_scale(app),
                "media_dir": str(app.paths.demo_media)}
    collector = create_collector("demo.synthetic", CollectorContext(platform=Platform.DEMO, settings=settings,
                                                                    secrets={}, data_dir=app.paths.data, tz=app.tz))
    for gi in await collector.list_groups():
        existing = app.store.get_group(gi.key)
        app.store.upsert_group(gi, is_demo=True, whitelisted=True if existing is None else None)
    groups = app.store.whitelisted_groups(platforms=rc.platforms or None, keys=rc.group_keys or None, is_demo=True)
    return groups, collector


async def run(rc: RunContext) -> StageResult:
    app = rc.app
    per_platform: Counter[str] = Counter()
    unavailable: list[str] = []
    inserted = 0
    if rc.demo:
        groups, collector = await _demo_groups(rc)
        by_p: dict[str, list[dict[str, Any]]] = {}
        for g in groups:
            by_p.setdefault(g["platform"], []).append(g)
        results = await asyncio.gather(*(_collect_platform(rc, p, gs, collector) for p, gs in by_p.items()))
        inserted = sum(r["inserted"] for r in results)
    else:
        groups = app.store.whitelisted_groups(platforms=rc.platforms or None, keys=rc.group_keys or None, is_demo=False)
        tasks = []
        by_p = {}
        for g in groups:
            by_p.setdefault(g["platform"], []).append(g)
        for p, gs in by_p.items():
            if not app.config.get(f"sources.{p}.enabled", False):
                rc.log.info("SCOUT", f"{p} 采集未启用，只使用已入库的消息（导入 / 实时上报）", "collect")
                continue
            adapter = app.config.get(f"sources.{p}.adapter")
            try:
                collector = create_platform_collector(app, p, adapter)
            except CollectorUnavailable as exc:
                unavailable.append(p)
                rc.log.warn("SCOUT", f"{exc}；该平台只使用已入库的消息", "collect")
                continue
            tasks.append(_collect_platform(rc, p, gs, collector))
        results = await asyncio.gather(*tasks)
        inserted = sum(r["inserted"] for r in results)
    rc.groups = groups
    keys = [g["key"] for g in groups]
    rc.raw = await asyncio.to_thread(app.store.messages_in_window, keys, rc.start, rc.end)
    for m in rc.raw:
        per_platform[m["platform"]] += 1
    metrics: dict[str, Any] = {"groups": len(groups), "messages": len(rc.raw), "inserted": inserted,
                               "failed_groups": len(rc.failed_groups)}
    for p, n in per_platform.items():
        metrics[f"msgs_{p}"] = n
    if unavailable:
        metrics["unavailable"] = ",".join(unavailable)
    rc.totals["messages_raw"] = len(rc.raw)
    rc.log.info("SCOUT", f"采集完成：{len(groups)} 个群，窗口内 {len(rc.raw):,} 条消息（新入库 {inserted:,} 条）", "collect")
    if not groups:
        raise StopPipeline("没有白名单群；请先在「情报源」页面把群加入白名单，或运行演示模式")
    if not rc.raw:
        raise StopPipeline("窗口内没有消息")
    return StageResult(metrics=metrics, message=f"{len(groups)} 个群 · {len(rc.raw):,} 条")
