"""推送版（docs/V2_KNOWLEDGE.md §3.5）：summary_md ≤ 1800 字，summary_text 为纯文本。
投递时先投文档类通道拿到链接，再用 doc_links 重新生成一次（deliver 阶段和重新投递接口共用）。"""

from __future__ import annotations

import re
from typing import Any

from bureau.pipeline.mdblocks import md_inline

SUMMARY_LIMIT = 1800
RES_KEYS = (("github", "🐙 GitHub", "项"), ("x", "🐦 X", "条"), ("wechat_article", "📑 公众号", "篇"), ("netdisk", "💾 网盘", "套"))


def summary_meta(*, groups: list[str], date_label: str, titles: list[str], resources: list[dict[str, Any]],
                 risky: int, dashboard_url: str, dashboard_base: str, demo: bool) -> dict[str, Any]:
    counts = {k: sum(1 for r in resources if r.get("kind") == k) for k, _, _ in RES_KEYS}
    return {"groups": groups, "date_label": date_label, "titles": titles, "res_counts": counts, "risky": risky,
            "dashboard_url": dashboard_url, "kb_url": f"{dashboard_base.rstrip('/')}/kb", "demo": demo}


def _scope(groups: list[str]) -> str:
    """§3.5 的「{群范围}」：一个群写群名，多个群写「N 群」。"""
    if len(groups) == 1:
        return f"「{groups[0]}」"
    return f" {len(groups)} 群" if groups else ""


def render_summary(meta: dict[str, Any], doc_links: dict[str, str] | None = None, *, title_len: int = 40,
                   max_titles: int | None = None) -> str:
    links = doc_links or {}
    titles = meta.get("titles") or []
    shown = titles if max_titles is None else titles[:max_titles]
    day = str(meta["date_label"]).split("（", 1)[0]               # date_label 带星期，如「2026-10-30（周五）」
    L = [f"今日{_scope(meta.get('groups') or [])}风向标（{day}）已更新！"
         + ("（演示数据）" if meta.get("demo") else ""), ""]
    if titles:
        L.append(f"📌 今日 {len(titles)} 篇深度实操拆解：")
        L += [f"{i}. {md_inline(t if len(t) <= title_len else t[:title_len - 1] + '…')}" for i, t in enumerate(shown, 1)]
        if len(shown) < len(titles):
            L.append(f"…… 等共 {len(titles)} 篇")
    else:
        L.append("📌 今日没有专题文章。")
    c = meta.get("res_counts") or {}
    L += ["", "🔥 外部精选资源：" + " · ".join(f"{label} {c.get(k, 0)} {unit}" for k, label, unit in RES_KEYS)]
    if meta.get("risky"):
        L += ["", f"⚠️ {meta['risky']} 条带风险提示（详见风险板块）"]
    doc = links.get("feishu_doc") or next((v for k, v in links.items() if k != "feishu_wiki" and v), None)
    L += ["", f"👉 今日风向标直达：{doc or meta['dashboard_url']}"]
    kb = links.get("feishu_wiki") or meta.get("kb_url")
    if kb:
        L += ["", f"👉 知识库目录：{kb}"]
    return "\n".join(L)


def build_summary(meta: dict[str, Any], doc_links: dict[str, str] | None = None) -> tuple[str, str]:
    md = render_summary(meta, doc_links)
    for kw in ({"title_len": 28}, {"title_len": 20}, {"title_len": 20, "max_titles": 10}, {"title_len": 16, "max_titles": 5}):
        if len(md) <= SUMMARY_LIMIT:
            break
        md = render_summary(meta, doc_links, **kw)
    md = md[:SUMMARY_LIMIT]
    return md, to_plain(md)


def to_plain(md: str) -> str:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", t)
    t = re.sub(r"\\([\\`*_\[\]|<>])", r"\1", t)
    return re.sub(r"^#+\s*", "", t, flags=re.M)
