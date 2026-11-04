"""大屏数据 /api/overview。没有数据时返回结构完整的空数据；演示模式只看演示群，实时模式只看真实群。"""

from __future__ import annotations

import asyncio
import threading
from datetime import timedelta
from typing import Any

from bureau.core.constants import AGENTS, LIVE_PLATFORMS
from bureau.core.dto import empty_stats, report_summary_dto, run_dto
from bureau.core.platforms import platform_dto
from bureau.core.textutil import fmt_int
from bureau.core.timeutil import iso
from bureau.llm.factory import llm_status
from bureau.pipeline.clean import clean_rows
from bureau.pipeline.stats import stats_for

_LOCK = threading.Lock()


def live_stats(app: Any, keys: list[str], end: Any, scope: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """窗口统计（带缓存：群集合 + 窗口终点 + 消息数 + 最大 id 不变就复用）。"""
    start = end - timedelta(hours=24)
    if not keys:
        return empty_stats(), {}
    q = ",".join("?" * len(keys))
    sig = app.db.query_one(f"SELECT COUNT(*) AS n, MAX(id) AS mx FROM messages WHERE group_key IN ({q}) AND ts>=? AND ts<?",
                           [*keys, int(start.timestamp()), int(end.timestamp())]) or {}
    ck = ("stats", scope, iso(end), int(sig.get("n") or 0), int(sig.get("mx") or 0), tuple(sorted(keys)))
    with _LOCK:
        hit = app.overview_cache.get(ck)
    if hit is not None:
        return hit
    settings = app.config.settings
    raw = app.store.messages_in_window(keys, start, end)
    clean, _ = clean_rows(raw, settings.get("pipeline", {}).get("clean", {}) or {}, settings.get("privacy", {}) or {})
    result = stats_for(app, keys, raw, clean, end, scope, settings)
    with _LOCK:
        for k in [k for k in app.overview_cache if isinstance(k, tuple) and k[:2] == ("stats", scope)]:
            app.overview_cache.pop(k, None)
        app.overview_cache[ck] = result
    return result


def _agents(run: dict[str, Any] | None, running: bool) -> list[dict[str, Any]]:
    stages = {s["name"]: s for s in (run or {}).get("stages", [])}
    out = []
    for code, name, names, idle_task in AGENTS:
        ss = [stages.get(n) or {"status": "pending", "metrics": {}} for n in names]
        sts = [s["status"] for s in ss]
        if "running" in sts:
            status = "running"
        elif "failed" in sts:
            status = "failed"
        elif run and all(s in ("done", "skipped") for s in sts) and "done" in sts:
            status = "done"
        else:
            status = "pending"
        msg = next((s.get("message") for s in reversed(ss) if s.get("message")), "")
        if status == "running":
            task = msg or idle_task
        elif status == "done":
            task = f"完成：{msg or idle_task}"
        elif status == "failed":
            task = f"告警：{msg or idle_task}"
        else:
            task = f"待命：{idle_task}"
        m: dict[str, Any] = {}
        for s in ss:
            m.update(s.get("metrics") or {})
        d = {"code": code, "name": name, "stages": names, "status": status, "task": task}
        metric = _metric(code, m)
        if metric:
            d["metric"] = metric
        out.append(d)
    return out


def _metric(code: str, m: dict[str, Any]) -> str | None:
    try:
        if code == "SCOUT" and "messages" in m:
            return f"已采集 {fmt_int(m['messages'])} 条"
        if code == "SWEEPER" and "clean" in m:
            return f"有效 {fmt_int(m['clean'])} 条 · 信噪比 {100 * float(m.get('snr', 0)):.1f}%"
        if code == "ANALYST" and "chunks" in m:
            return f"{m.get('threads', 0)} 线程 · {m['chunks']} 块"
        if code == "DECODER" and "candidates" in m:
            return f"候选 {m['candidates']} 条"
        if code == "STRATEGIST" and "items" in m:
            return f"情报 {m['items']} 条"
        if code == "AUDITOR" and "evidence_checked" in m:
            return f"证据 {m.get('evidence_valid', 0)}/{m['evidence_checked']} 有效"
        if code == "WRITER" and ("judgments" in m or "full_md_chars" in m):
            return f"风向 {m.get('judgments', 0)} 条 · 专题 {m.get('features', 0)} 篇"
        if code == "COURIER" and "channels" in m:
            return "仅预览，未投递" if m.get("dry_run") else f"投递 {m.get('ok', 0)}/{m['channels']}"
    except (TypeError, ValueError):
        return None
    return None


def _constellation(app: Any, groups: list[dict[str, Any]], st: dict[str, Any], internal: dict[str, Any],
                   items: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    links: list[dict[str, Any]] = []
    by_g = {g["group_key"]: g for g in st.get("top_groups", [])}
    plats = sorted({g["platform"] for g in groups}, key=lambda p: LIVE_PLATFORMS.index(p) if p in LIVE_PLATFORMS else 9)
    for p in plats:
        n = sum(by_g.get(g["key"], {}).get("messages", 0) for g in groups if g["platform"] == p)
        nodes.append({"id": f"p:{p}", "name": {"wechat": "微信", "qq": "QQ", "feishu": "飞书", "demo": "演示"}[p],
                      "type": "platform", "platform": p, "value": n})
    for g in groups:
        tg = by_g.get(g["key"], {})
        nodes.append({"id": f"g:{g['key']}", "name": g.get("alias") or g["name"], "type": "group", "platform": g["platform"],
                      "value": tg.get("messages", 0)})
        links.append({"source": f"p:{g['platform']}", "target": f"g:{g['key']}", "value": max(1, tg.get("messages", 0))})
    gkeys = {g["key"] for g in groups}
    for it in items[:20]:
        nid = f"t:{it['id']}"
        nodes.append({"id": nid, "name": it["title"][:16], "type": "topic", "value": round(float(it["score"]), 1),
                      "category": it["category"]})
        for s in it.get("sources", [])[:3]:
            if s["group_key"] in gkeys:
                links.append({"source": f"g:{s['group_key']}", "target": nid, "value": int(s["count"])})
    word_groups = internal.get("word_groups", {}) if internal else {}
    for kw in st.get("keywords", []):
        if len(nodes) >= 48:
            break
        wg = word_groups.get(kw["word"], {})
        targets = [k for k, _ in sorted(wg.items(), key=lambda kv: -kv[1]) if k in gkeys][:2]
        if not targets:
            continue
        nid = f"k:{kw['word']}"
        nodes.append({"id": nid, "name": kw["word"], "type": "topic", "value": kw["weight"], "category": "关键词"})
        links += [{"source": f"g:{k}", "target": nid, "value": int(wg[k])} for k in targets]
    return {"nodes": nodes, "links": links}


def _ticker(app: Any, heads: list[dict[str, Any]], st: dict[str, Any], report: dict[str, Any] | None,
            deliveries: list[dict[str, Any]], next_run: str | None) -> list[str]:
    out = [f"【{h['category'].split(' ', 1)[-1]}】{h['title']}——{h['hook']}" for h in heads]
    out += [f"上升信号 ▲ {r['word']}：今日 {r['today']} 次（7 日均值 {r['avg7']:g}，z={r['z']:g}）" for r in st.get("rising", [])]
    out += [f"投递回执 {'✓' if d['ok'] else '✗'} {d.get('channel_name') or d['channel_id']}" for d in deliveries[:4]]
    if report:
        out.append(f"最新报告：{report['title']}（情报 {report.get('items_total', 0)} 条）")
    out += [f"群热度 · {g['name']}：24 小时 {fmt_int(g['messages'])} 条，{g['speakers']} 人发言" for g in st.get("top_groups", [])[:6]]
    if next_run:
        out.append(f"下次出报：{next_run[5:16].replace('T', ' ')}")
    return out


def build_overview(app: Any) -> dict[str, Any]:
    mode = app.mode()
    demo = mode == "demo"
    now = app.now()
    end = (app.demo_anchor() or now.replace(minute=0, second=0, microsecond=0)) if demo else \
        now.replace(minute=(now.minute // 10) * 10, second=0, microsecond=0) + timedelta(minutes=10)
    start = end - timedelta(hours=24)
    groups = app.store.whitelisted_groups(is_demo=demo)
    keys = [g["key"] for g in groups]
    st, internal = live_stats(app, keys, end, "demo" if demo else "live")
    prev_n = app.store.count_messages(keys, start - timedelta(hours=24), start)
    activity = app.store.group_activity(keys, end)
    report = app.store.latest_report(is_demo=demo)
    items = app.store.report_items(report["id"]) if report else []
    heads = [i for i in items if i.get("is_headline")]
    prev_report = app.store.latest_report(is_demo=demo, offset=1) if report else None
    fresh = bool(report and report["window_end"] >= iso(start, app.tz))
    intel_today = int(report["items_total"]) if fresh else 0
    deliveries = app.store.deliveries_for(report["id"]) if report else []
    runner = app.runner
    current = runner.current_dto()
    last = app.store.last_finished_run(is_demo=demo)
    next_run = app.scheduler.next_run_at_any() if app.scheduler else None
    usage = app.store.llm_usage_since(iso(now.replace(hour=0, minute=0, second=0, microsecond=0), app.tz) or "")
    kpis: dict[str, Any] = {
        "messages_24h": st["messages_raw"], "messages_delta": st["messages_raw"] - prev_n,
        "intel_today": intel_today,
        "intel_delta": intel_today - int(prev_report["items_total"]) if (fresh and prev_report) else 0,
        "groups_active": sum(1 for k in keys if activity.get(k, {}).get("m24")),
        "groups_whitelisted": len(groups), "snr": st["snr"], "signals_rising": len(st["rising"]),
    }
    if next_run:
        kpis["next_run_at"] = next_run
    if last:
        kpis["last_run_status"] = last["status"]
    llm = llm_status(app)
    kb = app.store.kb_counts("demo" if demo else "live", now.strftime("%Y-%m-%d"))
    out: dict[str, Any] = {
        "generated_at": iso(now, app.tz), "mode": mode, "window": {"start": iso(start, app.tz), "end": iso(end, app.tz)},
        "kpis": kpis,
        "platforms": [platform_dto(app, p, demo_view=demo, scope_demo=demo, activity=activity, end=end) for p in LIVE_PLATFORMS],
        "stats": st, "constellation": _constellation(app, groups, st, internal, items), "headlines": heads,
        "agents": _agents(current or (run_dto(last) if last else None), current is not None),
        "ticker": _ticker(app, heads, st, report, deliveries, next_run),
        "llm": {"provider": llm["provider"], "ready": llm["ready"], "cloud_consent": llm["cloud_consent"],
                "tokens_today": int(usage["tokens"]), "cost_today_cny": usage["cost_cny"],
                "reason": llm["reason"], "offline_mode": llm["offline_mode"], **({"model": llm["model"]} if llm["model"] else {})},
        "kb": kb,                                  # v2：{total, updated_today, new_today}
    }
    if report:
        out["latest_report"] = report_summary_dto(report, deliveries)
    if current:
        out["current_run"] = current
    if last:
        out["last_run"] = run_dto(last)
    return out


async def overview(app: Any) -> dict[str, Any]:
    return await asyncio.to_thread(build_overview, app)


__all__ = ["overview", "build_overview", "live_stats"]
