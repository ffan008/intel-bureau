"""阶段 7 score：总分 = Σ 权重 × {新颖, 可执行, 可信, 热度, 相关} − 风险惩罚 − 重复惩罚。
与 topic_memory 比较标记 new / developing / repeat，选出头条 TOP N 与专题。"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from bureau.core.constants import SERIOUS_RISKS
from bureau.core.nlp import NLP_INSTANCE, log_norm, overlap
from bureau.core.textutil import norm_url, numbers_in
from bureau.core.timeutil import to_tz
from bureau.pipeline.models import Item, RunContext, StageResult
from bureau.pipeline.risk import blocks_feature, dropped_by_policy, has_risk, is_illegal, penalty_of, policy_of, \
    sanitize_illegal

FEATURES_MIN, FEATURES_MAX = 8, 15

DIMS = ("novelty", "actionability", "credibility", "heat", "relevance")


def report_day(rc: RunContext) -> str:
    return to_tz(rc.end - timedelta(seconds=1), rc.tz).strftime("%Y-%m-%d")


def prior_memory(rc: RunContext) -> list[dict[str, Any]]:
    """近 N 天的话题记忆，只看今天之前的记录（同一天重跑结果一致）。"""
    day = report_day(rc)
    since = to_tz(rc.end - timedelta(days=int(rc.cfg("pipeline.memory_days", 14))), rc.tz).strftime("%Y-%m-%d")
    out = []
    for m in rc.app.store.memory_recent(rc.scope, since):
        days = [h.get("day") for h in m.get("history") or [] if h.get("day") and h["day"] < day]
        if days:
            m["prior_days"] = days
            out.append(m)
    return out


def memory_similarity(it: Item, m: dict[str, Any]) -> float:
    """核心词与记忆关键词的重叠、标题与记忆标题的重叠取大；共享链接直接算高度相关。"""
    kws = {k.lower() for k in m.get("keywords") or []}
    core = set(it.core) or it.keywords
    sim = overlap(core, kws)
    title_tokens = NLP_INSTANCE.token_set(m.get("title") or "")
    shared = title_tokens & it.keywords
    if len(shared) >= 2:                      # 只共享一个泛词（如"起号"）不算同一话题
        sim = max(sim, len(shared) / max(2, len(title_tokens)) * 0.8)
    links = {norm_url(link["url"]) for link in it.links}
    if links & {norm_url(u) for u in m.get("links") or []}:
        sim = max(sim, 0.8)
    return sim


def match_memory(it: Item, memory: list[dict[str, Any]]) -> tuple[dict[str, Any] | None, float]:
    best, best_sim = None, 0.0
    for m in memory:
        sim = memory_similarity(it, m)
        if sim > best_sim:
            best, best_sim = m, sim
    return best, best_sim


def classify_trend(it: Item, mem: dict[str, Any] | None, sim: float) -> str:
    if mem is None or sim < 0.3:
        return "new"
    kws = {k.lower() for k in mem.get("keywords") or []}
    core = set(it.core) or it.keywords
    new_tokens = len(core - kws) / max(1, len(core))
    mem_links = {norm_url(u) for u in mem.get("links") or []}
    new_links = any(norm_url(link["url"]) not in mem_links for link in it.links)
    if sim >= 0.75 and new_tokens < 0.25 and not new_links:
        return "repeat"
    return "developing"


def dimension_scores(it: Item, rc: RunContext, novelty_mem: float, policy: str = "flag") -> dict[str, float]:
    interests = [w.lower() for w in rc.cfg("interests.keywords", []) or []]
    cat_w = rc.cfg("interests.category_weights", {}) or {}
    text = f"{it.title} {it.hook} {it.summary} {' '.join(it.tags)} {' '.join(it.tools)}".lower()
    h = it.heat_raw
    heat = 5 * (0.35 * log_norm(h.get("messages", 0), 40) + 0.3 * log_norm(h.get("participants", 0), 12)
                + 0.2 * log_norm(h.get("groups", 1) - 1, 4) + 0.15 * log_norm(h.get("depth", 0), 6))
    heat = min(5.0, heat * min(1.5, max(0.5, float(h.get("group_weight", 1.0)))))
    act_h = min(5.0, 1.2 * bool(it.steps) + 0.8 * min(2, len(it.links)) + 0.4 * min(3, len(it.tools))
                + 0.3 * min(4, len(numbers_in(text))))
    cred_h = 2.0 + 0.5 * min(2, h.get("groups", 1) - 1) + 0.3 * min(3, h.get("participants", 1) - 1) + \
        0.3 * min(2, len(it.evidence) - 1)
    if policy == "flag":       # v2 label 策略：风险标签只标注，不影响任何一项分数
        cred_h -= 1.0 * sum(1 for r in it.risk_flags if r in ("广告引流", "金钱风险")) + 0.6 * ("未核实" in it.risk_flags)
    hits = sum(1 for w in interests if w and w in text)
    cat = it.category or ""
    # 键用完整分类名（"01 工具与资源"）；也接受只写编号（"01"）
    cw = cat_w.get(cat, cat_w.get(cat.split(" ", 1)[0], 1.0))
    relevance = min(5.0, (1.0 + 1.2 * hits) * float(cw))
    llm = it.llm_scores
    return {
        "novelty": round(0.5 * llm.get("novelty", 2.5) + 0.5 * novelty_mem, 2),
        "actionability": round(max(0.0, 0.5 * llm.get("actionability", 2.5) + 0.5 * act_h), 2),
        "credibility": round(max(0.0, min(5.0, 0.5 * llm.get("credibility", 2.5) + 0.5 * cred_h)), 2),
        "heat": round(heat, 2),
        "relevance": round(relevance, 2),
    }


def total_score(scores: dict[str, float], weights: dict[str, float], risks: list[str], trend: str,
                risk_penalty: float, repeat_penalty: float) -> float:
    wsum = sum(float(weights.get(d, 1.0)) for d in DIMS) or 1.0
    base = sum(float(weights.get(d, 1.0)) * scores[d] for d in DIMS) / wsum          # 0~5
    pen = min(2.0, risk_penalty * len(risks)) + (repeat_penalty if trend == "repeat" else 0.0)
    return round(max(0.0, base - pen) * 20, 1)                                        # 0~100


def select(items: list[Item], top_n: int, max_features: int) -> None:
    """排序、定序号、选头条与专题。序号与计数都由代码决定。"""
    items.sort(key=lambda it: (-it.score, it.title))
    for i, it in enumerate(items, start=1):
        it.rank = i
        it.is_headline = it.is_feature = False
    pool = [it for it in items if not (set(it.risk_flags) & SERIOUS_RISKS) and it.trend != "repeat"]
    heads = pool[:top_n]
    if len(heads) < top_n:
        extra = [it for it in items if it not in heads and not (set(it.risk_flags) & SERIOUS_RISKS)]
        heads += extra[:top_n - len(heads)]
    for it in heads:
        it.is_headline = True
    feats = [it for it in pool if it.steps or len(it.evidence) >= 2][:max_features]
    for it in feats:
        it.is_feature = True


def max_features_of(rc: RunContext) -> int:
    try:
        n = int(rc.cfg("pipeline.max_features", 12) or 12)
    except (TypeError, ValueError):
        n = 12
    return max(FEATURES_MIN, min(FEATURES_MAX, n))


def is_rich(it: Item) -> bool:
    return bool(it.steps or it.sop_steps or it.prompts or it.links or len(it.evidence) >= 2)


def select_v2(items: list[Item], top_n: int, max_features: int, policy: str) -> None:
    """v2 选择：排序、定序号、选头条与专题、给专题编号。序号与计数都由代码决定。
    label 策略下风险条目照常参与；违法高危永远不进头条和专题；重复话题不当专题。"""
    items.sort(key=lambda it: (-it.score, it.title))
    for i, it in enumerate(items, start=1):
        it.rank = i
        it.is_headline = it.is_feature = False
        it.seq = 0
    eligible = [it for it in items if not blocks_feature(it, policy)]
    pool = [it for it in eligible if it.trend != "repeat"]
    heads = pool[:top_n]
    if len(heads) < top_n:
        heads += [it for it in eligible if it not in heads][:top_n - len(heads)]
    for it in heads:
        it.is_headline = True
    feats = [it for it in pool if is_rich(it)][:max_features]
    if len(feats) < min(FEATURES_MIN, max_features):            # 素材不够丰富时，用其余话题补足下限
        feats += [it for it in pool if it not in feats][:min(FEATURES_MIN, max_features) - len(feats)]
    for n, it in enumerate(sorted(feats, key=lambda x: x.rank), start=1):
        it.is_feature = True
        it.seq = n


async def run(rc: RunContext) -> StageResult:
    memory = prior_memory(rc)
    blocked = [w.lower() for w in rc.cfg("interests.blocked", []) or [] if w]
    policy = policy_of(rc)
    penalty = penalty_of(rc, policy)
    weights = rc.cfg("pipeline.weights", {}) or {}
    kept: list[Item] = []
    dropped_blocked = dropped_risk = dropped_privacy = 0
    for it in rc.items:
        text = f"{it.title} {it.hook} {it.summary}".lower()
        if it.privacy:                                     # 内容主要是某个人的隐私：整条剔除（§2）
            dropped_privacy += 1
            continue
        if blocked and any(w in text for w in blocked):
            dropped_blocked += 1
            continue
        if dropped_by_policy(it, policy):
            dropped_risk += 1
            continue
        if is_illegal(it):
            sanitize_illegal(it)
        mem, sim = match_memory(it, memory)
        it.trend = classify_trend(it, mem, sim)
        if mem is not None and it.trend != "new":
            it.memory_id, it.memory_title = mem["id"], mem["title"]
            it.memory_first_seen = mem.get("first_seen")
        it.scores = dimension_scores(it, rc, 5.0 * (1 - min(1.0, sim)), policy)
        it.score = total_score(it.scores, weights, it.risk_flags, it.trend, penalty,
                               float(rc.cfg("pipeline.repeat_penalty", 1.2)))
        kept.append(it)
    rc.items = kept
    select_v2(rc.items, rc.top_n, max_features_of(rc), policy)
    trends = {t: sum(1 for it in kept if it.trend == t) for t in ("new", "developing", "repeat")}
    risky = sum(1 for it in kept if has_risk(it.risk_flags))
    illegal = sum(1 for it in kept if is_illegal(it))
    rc.v2["privacy_dropped"] = dropped_privacy
    how = {"label": "只标注、不降权", "flag": f"已降权（每个标签 −{penalty:g}）", "drop": "严重风险已剔除"}[policy]
    rc.log.info("STRATEGIST", f"评分完成：{len(kept)} 个话题（新 {trends['new']} · 持续 {trends['developing']} · "
                              f"重复 {trends['repeat']}）；风险策略 {policy}：带风险标签 {risky} 条{how}，"
                              f"其中违法高危 {illegal} 条只进风险板块", "score")
    if dropped_privacy:
        rc.log.info("STRATEGIST", f"隐私内容剔除 {dropped_privacy} 条（主要是某个人的手机号、住址等）", "score")
    if dropped_blocked:
        rc.log.info("STRATEGIST", f"命中屏蔽词剔除 {dropped_blocked} 条", "score")
    return StageResult(metrics={"items": len(kept), **trends, "risky": risky, "illegal": illegal,
                                "blocked": dropped_blocked, "dropped_risk": dropped_risk,
                                "privacy_dropped": dropped_privacy, "risk_policy": policy, "memory": len(memory),
                                "features": sum(1 for i in kept if i.is_feature),
                                "top_score": kept[0].score if kept else 0},
                       message=f"{len(kept)} 个话题 · 专题 {sum(1 for i in kept if i.is_feature)}")
