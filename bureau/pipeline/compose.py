"""阶段 9 compose（阶段名不变，内部按 docs/V2_KNOWLEDGE.md §4 分子步骤）：
1. 媒体：取回被引用的图片和文件，图片 OCR，文档解析出正文（B2 bureau.media）；
2. 研究：每篇专题生成检索词 → web_search → fetch_page（B2 bureau.research）；
3. 链接增强：enrich_link；
4. 写专题：article.md 输出结构化 JSON，代码套 §3.2 模板（body_md 在 render 阶段生成，那时图片才有相对路径）；
5. 今日总览与分群摘要：digest.md。
每个子步骤单独兜底：一个失败不影响其它子步骤。没有模型时用离线模板：不写扩展研究，其余照常。
云端同意与单次费用上限照旧生效；研究的费用计入 rc.totals。
"""

from __future__ import annotations

import asyncio
from typing import Any

from bureau.llm.cache import LLMCache
from bureau.llm.factory import resolve_provider
from bureau.pipeline.compose_article import article_sources, llm_article, offline_article
from bureau.pipeline.compose_digest import run_digest
from bureau.pipeline.compose_media import run_media
from bureau.pipeline.compose_research import research_gate, run_enrich, run_research
from bureau.pipeline.models import Item, RunContext, StageResult


def feature_v1(art: dict[str, Any]) -> dict[str, Any]:
    """IntelItemDTO.feature（v1 字段，只增不改）：background / practice / scope。"""
    return {"background": "".join(art.get("background") or [])[:600], "practice": list(art.get("practice") or []),
            "scope": art.get("scope") or ""}


async def write_articles(rc: RunContext, provider: Any, research_note: str) -> dict[str, Any]:
    feats = sorted((it for it in rc.items if it.is_feature), key=lambda x: x.seq)
    stats = {"articles": len(feats), "llm": 0, "offline": 0}
    use_llm = provider is not None and getattr(provider, "name", "offline") != "offline"
    cache = LLMCache(rc.app.paths.llm_cache, enabled=bool(rc.cfg("llm.cache", True)))
    sem = asyncio.Semaphore(max(1, min(int(rc.cfg("llm.concurrency", 3)), getattr(provider, "concurrency", 1))))

    async def one(it: Item) -> None:
        note = research_note if not it.research else ""
        art = None
        if use_llm:
            try:
                art = await llm_article(rc, provider, it, cache, sem, note)
            except Exception as exc:                                 # noqa: BLE001
                rc.log.warn("WRITER", f"专题 {it.seq:02d}「{it.title}」改用离线模板：{exc}", "compose")
        if art is None:
            art = offline_article(it, note or "本次未做联网扩展。")
            stats["offline"] += 1
        else:
            stats["llm"] += 1
        art["sources"] = article_sources(it)
        it.article = art
        it.feature = feature_v1(art)

    await asyncio.gather(*(one(it) for it in feats))
    return stats


async def run(rc: RunContext) -> StageResult:
    resolved = resolve_provider(rc.app)
    provider = resolved.provider if resolved.provider.name != "offline" else None
    if provider is not None and rc.budget_exhausted()[0]:
        rc.log.warn("WRITER", f"本次模型费用已达上限 ¥{rc.cfg('llm.max_cost_cny', 0)}：专题和总览改用离线模板", "compose")
        provider = None
    metrics: dict[str, Any] = {}
    holder: dict[str, Any] = {}
    steps = (("media", lambda: run_media(rc)), ("research", lambda: run_research(rc, provider, holder)),
             ("enrich", lambda: run_enrich(rc, holder)))
    for name, fn in steps:
        try:
            res = await fn()
            metrics.update({f"{name}_{k}": v for k, v in res.items() if not isinstance(v, str) or v})
        except Exception as exc:                                     # noqa: BLE001
            rc.log.warn("WRITER", f"子步骤 {name} 出错，已跳过：{exc}", "compose")
            metrics[f"{name}_error"] = str(exc)[:120]
    _mod, gate_reason = research_gate(rc, provider)
    try:
        metrics.update(await write_articles(rc, provider, gate_reason and f"本次未做联网扩展：{gate_reason}。"))
    except Exception as exc:                                         # noqa: BLE001
        rc.log.warn("WRITER", f"写专题出错，全部改用离线模板：{exc}", "compose")
        for it in rc.items:
            if it.is_feature and not it.article:
                it.article = offline_article(it, "本次未做联网扩展。")
                it.article["sources"] = article_sources(it)
                it.feature = feature_v1(it.article)
    try:
        metrics.update({f"digest_{k}": v for k, v in (await run_digest(rc, provider)).items()})
    except Exception as exc:                                         # noqa: BLE001
        rc.log.warn("WRITER", f"总览出错：{exc}", "compose")
        rc.judgments = rc.judgments or []
    rc.totals["cost_cny"] = round(float(rc.totals.get("cost_cny", 0.0)), 4)
    feats = sum(1 for it in rc.items if it.is_feature)
    rc.log.info("WRITER", f"写出专题 {feats} 篇（模型 {metrics.get('llm', 0)} · 离线模板 {metrics.get('offline', 0)}）、"
                          f"今日风向 {len(rc.judgments)} 条", "compose")
    metrics.update({"judgments": len(rc.judgments), "features": feats,
                    "source": provider.name if provider is not None else "offline"})
    return StageResult(metrics=metrics, message=f"专题 {feats} · 风向 {len(rc.judgments)}")
