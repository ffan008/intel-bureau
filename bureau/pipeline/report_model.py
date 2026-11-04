"""报告数据模型：从流水线结果构建 IntelItemDTO 和报告上下文。所有计数、序号都在这里由代码算好。"""

from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Any

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.constants import RISK_ILLEGAL, SERIOUS_RISKS, SERIOUS_RISKS_V2
from bureau.core.textutil import fmt_int, norm_url
from bureau.core.timeutil import date_label, window_label
from bureau.pipeline.models import Item, RunContext

ACTIONS = {
    "教程方法": "按原文步骤复现一遍，记下参数和耗时",
    "工具资源": "收藏链接，挑一个场景试用",
    "数据复盘": "对照自己的数据，看哪些做法可以借鉴",
    "动态新闻": "等官方信息确认后再调整计划",
    "观点判断": "作为参考，结合自己的情况判断",
    "需求机会": "评估能否承接，先确认预算、交付时间和付款方式",
    "风险预警": "不要照做，提醒身边的人注意",
    "问答精华": "遇到同样问题时按这个思路排查",
}
PLATFORM_ORDER = ("wechat", "qq", "feishu", "demo")


def suggest_action(it: Item, policy: str = "flag") -> str:
    """policy=label（v2）：风险条目照常给建议，只提醒自行判断；违法高危只提醒注意。flag：v1 的说法。"""
    if RISK_ILLEGAL in it.risk_flags:
        return "只作了解，不要参与，提醒身边的人注意"
    if set(it.risk_flags) & SERIOUS_RISKS and policy == "flag":
        return ACTIONS["风险预警"]
    act = ACTIONS.get(it.kind, ACTIONS["观点判断"])
    if it.links and it.kind not in ("工具资源", "风险预警"):
        act += "；可先打开原文链接"
    if set(it.risk_flags) & SERIOUS_RISKS_V2:
        act += "；涉及平台规则或账号资金，是否采用请自行判断"
    return act


def item_dto(it: Item, report_id: str, policy: str = "flag") -> dict[str, Any]:
    d: dict[str, Any] = {
        "id": it.id, "report_id": report_id, "rank": it.rank, "title": it.title, "hook": it.hook,
        "summary": it.summary, "category": it.category, "kind": it.kind, "score": it.score,
        "scores": {k: it.scores.get(k, 0.0) for k in ("novelty", "actionability", "credibility", "heat", "relevance")},
        "trend": it.trend, "risk_flags": list(it.risk_flags), "tags": list(it.tags), "steps": list(it.steps),
        "tools": list(it.tools), "links": [{"url": x["url"], **({"title": x["title"]} if x.get("title") else {})}
                                           for x in it.links],
        "evidence": [{k: e[k] for k in ("message_id", "group_key", "group_name", "platform", "sender", "sent_at", "quote")}
                     for e in it.evidence],
        "sources": list(it.sources), "participants": list(it.participants),
        "is_headline": it.is_headline, "is_feature": it.is_feature,
        "action": suggest_action(it, policy), "unverified": list(it.unverified),
        # ---- v2（只增不改） ----
        "topic": it.topic, "seq": it.seq, "sop_steps": list(it.sop_steps),
        "prompts": [{k: x.get(k) for k in ("text", "purpose", "sender", "group_name", "sent_at", "message_id", "verbatim")}
                    for x in it.prompts],
        "data_points": [{k: x.get(k) for k in ("label", "value", "unit", "sender", "group_name", "sent_at",
                                               "self_reported", "message_id")} for x in it.data_points],
        "quotes": [{k: x.get(k) for k in ("quote", "sender", "group_name", "sent_at", "message_id")} for x in it.quotes],
        "tool_notes": [{k: x.get(k) for k in ("tool", "scene", "verdict", "sender", "group_name", "sent_at")}
                       for x in it.tool_notes],
    }
    if it.feature:
        d["feature"] = it.feature
    for x, link in zip(d["links"], it.links):
        for k in ("kind", "code", "shared_by", "group_name", "sent_at"):
            if link.get(k):
                x[k] = link[k]
    if it.memory_title:
        d["memory"] = {"title": it.memory_title, "first_seen": it.memory_first_seen}
    return d


def source_line(it: Item) -> str:
    ev = it.evidence[0] if it.evidence else None
    groups = "、".join(f"{PLATFORM_LABELS.get(Platform(s['platform']), s['platform'])}·{s['group_name']}"
                       for s in it.sources[:3]) or "—"
    if ev is None:
        return groups
    return f"{groups}｜{ev['sender']} · {ev['sent_at'][5:16].replace('T', ' ')}"


def build_context(rc: RunContext) -> dict[str, Any]:
    items = sorted(rc.items, key=lambda i: i.rank)
    st = rc.stats
    trends = Counter(i.trend for i in items)
    plat_groups = {p["platform"]: p["groups"] for p in st.get("by_platform", [])}
    plat_part = " · ".join(f"{PLATFORM_LABELS[Platform(p)]} {plat_groups[p]} 群" for p in PLATFORM_ORDER if plat_groups.get(p))
    win = window_label(rc.start, rc.end, rc.tz)
    dlabel = date_label(rc.end - timedelta(seconds=1), rc.tz)
    header = (f"窗口 {win}｜{plat_part or '无消息'}｜有效消息 {fmt_int(st.get('messages_clean', 0))} / "
              f"{fmt_int(st.get('messages_raw', 0))}（信噪比 {100 * st.get('snr', 0):.1f}%）｜情报 {len(items)} 条"
              f"（新 {trends.get('new', 0)} · 持续 {trends.get('developing', 0)} · 重复 {trends.get('repeat', 0)}）")
    heads = [i for i in items if i.is_headline]
    feats = [i for i in items if i.is_feature]
    risks = [i for i in items if set(i.risk_flags) & SERIOUS_RISKS or i.unverified or "未核实" in i.risk_flags]
    tracking = [i for i in items if i.trend in ("developing", "repeat") and i.memory_title]
    shown = {i.id for i in heads} | {i.id for i in feats} | {i.id for i in risks}
    others = [i for i in items if i.id not in shown]
    resources: dict[str, list[dict[str, str]]] = {}
    seen: set[str] = set()
    for it in items:
        for link in it.links:
            k = norm_url(link["url"])
            if k in seen:
                continue
            seen.add(k)
            resources.setdefault(it.category, []).append({"url": link["url"], "title": link.get("title") or it.title,
                                                          "item": it.title})
    return {
        "title": f"情报局 · 每日风向标 | {dlabel}", "date_label": dlabel, "window_label": win, "header": header,
        "items": items, "heads": heads, "feats": feats, "risks": risks, "tracking": tracking, "others": others,
        "resources": dict(sorted(resources.items())), "judgments": rc.judgments, "stats": st, "trends": dict(trends),
        "demo": rc.demo, "dry_run": rc.dry_run, "provider": rc.llm_provider, "top_n": rc.top_n,
        "report_id": rc.report.get("id", rc.run_id),
        "dashboard_url": f"{rc.app.dashboard_url()}/reports?id={rc.report.get('id', rc.run_id)}",
        "weights": rc.cfg("pipeline.weights", {}) or {}, "rising_z": rc.cfg("pipeline.rising_z", 2.0),
        "rising_min": rc.cfg("pipeline.rising_min_count", 5),
    }
