"""报告的 12 个板块（docs/V2_KNOWLEDGE.md §3.1，key 与顺序固定）。

每个板块是一组块（mdblocks），同时渲染成 Markdown（sections[key]、full_md）和 HTML（render_html）。
同时生成 API 的 v2 字段：articles（ArticleDTO）、resources（ResourceDTO）、media（MediaDTO）、groups、section_counts。
所有计数、序号由代码算；提示词、链接、提取码来自核验阶段从数据库原文截取的内容。
"""

from __future__ import annotations

from typing import Any

from bureau.core.constants import DISCLAIMER, ILLEGAL_NOTE, RESOURCE_GROUPS, SECTION_KEYS, SECTION_TITLES
from bureau.core.textutil import fmt_int, truncate
from bureau.pipeline import mdblocks as mb
from bureau.pipeline.compose_article import KIND_LABELS, article_blocks, plat_label, src_line, when
from bureau.pipeline.models import Item, RunContext
from bureau.pipeline.risk import has_risk, is_illegal


def is_risky(it: Item) -> bool:
    return has_risk(it.risk_flags) or it.category.startswith("08") or bool(it.unverified)


def flags_text(flags: list[str]) -> str:
    return "".join(f"〔{f}〕" for f in flags)


def who(x: dict[str, Any]) -> str:
    return " · ".join(s for s in (x.get("sender") or x.get("shared_by") or "", x.get("group_name") or "",
                                  when(x.get("sent_at"))) if s)


def legal(items: list[Item]) -> list[Item]:
    return [it for it in items if not is_illegal(it)]


