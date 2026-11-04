"""offline 提供方：不需要模型的规则提取。

按线索词、链接、数字、长度给消息打分；高分消息作为锚点，带上它的回复链和紧跟着的讨论组成一个话题。
标题、要点、步骤、证据全部摘自原文，不改写、不编造。
"""

from __future__ import annotations

import asyncio
import re
import time
from collections import Counter, defaultdict
from typing import Any

from bureau.core.nlp import NLP_INSTANCE
from bureau.core.taxonomy import Taxonomy
from bureau.core.textutil import URL_RE, extract_urls, first_clause, info_chars, numbers_in
from bureau.llm.base import LLMProvider, LLMResult

ANCHOR_MIN = 4.0
_LEAD_RE = re.compile(r"^(分享一个|分享一下|分享下|分享|提醒一下|提醒|同步一下|同步|求助|有偿求|整理了|更新|最近|说一下|补充)[：:，,\s]*")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])\s*|\n+")
_STEP_MARK = re.compile(r"(?:第[一二三四五六七八九十\d]+步|(?<![\d.])\d[.、)）](?!\d)|（\d）)\s*")
_SEQ_SPLIT = re.compile(r"(?:^|[，,；;。])\s*(?:先|首先|再|然后|接着|最后)")
_LINK_TITLE = re.compile(r"^\[链接\]\s*(.+)$")


def score_msg(m: dict[str, Any], tax: Taxonomy, reply_count: int = 0) -> float:
    text = m.get("text") or ""
    n = info_chars(URL_RE.sub("", text))
    s = min(n, 120) / 20.0
    if m.get("urls"):
        s += 2.0
    s += 1.2 * min(3, tax.cue_hits(text, "method")) + 1.0 * min(3, tax.cue_hits(text, "data"))
    s += 0.8 * min(2, tax.cue_hits(text, "news")) + 0.8 * min(2, tax.cue_hits(text, "demand"))
    s += 0.6 * min(1, tax.cue_hits(text, "question"))
    s += 0.6 * min(3, len(numbers_in(text)))
    s += 0.5 * min(3, len(tax.tools_in(text)))
    s += 1.0 * min(2, len(tax.risks_in(text)))          # 灰色内容也是情报（进「风险与待核实」）
    if _STEP_MARK.search(text):
        s += 1.5
    s += 0.6 * min(4, reply_count)
    if n < 8:
        s -= 2.0
    return s


def quote_of(text: str, limit: int = 80) -> str:
    t = (text or "").strip()
    if len(t) <= limit:
        return t
    cut = max(t.rfind(c, 0, limit) for c in "。！？；，,")
    return t[:cut + 1] if cut >= 30 else t[:limit]


_FILLER = re.compile(r"^(对|嗯|是的|没错|好的|可以|哈哈+|我也是|同感|说真的)[，,。！!\s]+")


def _title(anchor: str) -> str:
    t = _LEAD_RE.sub("", anchor.strip())
    return first_clause(t, 30) or first_clause(anchor, 30)


def _snippet(text: str, n: int) -> str:
    t = _FILLER.sub("", (text or "").strip())
    return quote_of(t, n).rstrip("，,；;。 ")


