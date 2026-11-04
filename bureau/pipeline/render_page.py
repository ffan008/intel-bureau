"""v2 当日 HTML（docs/V2_KNOWLEDGE.md §3.1）：自包含、深色、可打印；左侧板块标签，右侧内容区（最大 760px）。

切换用纯 CSS：每个板块是 <section id=key class=pane>，导航是 <a href="#key">；:target 显示被选中的板块，
「今日总览」放在最后，靠 .pane:target ~ #overview 在选中别的板块时隐藏（不支持 :has 的浏览器也能切换）。
不含 <script>，不引用外部资源；图片用相对路径引用同目录下的 <report_id>_assets/。
"""

from __future__ import annotations

from typing import Any

from bureau.core.constants import SECTION_KEYS, SECTION_TITLES
from bureau.pipeline import mdblocks as mb
from bureau.pipeline.mdblocks import e
from bureau.pipeline.render_css import CSS_V2, nav_css
from bureau.pipeline.sections import article_anchor

LEADS = {
    "overview": "一句话总结、今日风向、数据卡和今日专题。",
    "articles": "跨群合并后的话题写成的专题文章，点开看全文。提示词、链接、提取码均从群聊原文照录。",
    "resources": "群里分享的外部资源，按类型分组；网盘带提取码，均写明分享人、群和时间。",
    "prompts": "群里出现的完整提示词，一字不改。",
    "sops": "被群友验证过的做法，编号步骤。",
    "tools": "工具与模型的选型、对比和实测结论（谁、在什么场景、结论）。",
    "data": "群友自述的数字，非平台口径。",
    "risks": "踩坑经验，以及所有带风险标签的话题（含违法高危，只记录）。",
    "quotes": "有判断力的群内原话。",
    "media": "有用的图片（OCR 要点）和文档（正文提炼）。",
    "groups": "活跃群各一张卡：一句话总结、三件事、各项计数。",
    "briefs": "没有进专题的其余情报，每条一行。",
}


def _badges(a: dict[str, Any]) -> str:
    out = [f'<span class="badge">{e(a["category"])}</span>']
    for f in a["risk_flags"]:
        out.append(f'<span class="badge {"illegal" if f == "违法高危" else "risk"}">{e(f)}</span>')
    return "".join(out)


def article_cards(model: dict[str, Any]) -> str:
    out = []
    for it, a in zip(model["feats"], model["articles"]):
        blocks = list(it.article.get("blocks") or [])
        body = blocks[2:] if len(blocks) > 2 and blocks[0]["t"] == "h" and blocks[1]["t"] == "note" else blocks
        src = "；".join(a["source_lines"][:3])
        out.append(
            f'<details class="art" id="{article_anchor(a["seq"])}"><summary><span class="seq">{a["seq"]:02d}</span>'
            f'<span class="t">{e(a["title"])}</span><span class="h">{e(a["hook"])}</span>{_badges(a)}'
            f'<span class="meta">来源：{e(src)}</span> <span class="more">展开全文</span></summary>'
            f'<div class="body">{mb.to_html(body, 1)}</div></details>')
    return "".join(out) or '<p class="muted">今日没有适合写成专题的话题。</p>'


def render_page(ctx: dict[str, Any], model: dict[str, Any]) -> str:
    counts = model["counts"]
    nav = "".join(f'<a href="#{k}">{e(SECTION_TITLES[k])}<span class="n">{counts[k]}</span></a>' for k in SECTION_KEYS)
    panes = []
    order = [k for k in SECTION_KEYS if k != "overview"] + ["overview"]       # 总览放最后：没有选中时默认显示它
    for k in order:
        body = article_cards(model) if k == "articles" else mb.to_html(model["blocks"][k])
        panes.append(f'<section class="pane" id="{k}"><h2>{e(SECTION_TITLES[k])}<span class="n">{counts[k]}</span></h2>'
                     f'<p class="lead">{e(LEADS[k])}</p>{body}</section>')
    demo = '<span class="demo">本报告由演示数据生成，群名、人物和对话均为虚构。</span>' if ctx["demo"] else ""
    top = (f'<header class="top"><h1>{e(ctx["title"])}</h1><p class="meta">{e(ctx["header"])}</p>{demo}</header>')
    footer = (f"<footer>情报局工作台 · 报告编号 {e(ctx['report_id'])} · 本文件可离线打开（图片在同目录的 "
              f"{e(ctx['report_id'])}_assets 文件夹）</footer>")
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(ctx["title"])}</title>'
            f"<style>{CSS_V2}{nav_css(SECTION_KEYS)}</style></head><body><div class=\"layout\">"
            f'<nav class="tabs"><div class="brand">INTEL BUREAU<b>{e(ctx["date_label"])}</b></div>{nav}</nav>'
            f'<main>{top}<div class="panes">{"".join(panes)}</div>{footer}</main></div></body></html>')
