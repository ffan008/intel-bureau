"""compose 子步骤 5：今日总览（一句话总结 + 今日风向）与分群摘要（config/prompts/digest.md）。
计数由代码算；没有模型时按统计结果和话题标题生成（只陈述事实，不编造）。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from bureau.core.constants import TREND_LABELS
from bureau.core.textutil import number_supported, numbers_in, truncate
from bureau.core.timeutil import window_label
from bureau.llm.base import LLMError, parse_json_text
from bureau.llm.prompts import render_prompt
from bureau.llm.schemas import DIGEST_SCHEMA, DigestOut
from bureau.pipeline.models import Item, RunContext
from bureau.pipeline.risk import has_risk, is_illegal


def _flag(text: str, source: str) -> str:
    return text + "（待核实）" if [n for n in numbers_in(text) if not number_supported(n, source)] else text


def digest_groups(rc: RunContext) -> list[dict[str, Any]]:
    """活跃群（消息数 ≥ group_digest_min_msgs，按热度取前 group_digest_max 个）与各项计数。"""
    min_msgs = int(rc.cfg("pipeline.group_digest_min_msgs", 30) or 0)
    cap = int(rc.cfg("pipeline.group_digest_max", 12) or 12)
    tops = [g for g in rc.stats.get("top_groups", []) if g["messages"] >= min_msgs][:cap]
    out = []
    for g in tops:
        k = g["group_key"]
        mine = [it for it in rc.items if any(s["group_key"] == k for s in it.sources) and not is_illegal(it)]
        counts = {"links": sum(1 for it in mine for x in it.links if _gk(x, rc) == k),
                  "prompts": sum(1 for it in mine for x in it.prompts if x["group_key"] == k),
                  "sops": sum(1 for it in mine if it.sop_steps and it.sources and it.sources[0]["group_key"] == k),
                  "data": sum(1 for it in mine for x in it.data_points if x["group_key"] == k)}
        out.append({"group_key": k, "group_name": g["name"], "platform": g["platform"], "messages": g["messages"],
                    "summary": "", "highlights": [], "counts": counts, "topics": [it.title for it in mine[:6]],
                    "item_ids": [it.id for it in mine[:6]]})
    return out


def _gk(link: dict[str, Any], rc: RunContext) -> str:
    m = rc.by_ref.get(link.get("msg", ""))
    return m.group_key if m is not None else ""


def offline_trends(rc: RunContext) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    used: set[str] = set()
    for r in rc.stats.get("rising", [])[:2]:
        related = [it.id for it in rc.items if r["word"].lower() in it.keywords][:3]
        if r["avg7"] == 0:
            text = f"「{r['word']}」首次成规模出现：今日 {r['today']} 条消息提及"
        else:
            text = f"「{r['word']}」讨论升温：今日 {r['today']} 条，过去 7 日均值 {r['avg7']:g} 条"
        out.append({"text": text, "basis": f"z 值 {r['z']:g}；主要来源群：{'、'.join(r['groups'][:3])}", "item_ids": related})
        used.update(related)
    for it in [i for i in rc.items if i.is_headline]:
        if len(out) >= 4:
            break
        if it.id in used:
            continue
        h = it.heat_raw
        q = truncate(it.evidence[0]["quote"], 36) if it.evidence else ""
        groups = "、".join(s["group_name"] for s in it.sources[:3]) or "—"
        out.append({"text": f"【{TREND_LABELS.get(it.trend, it.trend)}】{it.title}",
                    "basis": f"{groups}，{h.get('messages', 0)} 条相关消息、{h.get('participants', 0)} 人参与；原文：「{q}」",
                    "item_ids": [it.id]})
        used.add(it.id)
    risky = [it for it in rc.items if has_risk(it.risk_flags) and set(it.risk_flags) != {"未核实"}]
    if risky and len(out) < 5:
        illegal = sum(1 for it in risky if is_illegal(it))
        shown = [it for it in risky if not is_illegal(it)][:3]          # 违法高危的标题只出现在风险板块
        out.append({"text": f"有 {len(risky)} 个话题带风险标签，已标注并附免责声明"
                            + (f"（其中违法高危 {illegal} 个只记录在风险板块）" if illegal else ""),
                    "basis": "；".join(truncate(it.title, 18) for it in shown) or "详见风险板块",
                    "item_ids": [it.id for it in shown]})
    return out[:5]


def offline_summary(rc: RunContext) -> str:
    feats = [it for it in rc.items if it.is_feature]
    groups = len(rc.stats.get("top_groups", []))
    lead = "、".join(f"「{it.title}」" for it in feats[:3])
    return (f"{groups} 个群的 {rc.stats.get('messages_clean', 0)} 条有效消息整理出 {len(rc.items)} 个话题、"
            f"{len(feats)} 篇专题" + (f"，重点是{lead}" if lead else "") + "。")


def offline_group(g: dict[str, Any]) -> tuple[str, list[str]]:
    if not g["topics"]:
        return f"{g['messages']} 条消息，没有形成独立话题。", []
    return f"{g['messages']} 条消息，主要在聊{'、'.join(truncate(t, 14) for t in g['topics'][:2])}。", \
        [truncate(t, 30) for t in g["topics"][:3]]


def digest_input(rc: RunContext, groups: list[dict[str, Any]]) -> dict[str, Any]:
    st = rc.stats
    return {"stats": {"messages_raw": st.get("messages_raw", 0), "messages_clean": st.get("messages_clean", 0),
                      "groups": len(st.get("top_groups", [])), "topics": len(rc.items),
                      "articles": sum(1 for it in rc.items if it.is_feature)},
            "rising": [{k: r[k] for k in ("word", "today", "avg7", "z", "groups")} for r in st.get("rising", [])],
            # 违法高危话题不交给模型写总览（它们只出现在风险板块）
            "topics": [{"id": it.id, "title": it.title, "category": it.category, "risk_flags": it.risk_flags,
                        "is_article": it.is_feature, "groups": [s["group_name"] for s in it.sources[:4]],
                        "hook": it.hook} for it in rc.items[:30] if not is_illegal(it)],
            "illegal_topics": sum(1 for it in rc.items if is_illegal(it)),
            "groups": [{"group_key": g["group_key"], "group_name": g["group_name"], "messages": g["messages"],
                        "topics": g["topics"], "counts": g["counts"]} for g in groups]}


async def llm_digest(rc: RunContext, provider: Any, groups: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    data_text = json.dumps(digest_input(rc, groups), ensure_ascii=False)
    system, user = render_prompt(rc.app.paths.prompts, "digest", {"data": data_text,
                                                                  "window": window_label(rc.start, rc.end, rc.tz)})
    prompt, out = user, None
    for attempt in range(2):
        if rc.budget_exhausted()[0]:
            raise LLMError(f"本次模型费用已达上限 ¥{rc.cfg('llm.max_cost_cny', 0)}")
        res = await provider.complete_json(system, prompt, DIGEST_SCHEMA, max_tokens=int(rc.cfg("llm.max_tokens", 4096)),
                                           temperature=float(rc.cfg("llm.temperature", 0.2)), task="digest")
        rc.add_usage(res.usage.get("input_tokens", 0), res.usage.get("output_tokens", 0), res.cost)
        try:
            out = DigestOut.model_validate(res.parsed if res.parsed is not None else parse_json_text(res.text))
            break
        except (ValidationError, ValueError) as exc:
            if attempt:
                raise LLMError(f"总览输出两次都不合格：{str(exc)[:120]}") from exc
            prompt = user + f"\n\n你上一次的输出没有通过校验：{str(exc)[:300]}\n请只输出符合要求的 JSON。"
    assert out is not None
    ids = {it.id for it in rc.items}
    by_key = {g["group_key"]: g for g in groups}
    for gd in out.groups:
        g = by_key.get(gd.group_key)
        if g is not None and gd.summary.strip():
            g["summary"] = _flag(gd.summary.strip(), data_text)
            g["highlights"] = [_flag(h, data_text) for h in gd.highlights][:3]
    trends = [{"text": _flag(j.text.strip(), data_text), "basis": _flag(j.basis.strip(), data_text),
               "item_ids": [i for i in j.item_ids if i in ids]} for j in out.overview.trends[:5]]
    return _flag(out.overview.summary.strip(), data_text), trends


async def run_digest(rc: RunContext, provider: Any) -> dict[str, Any]:
    groups = digest_groups(rc)
    summary, trends, source = "", [], "offline"
    if provider is not None and getattr(provider, "name", "offline") != "offline" and not rc.budget_exhausted()[0]:
        try:
            summary, trends = await llm_digest(rc, provider, groups)
            source = provider.name
        except Exception as exc:                                     # noqa: BLE001
            rc.log.warn("WRITER", f"总览和分群摘要改由程序撰写：{exc}", "compose")
    if len(trends) < 3:
        trends = (trends + [j for j in offline_trends(rc) if j["text"] not in {x["text"] for x in trends}])[:5]
    for g in groups:
        if not g["summary"]:
            g["summary"], g["highlights"] = offline_group(g)
    rc.judgments = trends
    rc.digests = [{k: g[k] for k in ("group_key", "group_name", "platform", "messages", "summary", "highlights", "counts")}
                  for g in groups]
    rc.v2["summary"] = summary or offline_summary(rc)
    rc.v2["digest_source"] = source
    rc.log.info("WRITER", f"今日风向 {len(trends)} 条，分群摘要 {len(groups)} 张卡（{source}）", "compose")
    return {"judgments": len(trends), "groups": len(groups), "source": source}