def _hook(title: str, texts: list[str], tax: Taxonomy) -> str:
    """一句话价值：选信息量最大、且不只是重复标题的原文句子。"""
    cands: list[str] = []
    for t in texts:
        if t.startswith(("[链接]", "[文件]", "[图片]", "[卡片]")):
            continue
        for s in _SENT_SPLIT.split(URL_RE.sub("", t)):
            s = _LEAD_RE.sub("", _FILLER.sub("", s.strip())).strip("，,；; ")
            if info_chars(s) < 8:
                continue
            if title and s.startswith(title):
                rest = s[len(title):]
                if rest and rest[0] not in "，,：:；;。":       # 标题在词中间截断：跳到下一个分句
                    cut = min((i for i in (rest.find(c) for c in "，,：:；;") if i >= 0), default=-1)
                    rest = rest[cut + 1:] if cut >= 0 else ""
                s = rest.lstrip("，,：:；; ")
            if title and title in s and len(s) <= len(title) + 8:
                continue
            if info_chars(s) >= 8:
                cands.append(s)
    if not cands:
        return title
    def value(s: str) -> tuple[float, int]:
        question = s.endswith(("吗", "？", "?", "呢")) or tax.cue_hits(s, "question") > 0
        return (len(numbers_in(s)) + tax.cue_hits(s, "method") + tax.cue_hits(s, "data") + len(tax.tools_in(s))
                - (2.5 if question else 0.0), min(len(s), 40))

    best = max(cands, key=value)
    return quote_of(best, 40).rstrip("，,；;。")


def _steps(texts: list[str]) -> list[str]:
    joined = "\n".join(texts)
    if _STEP_MARK.search(joined):
        parts = [p.strip(" ，,；;。\n") for p in _STEP_MARK.split(joined)[1:]]
        out = [re.split(r"[。\n]", p)[0].strip(" ，,；;") for p in parts]
        out = [p for p in out if info_chars(p) >= 4]
        if len(out) >= 2:
            return out[:8]
    body = texts[0].split("：", 1)[-1] if "：" in texts[0] else texts[0]
    segs = [s.strip(" ，,；;。") for s in _SEQ_SPLIT.split(body)]
    segs = [re.split(r"[。\n]", s)[0] for s in segs if info_chars(s) >= 4]
    return segs[:6] if len(segs) >= 3 else []


def _kind(anchor: str, text: str, tax: Taxonomy, risks: list[str], steps: list[str], links: list[str],
          tools: list[str]) -> str:
    """类型主要看话题起点（anchor），步骤与链接看整段讨论。"""
    if [r for r in risks if r != "未核实"]:
        return "风险预警"
    if any(w in anchor for w in ("有偿", "预算", "外包", "求：", "求助", "招人", "接单吗")):
        return "需求机会"
    if steps:
        return "教程方法"
    nums = len(numbers_in(anchor))
    if ((tax.cue_hits(anchor, "data") or "数据" in anchor) and nums >= 2) or nums >= 3:
        return "数据复盘"
    if tax.cue_hits(anchor, "method") >= 2:
        return "教程方法"
    if links and (tools or any(w in text for w in ("整理", "合集", "对照表", "模板", "开源"))):
        return "工具资源"
    if tax.cue_hits(anchor, "news"):
        return "动态新闻"
    if tax.cue_hits(anchor, "question") or anchor.rstrip().endswith(("吗", "？", "?")):
        return "问答精华"
    return "观点判断"


def extract_messages(msgs: list[dict[str, Any]], tax: Taxonomy, *, max_items: int = 6) -> dict[str, Any]:
    by_ref = {m["ref"]: m for m in msgs}
    children: dict[str, list[str]] = defaultdict(list)
    for m in msgs:
        if m.get("reply_ref") in by_ref:
            children[m["reply_ref"]].append(m["ref"])
    base = {m["ref"]: score_msg(m, tax, len(children.get(m["ref"], []))) for m in msgs}
    # 引出高质量回复的提问也有价值（问答精华）
    scores = {r: s + 0.4 * sum(sorted((max(0.0, base[c]) for c in children.get(r, []) if c in base), reverse=True)[:2])
              for r, s in base.items()}
    order = sorted(msgs, key=lambda m: scores[m["ref"]], reverse=True)
    used: set[str] = set()
    items: list[dict[str, Any]] = []
    for anchor in order:
        if scores[anchor["ref"]] < ANCHOR_MIN or len(items) >= max_items:
            break
        replies_to_anchor = anchor.get("reply_ref") in by_ref and scores.get(anchor["reply_ref"], 0) >= ANCHOR_MIN
        if anchor["ref"] in used or replies_to_anchor:
            continue
        cluster = _cluster(anchor, msgs, children, by_ref, scores, tax, used)
        if len(cluster) < 2 and not anchor.get("urls"):
            continue
        used.update(m["ref"] for m in cluster)
        items.append(_build(anchor, cluster, scores, tax))
    covered = sum(1 for m in msgs if m["ref"] in used)
    return {"items": items, "noise_ratio": round(1 - covered / len(msgs), 3) if msgs else 0.0}