# ---------------- 资源库 ----------------
def collect_resources(items: list[Item]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out = []
    for it in legal(items):
        for x in it.links:
            k = x["url"].strip().rstrip("/").lower()
            if k in seen:
                continue
            seen.add(k)
            d: dict[str, Any] = {"kind": x.get("kind") or "other", "title": x.get("title") or x["url"], "url": x["url"],
                                 "meta": dict(x.get("meta") or {}), "note": x.get("description") or it.title,
                                 "shared_by": x.get("shared_by"), "group_name": x.get("group_name"),
                                 "sent_at": x.get("sent_at"), "item_id": it.id, "risk_flags": list(it.risk_flags)}
            if x.get("code"):
                d["code"] = x["code"]
            out.append({k2: v for k2, v in d.items() if v is not None})
    return out


def _res_rows(kind: str, rows: list[dict[str, Any]]) -> tuple[list[str], list[list[Any]]]:
    def title(r: dict[str, Any]) -> list[Any]:
        return [mb.link(truncate(r["title"], 40), r["url"])] + ([" ⚠"] if has_risk(r.get("risk_flags") or []) else [])

    m = lambda r: r.get("meta") or {}                                  # noqa: E731
    if kind == "github":
        return (["项目", "星数", "语言", "简介", "分享"],
                [[title(r), str(m(r).get("stars", "—")), str(m(r).get("language") or "—"),
                  truncate(r.get("note") or "", 40), who(r)] for r in rows])
    if kind == "x":
        return (["动态", "作者", "点赞 / 转发", "分享"],
                [[title(r), str(m(r).get("author") or "—"),
                  f"{m(r).get('likes', '—')} / {m(r).get('retweets', '—')}", who(r)] for r in rows])
    if kind == "wechat_article":
        return (["文章", "作者", "字数", "摘要", "分享"],
                [[title(r), str(m(r).get("author") or "—"), str(m(r).get("words") or "—"),
                  truncate(r.get("note") or "", 40), who(r)] for r in rows])
    if kind == "netdisk":
        return (["资料", "平台", "提取码", "分享"],
                [[title(r), str(m(r).get("provider") or "—"), [("code", r["code"])] if r.get("code") else "—", who(r)]
                 for r in rows])
    return (["链接", "类型", "说明", "分享"],
            [[title(r), KIND_LABELS.get(r["kind"], "其它"), truncate(r.get("note") or "", 40), who(r)] for r in rows])


def resources_blocks(resources: list[dict[str, Any]]) -> list[mb.Block]:
    B: list[mb.Block] = []
    for key, label, kinds in RESOURCE_GROUPS:
        rows = [r for r in resources if r["kind"] in kinds]
        if not rows:
            continue
        B.append(mb.h(3, f"{label}（{len(rows)}）"))
        headers, body = _res_rows(key, rows)
        B.append(mb.table(headers, body))
    if not B:
        return mb.p("今日没有分享链接。")
    if any(has_risk(r.get("risk_flags") or []) for r in resources):
        B.append(mb.note("⚠ 表示来自带风险标签的话题。" + DISCLAIMER, "disclaimer"))
    return B


def _risk_tail(it: Item) -> list[mb.Block]:
    return [mb.note(f"{flags_text(it.risk_flags)} {DISCLAIMER}", "disclaimer")] if has_risk(it.risk_flags) else []


# ---------------- 提示词 / SOP / 工具 / 数据 / 金句 ----------------
def prompts_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    B: list[mb.Block] = []
    n = 0
    for it in legal(items):
        for x in it.prompts:
            n += 1
            B.append(mb.h(3, f"{n}. {x.get('purpose') or it.title}"))
            B.append(mb.note(f"{who(x)}｜话题：{it.title}" + ("" if x.get("verbatim", True) else
                                                            "｜原文含个人信息，已脱敏"), "meta"))
            B.append(mb.code(x["text"]))
            B += _risk_tail(it)
    return (B or mb.p("今日群里没有出现完整的提示词。")), n


def sops_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    B: list[mb.Block] = []
    n = 0
    for it in legal(items):
        steps = it.sop_steps or (it.steps if len(it.steps) >= 3 else [])
        if not steps:
            continue
        n += 1
        src = "；".join(src_line(e) for e in it.evidence[:2])
        B.append(mb.h(3, f"{n}. {it.title}"))
        B.append(mb.ol(steps))
        B.append(mb.note(("群友验证过的流程" if it.sop_steps else "原文给出的步骤") + f"｜{src}", "meta"))
        B += _risk_tail(it)
    return (B or mb.p("今日没有被验证过的成套做法。")), n


def tools_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    rows = [[t["tool"], t["scene"] or it.title, t["verdict"], who(t)] for it in legal(items) for t in it.tool_notes]
    if not rows:
        named = sorted({t for it in legal(items) for t in it.tools})
        if not named:
            return mb.p("今日没有工具与模型的实测结论。"), 0
        return [mb.note("今日没有成型的实测结论；被讨论到的工具：" + "、".join(named))], 0
    B = [mb.table(["工具 / 模型", "场景", "结论（原文）", "谁 · 时间"], rows, show=10)]
    if any(has_risk(it.risk_flags) and it.tool_notes for it in items):
        B.append(mb.note(DISCLAIMER, "disclaimer"))
    return B, len(rows)


def data_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    rows = []
    for it in legal(items):
        for d in it.data_points:
            rows.append([d["label"] or it.title, f"{d['value']}{d['unit']}", truncate(it.title, 24), who(d)])
    if not rows:
        return mb.p("今日没有群友自述的收益或数据。"), 0
    B = [mb.note("以下数字均为群友自述，非平台口径，未经核实。", "warn"),
         mb.table(["项", "数值", "话题", "谁 · 时间"], rows, show=10)]
    if any(has_risk(it.risk_flags) and it.data_points for it in items):
        B.append(mb.note(DISCLAIMER, "disclaimer"))
    return B, len(rows)


def quotes_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    qs = [(q, it) for it in legal(items) for q in it.quotes]
    if len(qs) < 3:                                    # 原话太少时，用头条话题的第一条证据补
        used = {q["quote"] for q, _ in qs}
        qs += [(e, it) for it in legal(items) if it.is_headline for e in it.evidence[:1] if e["quote"] not in used][:3]
    B = [mb.quote(q["quote"], f"{who(q)}｜{it.title}") for q, it in qs[:20]]
    return (B or mb.p("今日没有可摘录的原话。")), len(B)


# ---------------- 风险与踩坑 ----------------
def risks_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    rs = [it for it in items if is_risky(it)]
    rs.sort(key=lambda it: (not is_illegal(it), it.rank))
    B: list[mb.Block] = []
    for n, it in enumerate(rs, start=1):
        inner: list[mb.Block] = [mb.h(3, f"{n}. {it.title} {flags_text(it.risk_flags)}".strip())]
        inner += mb.p(it.hook if it.hook != it.title else it.summary)
        if it.summary and it.summary != it.hook:
            inner += mb.p(truncate(it.summary, 300))
        for e in it.evidence[:2]:
            inner.append(mb.quote(e["quote"], f"{e['sender']} · {e['group_name']} · {when(e['sent_at'])}"))
        if it.unverified:
            inner.append(mb.note(f"待核实的数字：{'、'.join(it.unverified)}", "warn"))
        if is_illegal(it):
            inner.append(mb.note(ILLEGAL_NOTE, "warn"))
        elif it.is_feature:
            inner.append(mb.note([f"完整内容见专题 {it.seq:02d}「", mb.anchor(it.title, article_anchor(it.seq)), "」。"],
                                 "meta"))
        src = "、".join(f"{plat_label(s['platform'])}·{s['group_name']}" for s in it.sources[:3])
        inner.append(mb.note(f"来源：{src}", "meta"))
        inner.append(mb.note(DISCLAIMER, "disclaimer"))
        B.append(mb.card(inner, "risk illegal" if is_illegal(it) else "risk"))
    return (B or mb.p("今日没有需要特别提示的风险。")), len(rs)


def article_anchor(seq: int) -> str:
    return f"a{int(seq):02d}"


# ---------------- 图片与文档 ----------------
def media_dto(m: dict[str, Any]) -> dict[str, Any]:
    d = {"kind": m["kind"], "name": m.get("name") or m["ref"], "url": m.get("url"), "ocr_text": m.get("ocr_text") or None,
         "summary": m.get("summary") or ("；".join(m.get("points") or []) or None), "why": m.get("why") or None,
         "group_name": m.get("group_name"), "sender": m.get("sender"), "sent_at": m.get("sent_at"),
         "article_seq": m.get("article_seq"), "note": m.get("note") or None}
    return {k: v for k, v in d.items() if v not in (None, "")}


def media_blocks(media: list[dict[str, Any]]) -> list[mb.Block]:
    imgs = [m for m in media if m["kind"] == "image"]
    docs = [m for m in media if m["kind"] == "file"]
    B: list[mb.Block] = []
    if imgs:
        B.append(mb.h(3, f"图片（{len(imgs)}）"))
        cards = []
        for m in imgs:
            inner: list[mb.Block] = []
            if m.get("asset"):
                inner.append(mb.img(m["asset"], m.get("name") or "群内图片"))
            pts = m.get("points") or []
            inner.append(mb.note(f"{m.get('why') or '群内图片'}｜{who(m)}", "meta"))
            if pts:
                inner.append(mb.ul(pts[:4]))
            elif m.get("note"):
                inner.append(mb.note(m["note"]))
            cards.append(mb.card(inner, "thumb"))
        B.append(mb.card(cards, "grid"))
    if docs:
        B.append(mb.h(3, f"文档（{len(docs)}）"))
        for m in docs:
            name = m.get("name") or m["ref"]
            ext = name.rsplit(".", 1)[-1].upper() if "." in name else "文件"
            inner = [mb.h(4, f"{name}（{ext}）"), mb.note(f"{m.get('why') or '群内文件'}｜{who(m)}", "meta")]
            pts = m.get("points") or []
            inner.append(mb.ul(pts[:6]) if pts else mb.note(m.get("note") or "没有读取到正文"))
            B.append(mb.card(inner, "doc"))
    return B or mb.p("今日没有被引用的图片或文档。")


# ---------------- 分群摘要 / 快讯 ----------------
def groups_blocks(digests: list[dict[str, Any]]) -> list[mb.Block]:
    B: list[mb.Block] = []
    for g in digests:
        c = g["counts"]
        inner: list[mb.Block] = [mb.h(3, f"{plat_label(g['platform'])}·{g['group_name']}"), *mb.p(g["summary"])]
        if g["highlights"]:
            inner.append(mb.ol(g["highlights"]))
        inner.append(mb.note(f"消息 {fmt_int(g['messages'])}｜链接 {c['links']}｜提示词 {c['prompts']}｜"
                             f"SOP {c['sops']}｜数据 {c['data']}", "meta"))
        B.append(mb.card(inner, "group"))
    return B or mb.p("今日没有达到摘要门槛的活跃群。")


def overview_blocks(rc: RunContext, items: list[Item], feats: list[Item], n_res: int) -> list[mb.Block]:
    st = rc.stats
    groups = len(st.get("top_groups", []))
    kpis = [("消息", fmt_int(st.get("messages_raw", 0))), ("群", str(groups)), ("情报", str(len(items))),
            ("专题", str(len(feats))), ("资源", str(n_res))]
    B: list[mb.Block] = [*mb.p([("b", "一句话"), "：" + (rc.v2.get("summary") or "今日没有足够的信息形成总结。")])]
    kpi_card = mb.card([mb.card([mb.note(k, "k"), mb.note(v, "v")], "kpi") for k, v in kpis], "kpis")
    kpi_card["md"] = "数据卡：" + " · ".join(f"{k} {v}" for k, v in kpis)
    B.append(kpi_card)
    B.append(mb.h(3, "今日风向"))
    if rc.judgments:
        B.append(mb.ol([[("b", j["text"]), f"（依据：{j.get('basis') or '—'}）"] for j in rc.judgments]))
    else:
        B += mb.p("今日没有足够的信息形成判断。")
    B.append(mb.h(3, f"今日 {len(feats)} 篇专题"))
    if feats:
        B.append(mb.ol([[mb.anchor(it.article.get("title") or it.title, article_anchor(it.seq)),
                         f"｜{it.category}" + (f"｜{flags_text(it.risk_flags)}" if it.risk_flags else "")] for it in feats]))
    else:
        B += mb.p("今日没有适合写成专题的话题。")
    privacy = int(rc.v2.get("privacy_dropped") or 0)
    B.append(mb.note(f"有效消息 {fmt_int(st.get('messages_clean', 0))} / {fmt_int(st.get('messages_raw', 0))}"
                     f"（信噪比 {100 * st.get('snr', 0):.1f}%）" + (f"；隐私内容剔除 {privacy} 条" if privacy else ""), "meta"))
    return B


def article_dto(it: Item, report_id: str) -> dict[str, Any]:
    art = it.article
    return {"id": f"{report_id}-a{it.seq:02d}", "seq": it.seq, "title": art.get("title") or it.title,
            "hook": art.get("hook") or it.hook, "category": it.category, "body_md": art.get("body_md", ""),
            "risk_flags": list(it.risk_flags), "risk_note": art.get("risk_note") or None,
            "sources": [{"group_name": s["group_name"], "platform": s["platform"], "sender": s["sender"],
                         "sent_at": s["sent_at"]} for s in art.get("sources") or []],
            "source_lines": [src_line(s) for s in (art.get("sources") or [])[:6]],
            "images": [m["asset_name"] for m in it.media if m.get("asset_name") and m["kind"] == "image"],
            "kb_id": it.kb_id, "research_refs": [{"n": r["n"], "title": r["title"], "url": r["url"]} for r in it.research],
            "item_id": it.id, "provider": art.get("provider") or "offline"}


def build_sections(rc: RunContext, items: list[Item], report_id: str) -> dict[str, Any]:
    """返回 {blocks: {key: [块]}, articles: [ArticleDTO], resources, media, counts, feats}。
    专题的 body_md（§3.2 模板）也在这里生成：此时图片已经有 assets 相对路径。"""
    feats = sorted((it for it in items if it.is_feature and it.article), key=lambda x: x.seq)
    for it in feats:
        it.article["blocks"] = article_blocks(it, it.article, it.article.get("sources") or [])
        it.article["body_md"] = mb.to_md(it.article["blocks"]) + "\n"
    resources = collect_resources(items)
    blocks: dict[str, list[mb.Block]] = {}
    counts: dict[str, int] = {}
    blocks["overview"] = overview_blocks(rc, items, feats, len(resources))
    counts["overview"] = len(rc.judgments)
    blocks["articles"] = [b for it in feats for b in (it.article.get("blocks") or [])] or \
        mb.p("今日没有适合写成专题的话题。")
    counts["articles"] = len(feats)
    blocks["resources"], counts["resources"] = resources_blocks(resources), len(resources)
    for key, fn in (("prompts", prompts_blocks), ("sops", sops_blocks), ("tools", tools_blocks), ("data", data_blocks),
                    ("risks", risks_blocks), ("quotes", quotes_blocks)):
        blocks[key], counts[key] = fn(items)
    blocks["media"], counts["media"] = media_blocks(rc.media), len(rc.media)
    blocks["groups"], counts["groups"] = groups_blocks(rc.digests), len(rc.digests)
    blocks["briefs"], counts["briefs"] = briefs_blocks(items)
    return {"blocks": {k: blocks[k] for k in SECTION_KEYS}, "counts": {k: counts[k] for k in SECTION_KEYS},
            "articles": [article_dto(it, report_id) for it in feats if it.article], "resources": resources,
            "media": [media_dto(m) for m in rc.media], "feats": feats}


def section_markdown(model: dict[str, Any]) -> dict[str, str]:
    """sections[key]：板块正文 Markdown（不含板块标题；板块内小标题从 ### 起，专题从 ## 起）。"""
    out = {}
    for k in SECTION_KEYS:
        hoff = 1 if k == "articles" else 0
        out[k] = mb.to_md(model["blocks"][k], hoff)
    return out


def full_markdown(title: str, header: str, demo: bool, model: dict[str, Any]) -> str:
    parts = [f"# {title}", "", f"> {header}", ""]
    if demo:
        parts += ["> 本报告由演示数据生成，群名、人物和对话均为虚构。", ""]
    for k in SECTION_KEYS:
        parts += [f"## {SECTION_TITLES[k]}（{model['counts'][k]}）", "", mb.to_md(model["blocks"][k], 2 if k == "articles" else 0), ""]
    return "\n".join(parts).rstrip() + "\n"


def briefs_blocks(items: list[Item]) -> tuple[list[mb.Block], int]:
    rest = [it for it in items if not it.is_feature and not is_risky(it)]
    lines = []
    for it in rest:
        src = "、".join(s["group_name"] for s in it.sources[:2])
        hook = "" if it.hook == it.title else "：" + truncate(it.hook, 40)
        lines.append(f"{it.title}{hook}（{src}）")
    return ([mb.ol(lines)] if lines else mb.p("今日没有其余快讯。")), len(lines)
