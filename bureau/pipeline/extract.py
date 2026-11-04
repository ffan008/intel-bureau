"""阶段 5 extract（LLM）：逐块调用 extract_v2.md，输出候选情报（含 v2 扩展字段：提示词、SOP、数据点、原话、
工具结论、媒体引用、隐私标记）。并发受限、按内容哈希缓存；JSON 校验失败带错误重试 1 次，再失败或模型不可用时
改用 offline 规则提取。消息引用在这里先按"必须是本块里的消息"过滤一遍，内容在 verify 阶段再核对。"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from pydantic import ValidationError

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.constants import LINK_KINDS, RISK_ILLEGAL, RISK_PRIVACY
from bureau.core.taxonomy import Taxonomy, load_taxonomy_v2
from bureau.core.timeutil import window_label
from bureau.llm.base import LLMError, LLMProvider, parse_json_text
from bureau.llm.cache import LLMCache, cache_key
from bureau.llm.factory import resolve_provider
from bureau.llm.offline import OfflineProvider
from bureau.llm.prompts import render_prompt
from bureau.llm.schemas import EXTRACT_V2_SCHEMA, ExtractOutV2
from bureau.pipeline.models import Candidate, Chunk, RunContext, StageResult

_REF = re.compile(r"m?(\d+)")


def norm_ref(s: str) -> str:
    m = _REF.search(str(s or "").strip("[] "))
    return f"m{m.group(1)}" if m else str(s)


def _in_chunk(rows: list[Any], refs: set[str], key: str = "msg") -> list[dict[str, Any]]:
    """子项的消息引用必须是本块里的消息（编号写错的直接丢掉）。"""
    out = []
    for x in rows:
        d = x.model_dump() if hasattr(x, "model_dump") else dict(x)
        d[key] = norm_ref(d.get(key, ""))
        if d[key] in refs:
            out.append(d)
    return out


def to_candidates(out: ExtractOutV2, chunk: Chunk, tax: Taxonomy, provider: str) -> list[Candidate]:
    refs_in_chunk = {m.ref for m in chunk.msgs}
    by_ref = {m.ref: m for m in chunk.msgs}
    res: list[Candidate] = []
    for it in out.items:
        evidence = [{"msg": norm_ref(e.msg), "quote": e.quote.strip()} for e in it.evidence if e.quote.strip()]
        ev_text = "\n".join(by_ref[e["msg"]].text for e in evidence if e["msg"] in by_ref)
        risks = [r for r in it.risk_flags if r in tax.risk_flags]
        for r in tax.risks_in(f"{it.title}\n{it.summary}\n{ev_text}"):     # 代码再按词表兜底打风险标签
            if r not in risks:
                risks.append(r)
        privacy = bool(it.privacy) or RISK_PRIVACY in risks
        risks = [r for r in risks if r != RISK_PRIVACY]
        refs = [r for r in (norm_ref(x) for x in it.refs) if r in refs_in_chunk]
        refs += [e["msg"] for e in evidence if e["msg"] in refs_in_chunk and e["msg"] not in refs]
        illegal = RISK_ILLEGAL in risks
        media_refs = [x for x in _in_chunk(it.media_refs, refs_in_chunk) if by_ref[x["msg"]].media is not None]
        links = [{"url": x.url.strip(), "title": x.title, "kind": x.kind if x.kind in LINK_KINDS else ""}
                 for x in it.links if x.url.strip()][:12]
        sub_refs = [x["msg"] for rows in (it.prompts, it.data_points, it.quotes, it.tool_notes) for x in
                    _in_chunk(rows, refs_in_chunk)] + [x["msg"] for x in media_refs]
        refs += [r for r in dict.fromkeys(sub_refs) if r not in refs]
        res.append(Candidate(
            chunk_id=chunk.id, group_key=chunk.group_key, title=it.title, hook=it.hook, summary=it.summary,
            category=tax.normalize_category(it.category), kind=it.kind if it.kind in tax.kinds else "观点判断",
            steps=[] if illegal else it.steps[:10], tools=it.tools[:10], links=[] if illegal else links,
            evidence=evidence[:4], participants=it.participants[:10], scores=it.scores.model_dump(),
            risk_flags=risks, tags=it.tags[:6], refs=refs, provider=provider, topic=it.topic,
            sop_steps=[] if illegal else it.sop_steps[:12],
            prompts=[] if illegal else _in_chunk(it.prompts, refs_in_chunk),
            data_points=[] if illegal else _in_chunk(it.data_points, refs_in_chunk),
            quotes=_in_chunk(it.quotes, refs_in_chunk), tool_notes=[] if illegal else _in_chunk(it.tool_notes, refs_in_chunk),
            media_refs=[] if illegal else media_refs, privacy=privacy))
    return res


def offline_context(chunk: Chunk) -> dict[str, Any]:
    return {"messages": [m.as_offline() for m in chunk.msgs]}


async def extract_chunk(rc: RunContext, chunk: Chunk, provider: LLMProvider, offline: LLMProvider, cache: LLMCache,
                        sem: asyncio.Semaphore, tax: Taxonomy) -> tuple[ExtractOutV2, str, bool]:
    """返回 (输出, 实际使用的提供方, 是否命中缓存)。"""
    if provider.name != "offline":
        system, user = render_prompt(rc.app.paths.prompts, "extract_v2", {
            "chat_log": chunk.text.split("\n", 1)[-1], "group_name": chunk.group_name,
            "platform": PLATFORM_LABELS.get(Platform(chunk.platform), chunk.platform),
            "window": window_label(rc.start, rc.end, rc.tz), "taxonomy": "、".join(tax.labels),
            "kinds": "、".join(tax.kinds), "risk_flags": "、".join(tax.risk_flags)})
        key = cache_key("extract_v2", provider.name, provider.model, system, user)
        hit = cache.get(key)
        if hit is not None:
            try:
                return ExtractOutV2.model_validate(hit["parsed"]), provider.name, True
            except (ValidationError, KeyError, TypeError):
                pass
        prompt = user
        async with sem:
            for attempt in range(2):
                exhausted, first = rc.budget_exhausted()
                if exhausted:
                    rc.budget_capped += 1
                    if first:
                        rc.log.warn("DECODER", f"本次模型费用已达上限 ¥{rc.cfg('llm.max_cost_cny', 0)}，"
                                               "剩余的块改用离线规则提取（可在「智能体」页调整上限）", "extract")
                    break
                try:
                    res = await provider.complete_json(system, prompt, EXTRACT_V2_SCHEMA,
                                                       max_tokens=int(rc.cfg("llm.max_tokens", 4096)),
                                                       temperature=float(rc.cfg("llm.temperature", 0.2)), task="extract")
                    rc.add_usage(res.usage.get("input_tokens", 0), res.usage.get("output_tokens", 0), res.cost)
                    data = res.parsed if res.parsed is not None else parse_json_text(res.text)
                    out = ExtractOutV2.model_validate(data)
                    cache.put(key, {"parsed": out.model_dump(), "provider": provider.name, "model": res.model})
                    return out, provider.name, False
                except (ValidationError, ValueError, TypeError) as exc:
                    if attempt == 0:
                        prompt = (user + f"\n\n你上一次的输出没有通过校验：{str(exc)[:300]}\n"
                                  "请严格按照要求的 JSON 结构重新输出，只输出 JSON。")
                        continue
                    rc.log.warn("DECODER", f"群「{chunk.group_name}」块 {chunk.id} 两次输出都不合格，改用离线规则提取", "extract")
                except LLMError as exc:
                    rc.log.warn("DECODER", f"模型调用失败：{exc}；块 {chunk.id} 改用离线规则提取", "extract")
                    break
    res = await offline.complete_json("", "", task="extract_v2", context=offline_context(chunk))
    return ExtractOutV2.model_validate(res.parsed), "offline", False


async def run(rc: RunContext) -> StageResult:
    app = rc.app
    resolved = resolve_provider(app)
    provider = resolved.provider
    rc.llm_provider, rc.llm_reason = provider.name, resolved.reason
    rc.totals["llm_provider"] = provider.name
    if resolved.blocked_by_consent:
        rc.log.warn("DECODER", f"{resolved.reason}（大屏「智能体」页可开启云端同意）", "extract")
    else:
        rc.log.info("DECODER", f"提取引擎：{provider.label}（{resolved.reason}）", "extract")
    tax = load_taxonomy_v2(app.paths.taxonomy, app.paths.taxonomy_v2)
    offline = OfflineProvider({}, {}, taxonomy=tax)
    cache = LLMCache(app.paths.llm_cache, enabled=bool(rc.cfg("llm.cache", True)))
    sem = asyncio.Semaphore(max(1, min(int(rc.cfg("llm.concurrency", 3)), provider.concurrency)))
    total = len(rc.chunks)
    counters: dict[str, Any] = {"done": 0, "candidates": 0, "cache_hits": 0, "fallbacks": 0, "llm_chunks": 0}

    async def one(idx: int, chunk: Chunk) -> list[Candidate]:
        p = provider if chunk.route == "llm" else offline
        out, used, cached = await extract_chunk(rc, chunk, p, offline, cache, sem, tax)
        cands = to_candidates(out, chunk, tax, used)
        counters["done"] += 1
        counters["candidates"] += len(cands)
        counters["cache_hits"] += int(cached)
        counters["llm_chunks"] += int(used != "offline")
        counters["fallbacks"] += int(p.name != "offline" and used == "offline")
        rc.log.info("DECODER", f"解析 群「{chunk.group_name}」块 {counters['done']}/{total} → 候选 {len(cands)} 条", "extract")
        rc.progress("extract", {"chunks_done": counters["done"], "chunks": total, "candidates": counters["candidates"],
                                "tokens_in": rc.totals.get("tokens_in", 0), "tokens_out": rc.totals.get("tokens_out", 0)},
                    f"{counters['done']}/{total}")
        return cands

    results = await asyncio.gather(*(one(i, c) for i, c in enumerate(rc.chunks)))
    rc.candidates = [c for r in results for c in r]
    rc.totals["candidates"] = len(rc.candidates)
    metrics = {"chunks_done": counters["done"], "chunks": total, "candidates": len(rc.candidates),
               "provider": provider.name, "llm_chunks": counters["llm_chunks"], "cache_hits": counters["cache_hits"],
               "fallbacks": counters["fallbacks"], "tokens_in": rc.totals.get("tokens_in", 0),
               "tokens_out": rc.totals.get("tokens_out", 0), "cost_cny": rc.totals.get("cost_cny", 0.0),
               "budget_capped": rc.budget_capped,
               "prompts": sum(len(c.prompts) for c in rc.candidates),
               "privacy_flagged": sum(1 for c in rc.candidates if c.privacy)}
    return StageResult(metrics=metrics, message=f"候选 {len(rc.candidates)} 条")