def _serious(tax: Taxonomy, text: str) -> bool:
    return any(r != "未核实" for r in tax.risks_in(text))


def _cluster(anchor: dict[str, Any], msgs: list[dict[str, Any]], children: dict[str, list[str]],
             by_ref: dict[str, dict[str, Any]], scores: dict[str, float], tax: Taxonomy,
             exclude: set[str] | frozenset[str] = frozenset()) -> list[dict[str, Any]]:
    """锚点 + 回复链 + 同一线程里紧接着的相关讨论（滚动时间窗）。风险内容不与普通话题混在一起。"""
    refs: list[str] = []
    ref_set: set[str] = set()

    def add(r: str) -> None:
        stack = [r]
        while stack:
            x = stack.pop()
            if x in ref_set or x not in by_ref or (x in exclude and x != anchor["ref"]):
                continue
            ref_set.add(x)
            refs.append(x)
            stack.extend(children.get(x, []))
            parent = by_ref.get(by_ref[x].get("reply_ref") or "")
            if parent is not None and parent["ts"] >= anchor["ts"] and parent.get("thread_id") == anchor.get("thread_id"):
                stack.append(parent["ref"])          # 回复的上文也属于这段讨论

    add(anchor["ref"])
    anchor_tokens = NLP_INSTANCE.token_set(anchor["text"])
    anchor_risky = _serious(tax, anchor["text"])
    people = {anchor["sender"]}
    last_ts = anchor["ts"]
    later = sorted((m for m in msgs if m.get("thread_id") == anchor.get("thread_id") and m["ts"] > anchor["ts"]),
                   key=lambda m: m["ts"])
    for m in later:
        if m["ref"] in ref_set:
            last_ts = max(last_ts, m["ts"])
            continue
        if m["ts"] - anchor["ts"] > 45 * 60:
            break
        if m["ts"] - last_ts > 12 * 60 or _serious(tax, m["text"]) != anchor_risky:
            continue
        shared = len(anchor_tokens & NLP_INSTANCE.token_set(m["text"]))
        strong = scores[m["ref"]] >= ANCHOR_MIN
        ok = m.get("reply_ref") in ref_set or shared >= 2 or (not strong and (
            (m["sender"] in people and scores[m["ref"]] >= 2) or (shared >= 1 and scores[m["ref"]] >= 3)))
        if ok:
            add(m["ref"])
            people.add(m["sender"])
            last_ts = m["ts"]
    cluster = [by_ref[r] for r in refs]
    cluster.sort(key=lambda m: m["ts"])
    return cluster


