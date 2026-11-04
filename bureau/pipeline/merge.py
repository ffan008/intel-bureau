"""阶段 6 merge：两级合并。

1. 要点：跨群、跨块合并同一条情报（标题 + 关键词的 Jaccard 相似度；共享同一链接也合并；拿不准的可选交给 LLM）。
2. 话题（v2）：把讲同一件事的要点再合并成一个话题，一个话题就是报告里的一条情报、一篇专题的素材。
   用话题名、标签、工具、标题核心词的重叠系数，贪心合并；在本次运行里出现得太普遍的词不参与；
   违法高危、隐私与普通讨论不合并；单个话题的要点数有上限，防止滚雪球。
合并来源、证据、热度，以及 v2 的提示词、SOP、数据点、原话、工具结论和媒体引用。
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any

from bureau.core.constants import RISK_ILLEGAL
from bureau.core.nlp import NLP_INSTANCE, jaccard, overlap
from bureau.core.textutil import norm_url
from bureau.llm.base import parse_json_text
from bureau.llm.factory import resolve_provider
from bureau.llm.prompts import render_prompt
from bureau.llm.schemas import MERGE_SCHEMA, MergeOut
from bureau.pipeline.models import Candidate, CleanMsg, Item, RunContext, StageResult

GENERIC = {"ai", "分享", "教程", "工具", "方法", "经验", "问题", "大家", "今天", "最近", "群里", "一下", "这个", "那个",
           "效果", "感觉", "推荐", "使用", "可以", "需要", "怎么", "什么", "时候", "现在", "一个", "出来", "看看",
           "提示词", "流程", "模型", "生成", "图片", "视频", "内容", "复盘", "数据", "收藏", "学到", "实测"}
TOPIC_OVERLAP = 0.4
TOPIC_MAX_POINTS = 8
_LEAD = re.compile(r"^(分享一个|分享一下|分享下|分享|提醒一下|提醒|同步一下|同步|求助|整理了|更新|补充)[：:，,\s]*")


def signature(c: Candidate) -> set[str]:
    return NLP_INSTANCE.token_set(c.title, c.hook) | {t.lower() for t in c.tags} | {t.lower() for t in c.tools}


def cluster(cands: list[Candidate], threshold: float) -> tuple[list[list[int]], list[tuple[int, int, float]]]:
    n = len(cands)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    sigs = [signature(c) for c in cands]
    urls = [{norm_url(link["url"]) for link in c.links} for c in cands]
    unsure: list[tuple[int, int, float]] = []
    for i in range(n):
        for j in range(i + 1, n):
            if _flag_class(cands[i]) != _flag_class(cands[j]):
                continue
            sim = jaccard(sigs[i], sigs[j])
            if sim >= threshold or (urls[i] & urls[j]):
                parent[find(i)] = find(j)
            elif sim >= threshold * 0.6:
                unsure.append((i, j, sim))
    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)
    return list(groups.values()), unsure


def _flag_class(c: Candidate) -> tuple[bool, bool]:
    """违法高危、隐私的内容不与普通讨论合并（否则风险标签会污染正常话题，违法内容也会混进专题）。"""
    return RISK_ILLEGAL in c.risk_flags, bool(getattr(c, "privacy", False))


def norm_topic(s: str) -> str:
    return re.sub(r"[\s·・,，、:：/|（）()]+", "", (s or "").lower())


_COUNT_WORD = re.compile(r"^(?:[一二三四五六七八九十两几每单本第这那半整前后]+|\d+)"
                         r"[个周天集篇条张单圈次月年期件位号步段份套轮]*$|^第|^前|^最")


def topic_keys(cs: list[Candidate]) -> set[str]:
    keys: set[str] = set()
    for c in cs:
        keys |= NLP_INSTANCE.token_set(c.topic, _LEAD.sub("", c.title)) | {t.lower() for t in c.tags} | \
            {t.lower() for t in c.tools}
    return {k for k in keys if k not in GENERIC and len(k) >= 2 and not _COUNT_WORD.match(k)}


def topic_groups(cands: list[Candidate], points: list[list[int]], *, threshold: float = TOPIC_OVERLAP,
                 max_points: int = TOPIC_MAX_POINTS) -> list[list[int]]:
    """把要点（cands 的下标组）贪心合并成话题，返回每个话题包含的要点下标（points 的下标）。"""
    if not points:
        return []
    tools = {t.lower() for c in cands for t in c.tools}
    keys = [topic_keys([cands[i] for i in p]) for p in points]
    df: Counter[str] = Counter(k for ks in keys for k in ks)
    if len(points) >= 8:                                   # 在本次运行里太普遍的词不能决定话题
        common = {k for k, n in df.items() if n / len(points) > 0.35}
        keys = [ks - common for ks in keys]
    # 工具名（剪映、即梦…）很多话题都会提到，只算共同的话题词；工具名只在话题名相同时起作用
    keys = [ks - tools or ks for ks in keys]
    names = [Counter(norm_topic(cands[i].topic) for i in p if cands[i].topic).most_common(1) for p in points]
    names_s = [n[0][0] if n else "" for n in names]
    flags = [_flag_class(cands[p[0]]) for p in points]
    weight = [sum(len(cands[i].evidence) + 1 for i in p) for p in points]
    order = sorted(range(len(points)), key=lambda k: (-weight[k], k))
    topics: list[dict[str, Any]] = []
    for k in order:
        best, best_sim = None, 0.0
        for t in topics:
            if t["flags"] != flags[k] or len(t["members"]) >= max_points:
                continue
            if names_s[k] and names_s[k] in t["names"]:
                sim = 1.0
            elif not keys[k] & t["core"]:              # 和话题核心词一个都不沾：不合并（防止链式滚雪球）
                sim = 0.0
            else:
                # 与话题里任一要点共享 2 个以上区分性的词，或与核心词的重叠系数够高
                pair = max(len(keys[k] & keys[m]) for m in t["members"])
                shared = keys[k] & t["core"]
                sim = 1.0 if pair >= 2 else (overlap(keys[k], t["core"]) if len(shared) >= 2 else 0.0)
            if sim > best_sim:
                best, best_sim = t, sim
        if best is not None and best_sim >= threshold:
            best["members"].append(k)
            best["seen"].update(keys[k])
            best["core"] = best["seed"] | {w for w, n in best["seen"].items() if n >= 2}
            if names_s[k]:
                best["names"].add(names_s[k])
        else:
            topics.append({"members": [k], "seed": set(keys[k]), "core": set(keys[k]), "seen": Counter(keys[k]),
                           "flags": flags[k], "names": {names_s[k]} if names_s[k] else set()})
    return [list(t["members"]) for t in topics]


def _uniq(seq: list[Any], key: Any = lambda x: x, limit: int = 99) -> list[Any]:
    seen, out = set(), []
    for x in seq:
        k = key(x)
        if k in seen:
            continue
        seen.add(k)
        out.append(x)
    return out[:limit]


def expand_refs(refs: set[str], by_ref: dict[str, CleanMsg], children: dict[str, list[str]]) -> set[str]:
    """加上回复链的上游与下游消息。"""
    out = set(refs)
    stack = list(refs)
    while stack:
        r = stack.pop()
        m = by_ref.get(r)
        nxt = list(children.get(r, []))
        if m is not None and m.reply_ref:
            nxt.append(m.reply_ref)
        for x in nxt:
            if x not in out and x in by_ref:
                out.add(x)
                stack.append(x)
    return out


def chain_depth(refs: set[str], by_ref: dict[str, CleanMsg]) -> int:
    best = 0
    for r in refs:
        d, cur, seen = 0, by_ref.get(r), set()
        while cur is not None and cur.reply_ref and cur.ref not in seen:
            seen.add(cur.ref)
            d += 1
            cur = by_ref.get(cur.reply_ref)
        best = max(best, d)
    return best


def _round_robin(lists: list[list[Any]], limit: int) -> list[Any]:
    out: list[Any] = []
    i = 0
    while len(out) < limit and any(i < len(x) for x in lists):
        for x in lists:
            if i < len(x):
                out.append(x[i])
        i += 1
    return out[:limit]


def _rep(cs: list[Candidate]) -> Candidate:
    return max(cs, key=lambda c: c.scores.get("credibility", 0) + 0.5 * len(c.evidence) + c.scores.get("actionability", 0))


_SELF_LEAD = re.compile(r"^(?:我|我们)[^，,：:。]{0,8}?的(?=\S{4,})|^(?:出一个|整理了一个|整理了|做了一个|这篇|之前问[^，,]{0,16}的[，,]?)")
_ONE = re.compile(r"^(?:一个|一套|一篇)\s*")
_TAIL = re.compile(r"[和与及、，,：:；;的了]+$")


def tidy_title(title: str, limit: int = 30) -> str:
    """离线提取的标题是原文第一句：去掉「分享一个」「我这两天跑通的」类引导语；冒号 / 逗号前已经有 8 个字以上时
    只留前半句；最长 limit 字（在词边界截）。只删字、不加字。"""
    t = _LEAD.sub("", (title or "").strip())
    t = _ONE.sub("", _SELF_LEAD.sub("", t).strip())
    m = re.match(r"^(.{8,}?)[：:，,；;]", t)
    if m:
        t = m.group(1)
    if len(t) > limit:
        cut = max(t.rfind(c, 0, limit) for c in " 、，,")
        t = t[:cut] if cut >= 8 else t[:limit]
    return _TAIL.sub("", t.strip()).strip() or title


def _title(cs: list[Candidate], rep: Candidate) -> str:
    topics = Counter(c.topic.strip() for c in cs if c.topic.strip())
    if len(cs) > 1 and topics:
        name, n = topics.most_common(1)[0]
        if n >= 2 and 4 <= len(name) <= 24:              # 多个要点用同一个话题名时，用话题名当标题
            return name
    return tidy_title(rep.title) if rep.provider == "offline" else rep.title


def build_items(rc: RunContext, topics: list[list[list[int]]], cands: list[Candidate]) -> list[Item]:
    """topics：每个话题是若干要点，每个要点是若干候选的下标。"""
    children: dict[str, list[str]] = defaultdict(list)
    for m in rc.clean:
        if m.reply_ref:
            children[m.reply_ref].append(m.ref)
    gname = {g["key"]: (g.get("alias") or g["name"], g["platform"]) for g in rc.groups}
    items: list[Item] = []
    for gi, pts in enumerate(topics):
        point_cs = [[cands[i] for i in p] for p in pts]
        cs = [c for p in point_cs for c in p]
        rep = _rep(cs)
        order = [rep, *[c for c in cs if c is not rep]]
        refs = {r for c in cs for r in c.refs} | {e["msg"] for c in cs for e in c.evidence}
        expanded = expand_refs({r for r in refs if r in rc.by_ref}, rc.by_ref, children)
        msgs = [rc.by_ref[r] for r in expanded]
        group_counts: Counter[str] = Counter(m.group_key for m in msgs)
        for m in msgs:
            for k in m.spread_groups:
                group_counts[k] += 1
        sources = [{"group_key": k, "group_name": gname.get(k, (k, ""))[0], "platform": gname.get(k, ("", k.split(":")[0]))[1],
                    "count": n} for k, n in group_counts.most_common()]
        llm_scores = {k: round(max(c.scores.get(k, 0) for c in cs), 2) for k in ("novelty", "actionability", "credibility")}
        cat_w: Counter[str] = Counter()
        for c in cs:
            cat_w[c.category] += 1 + len(c.evidence)
        points = []
        for p in point_cs:
            pr = _rep(p)
            points.append({"title": pr.title, "hook": pr.hook, "summary": pr.summary, "group_key": pr.group_key,
                           "steps": pr.steps[:6]})
        it = Item(
            id=f"tmp{gi}", title=_title(cs, rep), hook=rep.hook, summary=rep.summary,
            category=rep.category if cat_w[rep.category] == max(cat_w.values()) else cat_w.most_common(1)[0][0],
            kind=rep.kind, steps=rep.steps or next((c.steps for c in order if c.steps), []),
            tools=_uniq([t for c in order for t in c.tools], str.lower, 10),
            links=_uniq([link for c in order for link in c.links], lambda x: norm_url(x["url"]), 12),
            evidence=_uniq(_round_robin([[e for c in p for e in c.evidence] for p in point_cs], 24),
                           lambda e: (e["msg"], e["quote"]), 8),
            participants=_uniq([p for c in order for p in c.participants], limit=12),
            llm_scores=llm_scores, risk_flags=_uniq([r for c in cs for r in c.risk_flags]),
            tags=_uniq([t for c in order for t in c.tags], str.lower, 8), refs=expanded, candidates=len(cs),
            sources=sources)
        it.topic = Counter(c.topic for c in cs if c.topic).most_common(1)[0][0] if any(c.topic for c in cs) else ""
        it.points = points
        it.sop_steps = max((c.sop_steps for c in cs), key=len, default=[])
        it.prompts = _uniq([x for c in order for x in c.prompts], lambda x: (x["msg"], x.get("excerpt", "")[:40]), 12)
        it.data_points = _uniq([x for c in order for x in c.data_points], lambda x: (x["msg"], x["value"]), 12)
        it.quotes = _uniq([x for c in order for x in c.quotes], lambda x: (x["msg"], x.get("quote", "")), 6)
        it.tool_notes = _uniq([x for c in order for x in c.tool_notes], lambda x: (x["msg"], x["tool"]), 8)
        it.media_refs = _uniq([x for c in order for x in c.media_refs], lambda x: x["msg"], 8)
        it.privacy = any(c.privacy for c in cs)
        it.heat_raw = {"messages": len(msgs), "participants": len({m.sender for m in msgs}),
                       "groups": len(group_counts), "depth": chain_depth(expanded, rc.by_ref),
                       "group_weight": max((m.group_weight for m in msgs), default=1.0)}
        it.keywords = NLP_INSTANCE.token_set(it.title, it.hook, it.summary, it.topic) | \
            {t.lower() for t in it.tags} | {t.lower() for t in it.tools}
        texts = [it.title, it.topic, it.hook, it.summary, *it.steps, *(p["title"] for p in points),
                 *(rc.by_ref[e["msg"]].text for e in it.evidence if e["msg"] in rc.by_ref)]
        core = [w.lower() for w in NLP_INSTANCE.extract_keywords(texts, top_k=12)]
        it.core = list(dict.fromkeys([*core, *(t.lower() for t in it.tags), *(t.lower() for t in it.tools)]))
        items.append(it)
    return items


async def judge_unsure(rc: RunContext, cands: list[Candidate], unsure: list[tuple[int, int, float]]) -> list[tuple[int, int]]:
    if not rc.cfg("llm.merge_judge", False) or not unsure:
        return []
    provider = resolve_provider(rc.app).provider
    if provider.name == "offline":
        return []
    out: list[tuple[int, int]] = []
    for i, j, sim in sorted(unsure, key=lambda x: -x[2])[:20]:
        pair = json.dumps([{"title": c.title, "hook": c.hook, "tags": c.tags} for c in (cands[i], cands[j])], ensure_ascii=False)
        system, user = render_prompt(rc.app.paths.prompts, "merge", {"pair": pair})
        try:
            res = await provider.complete_json(system, user, MERGE_SCHEMA, max_tokens=200, temperature=0, task="merge",
                                               context={"similarity": sim})
            rc.add_usage(res.usage.get("input_tokens", 0), res.usage.get("output_tokens", 0), res.cost)
            if MergeOut.model_validate(res.parsed if res.parsed is not None else parse_json_text(res.text)).same:
                out.append((i, j))
        except Exception as exc:                                     # noqa: BLE001
            rc.log.warn("STRATEGIST", f"合并判断调用失败：{exc}", "merge")
            break
    return out


async def run(rc: RunContext) -> StageResult:
    threshold = float(rc.cfg("pipeline.merge_threshold", 0.35))
    groups, unsure = cluster(rc.candidates, threshold)
    extra = await judge_unsure(rc, rc.candidates, unsure)
    if extra:
        index = {i: gi for gi, g in enumerate(groups) for i in g}
        for i, j in extra:
            a, b = index[i], index[j]
            if a != b:
                groups[a].extend(groups[b])
                for k in groups[b]:
                    index[k] = a
                groups[b] = []
        groups = [g for g in groups if g]
    topics = topic_groups(rc.candidates, groups, threshold=float(rc.cfg("pipeline.topic_overlap", TOPIC_OVERLAP)))
    rc.items = build_items(rc, [[groups[k] for k in t] for t in topics], rc.candidates)
    merged = len(rc.candidates) - len(rc.items)
    cross = sum(1 for it in rc.items if it.heat_raw["groups"] > 1)
    rc.log.info("STRATEGIST", f"合并 {len(rc.candidates)} 条候选 → {len(groups)} 个要点 → {len(rc.items)} 个话题"
                              f"（跨群话题 {cross} 个）", "merge")
    return StageResult(metrics={"candidates": len(rc.candidates), "points": len(groups), "topics": len(rc.items),
                                "merged": merged, "cross_group": cross, "llm_judged": len(extra)},
                       message=f"{len(rc.items)} 个话题")
