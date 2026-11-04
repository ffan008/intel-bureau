"""compose 子步骤 2、3：联网研究与链接增强（B2 的 bureau.research，签名见 docs/V2_KNOWLEDGE.md §5）。

- 研究：每篇专题 research.per_article_queries 个检索词（模型生成，或没有模型时按话题和工具名拼）→ web_search →
  fetch_page 读正文。检索词里不得有群名、昵称、手机号等，代码再清洗一遍。违法高危不做研究。
- 链接增强：GitHub 星数 / 语言 / 简介、X 点赞转发、公众号字数等。提取码只认数据库原文里出现过的。
- 都需要 privacy.cloud_llm_consent=true（检索词和链接会发到外部服务）；没有同意、模块不可用、关闭时跳过并打日志。
- 费用（ctx.cost_usd）按汇率折成人民币计入 rc.totals，受 llm.max_cost_cny 上限约束。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from bureau.core.nlp import NLP_INSTANCE
from bureau.core.textutil import URL_RE, desensitize, norm_url, truncate
from bureau.llm.base import parse_json_text
from bureau.llm.prompts import render_prompt
from bureau.llm.schemas import QUERIES_SCHEMA, QueriesOut
from bureau.pipeline.b2 import research_api, scoped_secrets
from bureau.pipeline.models import Item, RunContext
from bureau.pipeline.risk import is_illegal

CALL_TIMEOUT = 60.0
_PII = ["phone", "email", "idcard", "bankcard", "wechat_id"]


def forbidden_names(rc: RunContext, tools: set[str]) -> list[str]:
    """群名、别名、发言人昵称（长度 ≥ 2，且不是工具名）。"""
    names = {str(g.get("name") or "") for g in rc.groups} | {str(g.get("alias") or "") for g in rc.groups}
    names |= {m.sender for m in rc.clean} | {m.group_name for m in rc.clean}
    low_tools = {t.lower() for t in tools}
    return sorted((n for n in names if len(n.strip()) >= 2 and n.strip().lower() not in low_tools),
                  key=len, reverse=True)


def clean_query(q: str, names: list[str]) -> str:
    """检索词清洗：去掉群名、昵称、手机号、微信号、邮箱、链接，以及脱敏占位符。"""
    t = URL_RE.sub(" ", q or "")
    t, _ = desensitize(t, _PII)
    t = re.sub(r"\[(?:手机号|邮箱|身份证|银行卡|微信号)\]", " ", t)
    for n in names:
        if n and n in t:
            t = t.replace(n, " ")
    t = re.sub(r"\s+", " ", t).strip(" ，,。：:")
    return truncate(t, 60) if len(t) >= 2 else ""


def offline_queries(it: Item, n: int) -> list[str]:
    base = it.topic or re.sub(r"[：:，,。].*$", "", it.title)
    out = [base]
    for tool in it.tools[:2]:
        if tool.lower() not in base.lower():
            out.append(f"{tool} {base}")
    kws = [k for k in NLP_INSTANCE.extract_keywords([it.title, it.summary], top_k=4) if k.lower() not in base.lower()]
    if kws:
        out.append(f"{base} {' '.join(kws[:2])}")
    out.append(f"{base} 教程")
    return list(dict.fromkeys(out))[:n]


def consent_ok(rc: RunContext) -> bool:
    return bool(rc.cfg("privacy.cloud_llm_consent", False))


def make_ctx(rc: RunContext, mod: Any) -> Any:
    secrets = scoped_secrets(rc.app.config.secrets_tree(), "research", "llm.openai_compat")
    return mod.ResearchContext(settings=rc.settings, secrets=secrets, data_dir=rc.app.paths.data,
                               max_searches=int(rc.cfg("research.max_searches", 30) or 0),
                               max_fetches=int(rc.cfg("research.max_fetches", 30) or 0),
                               logger=logging.getLogger("bureau.research"))


def charge(rc: RunContext, ctx: Any, last_usd: list[float]) -> None:
    """把研究模块累计的美元费用增量折成人民币记进 rc.totals（同时受单次费用上限约束）。"""
    usd = float(getattr(ctx, "cost_usd", 0.0) or 0.0)
    delta = max(0.0, usd - last_usd[0])
    last_usd[0] = usd
    if delta:
        rc.add_usage(0, 0, delta * float(rc.cfg("llm.fx_usd_cny", 7.2) or 7.2))
    rc.totals["research_cost_cny"] = round(usd * float(rc.cfg("llm.fx_usd_cny", 7.2) or 7.2), 4)


async def llm_queries(rc: RunContext, provider: Any, feats: list[Item], n: int) -> dict[str, list[str]]:
    data = [{"id": it.id, "title": it.title, "topic": it.topic, "tools": it.tools[:6], "tags": it.tags[:6],
             "summary": truncate(it.summary, 200)} for it in feats]
    system, user = render_prompt(rc.app.paths.prompts, "research_queries",
                                 {"data": json.dumps(data, ensure_ascii=False), "per_article": n})
    res = await provider.complete_json(system, user, QUERIES_SCHEMA, max_tokens=1500, temperature=0.2,
                                       task="research_queries")
    rc.add_usage(res.usage.get("input_tokens", 0), res.usage.get("output_tokens", 0), res.cost)
    out = QueriesOut.model_validate(res.parsed if res.parsed is not None else parse_json_text(res.text))
    return {p.id: p.queries for p in out.plans}


def research_gate(rc: RunContext, provider: Any) -> tuple[Any, str]:
    """返回 (research 模块, 跳过原因)。模块为 None 时调用方跳过研究。"""
    if not rc.cfg("research.enabled", True) or str(rc.cfg("research.provider", "deepseek")) == "none":
        return None, "设置里关闭了联网研究"
    if not consent_ok(rc):
        return None, "未同意使用云端服务（联网搜索要求 privacy.cloud_llm_consent=true）"
    if provider is None or getattr(provider, "name", "offline") == "offline":
        return None, "没有可用的模型（扩展研究需要模型把检索结果写成结论）"
    mod, why = research_api()
    if mod is None:
        return None, why
    return mod, ""


async def run_research(rc: RunContext, provider: Any, ctx_holder: dict[str, Any]) -> dict[str, Any]:
    feats = [it for it in rc.items if it.is_feature and not is_illegal(it)]
    stats = {"queries": 0, "searches": 0, "fetches": 0, "hits": 0, "skipped": ""}
    mod, why = research_gate(rc, provider)
    if mod is None:
        stats["skipped"] = why
        rc.log.info("WRITER", f"跳过扩展研究：{why}", "compose")
        return stats
    n = max(1, min(3, int(rc.cfg("research.per_article_queries", 2) or 2)))
    try:
        ctx = ctx_holder.setdefault("ctx", make_ctx(rc, mod))
    except Exception as exc:                                         # noqa: BLE001
        stats["skipped"] = f"研究上下文创建失败：{exc}"
        rc.log.warn("WRITER", f"跳过扩展研究：{stats['skipped']}", "compose")
        return stats
    last = ctx_holder.setdefault("usd", [0.0])
    plans: dict[str, list[str]] = {}
    try:
        plans = await llm_queries(rc, provider, feats, n)
    except Exception as exc:                                         # noqa: BLE001
        rc.log.warn("WRITER", f"检索词生成失败，改按话题和工具名拼检索词：{exc}", "compose")
    names = forbidden_names(rc, {t for it in rc.items for t in it.tools})
    max_s, max_f = int(rc.cfg("research.max_searches", 30) or 0), int(rc.cfg("research.max_fetches", 30) or 0)
    for it in feats:
        qs = [clean_query(q, names) for q in (plans.get(it.id) or offline_queries(it, n))]
        qs = [q for q in dict.fromkeys(qs) if q][:n]
        stats["queries"] += len(qs)
        refs: list[dict[str, Any]] = []
        for q in qs:
            if stats["searches"] >= max_s or rc.budget_exhausted()[0]:
                break
            try:
                hits = await asyncio.wait_for(mod.web_search(ctx, q, count=5), CALL_TIMEOUT)
            except Exception as exc:                                 # noqa: BLE001
                rc.log.warn("WRITER", f"检索「{q}」失败：{exc or '超时'}", "compose")
                continue
            finally:
                stats["searches"] += 1
                charge(rc, ctx, last)
            for h in (hits or [])[:3]:
                url = str(getattr(h, "url", "") or "")
                if not url.startswith(("http://", "https://")) or any(norm_url(url) == norm_url(r["url"]) for r in refs):
                    continue
                excerpt = str(getattr(h, "content", None) or getattr(h, "summary", "") or "")
                if stats["fetches"] < max_f and not rc.budget_exhausted()[0] and len(refs) < 2:
                    try:
                        page = await asyncio.wait_for(mod.fetch_page(ctx, url, max_chars=6000), CALL_TIMEOUT)
                        if getattr(page, "ok", False) and getattr(page, "markdown", ""):
                            excerpt = page.markdown
                    except Exception:                                # noqa: BLE001
                        pass
                    finally:
                        stats["fetches"] += 1
                        charge(rc, ctx, last)
                refs.append({"n": len(refs) + 1, "title": str(getattr(h, "title", "") or url)[:80], "url": url,
                             "site": getattr(h, "site", None), "excerpt": truncate(excerpt.strip(), 1500), "query": q})
                if len(refs) >= 5:
                    break
        it.research = refs
        stats["hits"] += len(refs)
    rc.totals["research_searches"] = max(stats["searches"], int(getattr(ctx, "used_searches", 0) or 0))
    rc.totals["research_fetches"] = max(stats["fetches"], int(getattr(ctx, "used_fetches", 0) or 0))
    rc.log.info("WRITER", f"扩展研究：{len(feats)} 篇专题，检索 {stats['searches']} 次、读取网页 {stats['fetches']} 篇，"
                          f"得到参考资料 {stats['hits']} 条；费用 ¥{rc.totals.get('research_cost_cny', 0):g}", "compose")
    return stats


async def run_enrich(rc: RunContext, ctx_holder: dict[str, Any]) -> dict[str, Any]:
    links = [x for it in rc.items if not is_illegal(it) for x in it.links]
    stats = {"links": len(links), "enriched": 0, "skipped": ""}
    if not links:
        return stats
    if not rc.cfg("research.enabled", True):
        stats["skipped"] = "设置里关闭了联网研究"
    elif not consent_ok(rc):
        stats["skipped"] = "未同意使用云端服务"
    else:
        mod, why = research_api()
        if mod is None:
            stats["skipped"] = why
    if stats["skipped"]:
        rc.log.info("WRITER", f"跳过链接增强（{stats['skipped']}）：{len(links)} 个链接只按规则分类", "compose")
        return stats
    try:
        ctx = ctx_holder.setdefault("ctx", make_ctx(rc, mod))
    except Exception as exc:                                         # noqa: BLE001
        rc.log.warn("WRITER", f"跳过链接增强：研究上下文创建失败：{exc}", "compose")
        return stats
    last = ctx_holder.setdefault("usd", [0.0])
    skip_kind = {k for k, on in (("github", rc.cfg("research.github_enrich", True)), ("x", rc.cfg("research.x_enrich", True)))
                 if not on}
    raw_of = {m.ref: (m.raw_text or m.text) for m in rc.clean}
    uniq: dict[str, list[dict[str, Any]]] = {}
    for x in links:
        if x.get("kind") not in skip_kind:
            uniq.setdefault(norm_url(x["url"]), []).append(x)
    sem = asyncio.Semaphore(4)

    async def one(group: list[dict[str, Any]]) -> None:
        x0 = group[0]
        context = raw_of.get(x0.get("msg", ""), "")
        async with sem:
            try:
                meta = await asyncio.wait_for(mod.enrich_link(ctx, x0["url"], context_text=context), CALL_TIMEOUT)
            except Exception:                                        # noqa: BLE001
                return
            finally:
                charge(rc, ctx, last)
        if not getattr(meta, "ok", False):
            return
        stats["enriched"] += 1
        for x in group:
            if getattr(meta, "kind", None):
                x["kind"] = meta.kind
            x["title"] = x.get("title") or (meta.title or "")
            x["description"] = meta.description or ""
            x["meta"] = dict(meta.meta or {})
            code = getattr(meta, "code", None)
            if not x.get("code") and code and code in raw_of.get(x.get("msg", ""), ""):   # 只认原文里出现过的提取码
                x["code"] = code

    await asyncio.gather(*(one(g) for g in list(uniq.values())[:60]))
    rc.log.info("WRITER", f"链接增强：{len(uniq)} 个链接，补全元数据 {stats['enriched']} 个", "compose")
    return stats