def _build(anchor: dict[str, Any], cluster: list[dict[str, Any]], scores: dict[str, float], tax: Taxonomy) -> dict[str, Any]:
    texts = [m["text"] for m in cluster]
    alltext = "\n".join(texts)
    title = _title(anchor["text"])
    hook = _hook(title, texts, tax)
    support = sorted((m for m in cluster if m is not anchor), key=lambda m: scores[m["ref"]], reverse=True)
    summary_parts = [_snippet(anchor["text"], 150)] + [_snippet(m["text"], 80) for m in support[:2] if scores[m["ref"]] >= 2.5]
    urls = list(dict.fromkeys(u for m in cluster for u in (m.get("urls") or extract_urls(m["text"]))))
    link_titles = [mt.group(1) for t in texts if (mt := _LINK_TITLE.match(t))]
    links = [{"url": u, "title": link_titles[i] if i < len(link_titles) else ""} for i, u in enumerate(urls[:6])]
    tools = tax.tools_in(alltext)[:8]
    steps = _steps([anchor["text"], *[m["text"] for m in support if m["sender"] == anchor["sender"]]])
    risks = tax.risks_in(alltext)
    kind = _kind(anchor["text"], alltext, tax, risks, steps, urls, tools)
    category = tax.classify(anchor["text"])
    if category == tax.other_label:
        category = tax.classify(alltext)
    if kind == "风险预警":
        category = next((c for c in tax.labels if c.startswith("08")), category)
    ev_msgs = [anchor] + [m for m in support if scores[m["ref"]] >= 3.0][:2]
    evidence = [{"msg": m["ref"], "quote": quote_of(m["text"])} for m in ev_msgs]
    nums = len(numbers_in(alltext))
    novelty = 2.0 + 0.8 * min(2, tax.cue_hits(alltext, "news")) + (0.5 if "新" in anchor["text"] else 0)
    action = 1.0 + 1.2 * bool(steps) + 0.8 * bool(urls) + 0.4 * min(2, len(tools)) + 0.3 * min(3, nums)
    cred = 2.0 + 0.6 * min(2, tax.cue_hits(alltext, "data")) + 0.4 * min(2, len(evidence) - 1) + \
        0.3 * min(3, len({m["sender"] for m in cluster}) - 1)
    cred -= 1.2 * sum(1 for r in risks if r in ("广告引流", "金钱风险")) + 0.8 * ("未核实" in risks)
    tags = [w for w in NLP_INSTANCE.extract_keywords(texts, top_k=6) if w not in tools][:5]
    return {
        "title": title, "hook": hook, "summary": ("；".join(p for p in summary_parts if p) + "。")[:400],
        "category": category, "kind": kind, "steps": steps, "tools": tools, "links": links,
        "evidence": evidence, "participants": list(dict.fromkeys(m["sender"] for m in cluster))[:8],
        "scores": {"novelty": round(min(5, novelty), 2), "actionability": round(min(5, action), 2),
                   "credibility": round(max(0.5, min(5, cred)), 2)},
        "risk_flags": risks, "tags": tags, "refs": [m["ref"] for m in cluster],
    }


class OfflineProvider(LLMProvider):
    """规则提取器，实现与其它提供方相同的接口（通过 context 拿到结构化的块）。"""
    name = "offline"
    label = "离线规则提取（不调用模型）"

    def __init__(self, *args: Any, taxonomy: Taxonomy | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.taxonomy = taxonomy or Taxonomy()

    @property
    def is_cloud(self) -> bool:
        return False

    @property
    def model(self) -> str:
        return "rules-v1"

    async def complete_json(self, system: str, user: str, schema: dict[str, Any] | None = None, *,
                            max_tokens: int = 4096, temperature: float = 0.2, task: str | None = None,
                            context: dict[str, Any] | None = None) -> LLMResult:
        t0 = time.perf_counter()
        ctx = context or {}
        if task == "extract" and "messages" in ctx:
            parsed: Any = await asyncio.to_thread(extract_messages, ctx["messages"], self.taxonomy)
        elif task == "extract_v2" and "messages" in ctx:
            from bureau.llm.offline_v2 import extract_messages_v2

            parsed = await asyncio.to_thread(extract_messages_v2, ctx["messages"], self.taxonomy)
        elif task == "merge":
            parsed = {"same": bool(ctx.get("similarity", 0) >= 0.5), "reason": "规则判断：相似度阈值"}
        elif task == "compose" and "fallback" in ctx:
            parsed = ctx["fallback"]
        else:
            parsed = {"ok": True}
        return LLMResult(text="", parsed=parsed, provider=self.name, model=self.model, latency=time.perf_counter() - t0)


def kind_counts(items: list[dict[str, Any]]) -> Counter[str]:
    return Counter(i.get("kind", "") for i in items)
