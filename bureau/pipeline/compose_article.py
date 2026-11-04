"""compose 子步骤 4：写专题文章。

模型（config/prompts/article.md）只输出结构化 JSON 里的文字部分；序号、标题行、来源、群内原话、提示词原文、链接、
提取码、资源、数据点和免责声明都由代码从原文填进 §3.2 模板（article_blocks）。
没有模型、未同意上云、费用到顶或输出不合格时用离线模板：不写扩展研究，其余照常（全部摘自原文）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from pydantic import ValidationError

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.constants import DISCLAIMER, ILLEGAL_NOTE
from bureau.core.textutil import number_supported, numbers_in, truncate
from bureau.core.timeutil import window_label
from bureau.llm.base import LLMError, parse_json_text
from bureau.llm.cache import LLMCache, cache_key
from bureau.llm.prompts import render_prompt
from bureau.llm.schemas import ARTICLE_SCHEMA, ArticleOut
from bureau.pipeline import mdblocks as mb
from bureau.pipeline.models import Item, RunContext
from bureau.pipeline.risk import is_illegal

KIND_LABELS = {"github": "GitHub", "x": "X", "wechat_article": "公众号", "netdisk": "网盘", "video": "视频",
               "doc": "文档", "web": "网页", "other": "其它"}


def plat_label(p: str) -> str:
    try:
        return PLATFORM_LABELS[Platform(p)]
    except (ValueError, KeyError):
        return str(p or "")


def when(s: str | None) -> str:
    return (s or "")[5:16].replace("T", " ")


def src_line(e: dict[str, Any]) -> str:
    return f"{plat_label(e.get('platform', ''))}·{e.get('group_name', '')}·{e.get('sender', '')}·{when(e.get('sent_at'))}"


def article_sources(it: Item) -> list[dict[str, Any]]:
    seen, out = set(), []
    default_platform = it.sources[0]["platform"] if it.sources else ""
    for e in [*it.evidence, *it.prompts, *it.links, *it.data_points]:
        k = (e.get("group_name"), e.get("sender") or e.get("shared_by"))
        if k in seen or not k[1]:
            continue
        seen.add(k)
        out.append({"group_name": e.get("group_name") or "", "platform": e.get("platform") or default_platform,
                    "sender": k[1], "sent_at": e.get("sent_at") or ""})
    return out


def _flag_numbers(text: str, source: str) -> str:
    bad = [n for n in numbers_in(text) if not number_supported(n, source)]
    return text + "（待核实）" if bad else text


def _group_name(it: Item, key: str) -> str:
    return next((s["group_name"] for s in it.sources if s["group_key"] == key), "")


# ---------------- 离线模板 ----------------
def offline_article(it: Item, research_note: str) -> dict[str, Any]:
    illegal = is_illegal(it)
    background = []
    for pt in it.points[:4]:
        g = _group_name(it, pt.get("group_key", ""))
        summary = pt["summary"]
        lead = "" if summary.startswith(pt["title"][:8]) else f"{pt['title']}："     # 摘要本身就以标题开头时不重复
        background.append(f"「{g}」：{lead}{summary}" if g else f"{lead}{summary}")
    practice, kind = (list(it.sop_steps) or list(it.steps)), "steps"
    if not practice and not illegal:
        practice, kind = [p["hook"] for p in it.points if p.get("hook") and p["hook"] != p["title"]][:5], "points"
    people, groups = len(it.participants), len(it.sources)
    scope = f"整理自 {people} 位群友在 {groups} 个群的讨论，未经独立验证。"
    if it.unverified:
        scope += f"数字 {'、'.join(it.unverified)} 在原文中找不到出处，使用前请核实。"
    cost = "；".join(f"{d['label'] or '数字'} {d['value']}{d['unit']}" for d in it.data_points[:4])
    return {"title": it.title, "hook": it.hook, "background": background, "quote_refs": [], "practice": practice,
            "practice_kind": kind, "research": [], "research_note": research_note, "scope": scope,
            "cost": f"群友自述：{cost}。" if cost else "原文没有给出成本或收益数字。",
            "risk_note": risk_note_of(it), "media_notes": {}, "provider": "offline"}


def risk_note_of(it: Item) -> str:
    flags = [f for f in it.risk_flags if f != "未核实"]
    parts = []
    if is_illegal(it):
        parts.append(ILLEGAL_NOTE)
    elif flags:
        parts.append(f"涉及{'、'.join(flags)}：群内讨论照常整理，是否采用请结合平台规则自行判断。")
    if "未核实" in it.risk_flags:
        parts.append("部分说法没有给出来源，使用前请核实。")
    return "".join(parts)


# ---------------- §3.2 模板（代码组装） ----------------
def resource_line(x: dict[str, Any]) -> list[Any]:
    title = x.get("title") or x["url"]
    seg: list[Any] = [f"〔{KIND_LABELS.get(x.get('kind') or 'other', '其它')}〕", mb.link(title, x["url"])]
    if x.get("code"):
        seg += ["  提取码 ", ("code", x["code"])]
    meta = x.get("meta") or {}
    extra = [f"★{meta['stars']}" if meta.get("stars") not in (None, "") else "", str(meta.get("language") or ""),
             f"赞 {meta['likes']}" if meta.get("likes") not in (None, "") else ""]
    extra = [s for s in extra if s]
    who = "·".join(s for s in (x.get("shared_by") or "", x.get("group_name") or "", when(x.get("sent_at"))) if s)
    tail = "；".join(s for s in (" ".join(extra), f"分享：{who}" if who else "") if s)
    return seg + ([f"（{tail}）"] if tail else [])


def article_blocks(it: Item, art: dict[str, Any], sources: list[dict[str, Any]]) -> list[mb.Block]:
    flags = "、".join(it.risk_flags)
    src = "；".join(src_line(s) for s in sources[:4]) + (f" 等 {len(sources)} 处" if len(sources) > 4 else "")
    B: list[mb.Block] = [mb.h(1, f"{it.seq:02d}-{art['title']}"),
                         mb.note(f"分类：{it.category}｜来源：{src or '—'}" + (f"｜{flags}" if flags else ""), "meta"),
                         *mb.p([("b", "一句话"), "：" + art["hook"]])]
    B.append(mb.h(2, "背景与群内讨论"))
    for para in art["background"] or [it.summary]:
        B += mb.p(para)
    by_ref = {e["ref"]: e for e in it.evidence}
    quotes = [by_ref[r] for r in art.get("quote_refs") or [] if r in by_ref] or it.evidence[:3]
    qb = [mb.quote(e["quote"], f"{e['sender']} · {e['group_name']} · {when(e['sent_at'])}") for e in quotes]
    B += qb[:2]
    if len(qb) > 2:
        B.append(mb.details(f"更多群内原话（{len(qb) - 2} 条）", qb[2:]))
    B.append(mb.h(2, "关键做法"))
    if is_illegal(it):
        B += mb.p(ILLEGAL_NOTE)
    elif art["practice"]:
        B.append(mb.ol(art["practice"]) if art.get("practice_kind") == "steps" else mb.ul(art["practice"]))
        if art.get("practice_kind") != "steps":
            B.append(mb.note("原文没有给出编号步骤，以上是要点。"))
    else:
        B += mb.p("原文没有给出明确步骤。")
    B.append(mb.h(2, "提示词 / 参数原文"))
    if it.prompts:
        for x in it.prompts:
            cite = f"{x['sender']} · {x['group_name']} · {when(x['sent_at'])}"
            B.append(mb.note(f"{x.get('purpose') or '原文'}（{cite}）" + ("" if x.get("verbatim", True) else
                                                                       "；原文含手机号等个人信息，已脱敏"), "meta"))
            B.append(mb.code(x["text"]))
    else:
        B += mb.p("本话题没有提示词或参数原文。")
    B.append(mb.h(2, "扩展研究"))
    if art["research"]:
        for f in art["research"]:
            seg: list[Any] = [f["text"], *(mb.ref(n) for n in f["refs"])]
            if f.get("conflict"):
                seg.append(f"（与群内说法不同：{f['conflict']}）")
            B += mb.p(seg)
    else:
        B += mb.p(art.get("research_note") or "本次未做联网扩展。")
    B.append(mb.h(2, "资源"))
    res_lines = [resource_line(x) for x in it.links]
    imgs = [m for m in it.media if m["kind"] == "image" and m.get("asset")]
    docs = [m for m in it.media if m["kind"] == "file"]
    if res_lines:
        B.append(mb.ul(res_lines))
    for m in imgs:
        cap = art.get("media_notes", {}).get(m.get("name") or m["ref"]) or m.get("why") or ""
        B.append(mb.img(m["asset"], m.get("name") or "群内图片", f"{cap}（{m['sender']} · {when(m['sent_at'])}）"))
    for m in docs:
        pts = m.get("points") or []
        line = f"文档《{m.get('name') or m['ref']}》（{m['sender']} · {when(m['sent_at'])}）"
        B += mb.p(line + ("：" + "；".join(pts[:4]) if pts else f"：{m.get('note') or '未读取正文'}"))
    if it.media and not imgs and any(m["kind"] == "image" for m in it.media):
        B.append(mb.note("图片见工作台「图片与文档」板块。"))
    if not (res_lines or it.media):
        B += mb.p("本话题没有分享链接或附件。")
    B.append(mb.h(2, "适用范围、成本与数据"))
    B += mb.p(art["scope"] or "适用范围见群内讨论。")
    if it.data_points:
        B.append(mb.ul([f"{d['label'] or '数字'}：{d['value']}{d['unit']}（群友自述，非平台口径；{d['sender']} · "
                        f"{when(d['sent_at'])}）" for d in it.data_points[:6]]))
    if art.get("cost"):
        B += mb.p(art["cost"])
    B.append(mb.h(2, "风险提示"))
    B += mb.p(f"风险标签：{flags}。{art['risk_note']}" if flags else (art["risk_note"] or "本话题没有风险标签。"))
    B.append(mb.note(DISCLAIMER, "disclaimer"))
    B.append(mb.hr())
    if it.research:
        B += mb.p([("b", "参考")])
        B.append(mb.ol([[r["title"] + " · ", mb.link(r["url"], r["url"])] for r in it.research]))
    else:
        B += mb.p("参考：本文只整理自群内讨论，没有外部资料。")
    return B


# ---------------- 模型 ----------------
def article_input(it: Item) -> dict[str, Any]:
    return {
        "id": it.id, "title": it.title, "topic": it.topic, "category": it.category, "risk_flags": it.risk_flags,
        "points": [{"title": p["title"], "summary": truncate(p["summary"], 300), "group": _group_name(it, p["group_key"]),
                    "steps": p.get("steps") or []} for p in it.points[:6]],
        "evidence": [{"msg": e["ref"], "sender": e["sender"], "group": e["group_name"], "time": when(e["sent_at"]),
                      "quote": e["quote"]} for e in it.evidence],
        "steps": it.steps, "sop_steps": it.sop_steps, "tools": it.tools,
        "prompts": [{"purpose": x.get("purpose") or "", "sender": x["sender"], "chars": len(x["text"])} for x in it.prompts],
        "links": [{"kind": x.get("kind"), "title": x.get("title") or "", "meta": x.get("meta") or {}} for x in it.links],
        "data_points": [{"label": d["label"], "value": d["value"], "unit": d["unit"], "sender": d["sender"]}
                        for d in it.data_points],
        "tool_notes": [{"tool": t["tool"], "scene": t["scene"], "verdict": t["verdict"]} for t in it.tool_notes],
        "media": [{"name": m.get("name") or m["ref"], "kind": m["kind"], "why": m.get("why") or "",
                   "text": truncate(m.get("ocr_text") or m.get("text") or "", 600)} for m in it.media],
        "research": [{"n": r["n"], "title": r["title"], "url": r["url"], "excerpt": truncate(r["excerpt"], 1200)}
                     for r in it.research],
        "unverified_numbers": it.unverified,
    }


def from_llm(out: ArticleOut, it: Item, data_text: str, research_note: str, provider: str) -> dict[str, Any]:
    refs_ok = {r["n"] for r in it.research}
    research = []
    for f in out.research:
        refs = [n for n in f.refs if n in refs_ok]
        if refs and f.text.strip():
            research.append({"text": _flag_numbers(f.text.strip(), data_text), "refs": refs,
                             "conflict": _flag_numbers(f.conflict.strip(), data_text)})
    title = out.title.strip() if 2 <= len(out.title.strip()) <= 30 else it.title
    if [n for n in numbers_in(title) if not number_supported(n, data_text)]:
        title = it.title
    names = {m.get("name") or m["ref"] for m in it.media}
    return {"title": title, "hook": _flag_numbers(out.hook.strip() or it.hook, data_text),
            "background": [_flag_numbers(b, data_text) for b in out.background if b.strip()][:4],
            "quote_refs": [r for r in out.quote_msgs if any(e["ref"] == r for e in it.evidence)][:4],
            "practice": [] if is_illegal(it) else [_flag_numbers(x, data_text) for x in out.practice][:12],
            "practice_kind": "steps", "research": research,
            "research_note": "" if research else (research_note or "检索结果里没有与群内讨论直接相关的内容。"),
            "scope": _flag_numbers(out.scope.strip(), data_text), "cost": _flag_numbers(out.cost.strip(), data_text),
            "risk_note": _flag_numbers(out.risk_note.strip(), data_text) or risk_note_of(it),
            "media_notes": {n.name: n.note for n in out.media_notes if n.name in names}, "provider": provider}


async def llm_article(rc: RunContext, provider: Any, it: Item, cache: LLMCache, sem: asyncio.Semaphore,
                      research_note: str) -> dict[str, Any] | None:
    data_text = json.dumps(article_input(it), ensure_ascii=False)
    system, user = render_prompt(rc.app.paths.prompts, "article",
                                 {"data": data_text, "window": window_label(rc.start, rc.end, rc.tz)})
    key = cache_key("article", provider.name, provider.model, system, user)
    hit = cache.get(key)
    out: ArticleOut | None = None
    if hit is not None:
        try:
            out = ArticleOut.model_validate(hit["parsed"])
        except (ValidationError, KeyError, TypeError):
            out = None
    if out is None:
        prompt = user
        async with sem:
            for attempt in range(2):
                if rc.budget_exhausted()[0]:
                    return None
                res = await provider.complete_json(system, prompt, ARTICLE_SCHEMA,
                                                   max_tokens=int(rc.cfg("llm.max_tokens", 4096)),
                                                   temperature=float(rc.cfg("llm.temperature", 0.2)), task="article")
                rc.add_usage(res.usage.get("input_tokens", 0), res.usage.get("output_tokens", 0), res.cost)
                try:
                    out = ArticleOut.model_validate(res.parsed if res.parsed is not None else parse_json_text(res.text))
                    break
                except (ValidationError, ValueError) as exc:
                    if attempt:
                        raise LLMError(f"专题输出两次都不合格：{str(exc)[:120]}") from exc
                    prompt = user + f"\n\n你上一次的输出没有通过校验：{str(exc)[:300]}\n请只输出符合要求的 JSON。"
        if out is None:
            return None
        cache.put(key, {"parsed": out.model_dump(), "provider": provider.name})
    return from_llm(out, it, data_text, research_note, provider.name)
