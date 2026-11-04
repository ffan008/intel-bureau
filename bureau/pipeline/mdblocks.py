"""报告内容的块模型：同一份结构渲染成 Markdown（full_md、sections、专题 body_md、知识库）和 HTML（§3.1 页面）。

行内内容是 str，或 str 与 ("link", 文本, url) / ("b", 文本) / ("code", 文本) 组成的列表。
所有原文都经过转义：Markdown 里转义会破坏版式的字符，HTML 里全部转义，链接只允许 http / https。
长段落按句子切成每段不超过 PARA_MAX 字（16px、760px 宽约每行 45 字，4 行约 150 字）。
"""

from __future__ import annotations

import re
from html import escape
from typing import Any, Iterable, Union

Inline = Union[str, list[Any]]
Block = dict[str, Any]
PARA_MAX = 150
_SENT = re.compile(r"(?<=[。！？!?；;])")
_MD_ESC = re.compile(r"([\\`*_\[\]<>])")
_LINE_START = re.compile(r"^(\s*)(#{1,6}\s|>|[-+*]\s|\d+[.)]\s|=+\s*$|-{3,}\s*$)")


# ---------------- 构造 ----------------
def h(level: int, text: Inline, anchor: str | None = None) -> Block:
    return {"t": "h", "level": level, "text": text, "id": anchor}


def p(text: Inline) -> list[Block]:
    """普通段落；纯文本超过 PARA_MAX 字时按句子拆成多段。"""
    if isinstance(text, str):
        return [{"t": "p", "text": s} for s in split_para(text)]
    return [{"t": "p", "text": text}]


def quote(text: Inline, cite: str = "") -> Block:
    return {"t": "quote", "text": text, "cite": cite}


def ol(items: Iterable[Inline]) -> Block:
    return {"t": "ol", "items": list(items)}


def ul(items: Iterable[Inline]) -> Block:
    return {"t": "ul", "items": list(items)}


def code(text: str, lang: str = "") -> Block:
    return {"t": "code", "text": text or "", "lang": lang}


def table(headers: list[str], rows: list[list[Inline]], show: int = 8) -> Block:
    return {"t": "table", "headers": headers, "rows": rows, "show": show}


def details(summary: str, blocks: list[Block], open_: bool = False) -> Block:
    return {"t": "details", "summary": summary, "blocks": blocks, "open": open_}


def note(text: Inline, cls: str = "muted") -> Block:
    return {"t": "note", "text": text, "cls": cls}


def card(blocks: list[Block], cls: str = "", anchor: str | None = None) -> Block:
    return {"t": "card", "blocks": blocks, "cls": cls, "id": anchor}


def img(src: str, alt: str, caption: str = "") -> Block:
    return {"t": "img", "src": src, "alt": alt, "caption": caption}


def hr() -> Block:
    return {"t": "hr"}


def link(text: str, url: str) -> tuple[str, str, str]:
    return ("link", text, url)


def ref(n: int) -> tuple[str, int]:
    """扩展研究的来源标号 [n]（代码生成，只含数字，不转义）。"""
    return ("ref", int(n))


def anchor(text: str, target: str) -> tuple[str, str, str]:
    """页内锚点（HTML 里是 <a href="#target">，Markdown 里只保留文字）。target 只能是字母数字和 -。"""
    return ("anchor", text, re.sub(r"[^A-Za-z0-9-]", "", target))


def split_para(text: str, limit: int = PARA_MAX) -> list[str]:
    t = re.sub(r"\s*\n\s*", " ", (text or "").strip())
    if not t:
        return []
    if len(t) <= limit:
        return [t]
    out, cur = [], ""
    for s in (x for x in _SENT.split(t) if x):
        while len(s) > limit:                                   # 单句太长：在逗号处切，找不到就硬切
            cut = max(s.rfind(c, 0, limit) for c in "，,、 ")
            cut = cut + 1 if cut >= limit // 2 else limit
            if cur:
                out.append(cur)
                cur = ""
            out.append(s[:cut].strip())
            s = s[cut:].strip()
        if len(cur) + len(s) > limit and cur:
            out.append(cur)
            cur = s
        else:
            cur += s
    if cur.strip():
        out.append(cur.strip())
    return [x for x in out if x]


def safe_url(url: str) -> bool:
    return isinstance(url, str) and url.startswith(("http://", "https://")) and not re.search(r"[\s<>\"']", url)


_ASSET = re.compile(r"^[\w.-]+_assets/[\w.-]+$")


# ---------------- Markdown ----------------
def _esc_md(text: str, table: bool = False) -> str:
    t = _MD_ESC.sub(r"\\\1", str(text or "").replace("\r", "").replace("\n", " "))
    return t.replace("|", "\\|") if table else t


def _md_url(url: str) -> str:
    return url.replace("(", "%28").replace(")", "%29").replace(" ", "%20")


def _fence(text: str, minimum: int = 3) -> str:
    runs = [len(m) for m in re.findall(r"`+", text or "")]
    return "`" * max(minimum, (max(runs) + 1) if runs else minimum)


def md_inline(x: Inline, table: bool = False) -> str:
    if isinstance(x, str):
        return _esc_md(x, table)
    out = []
    for seg in x:
        if isinstance(seg, str):
            out.append(_esc_md(seg, table))
        elif seg[0] == "link":
            out.append(f"[{_esc_md(seg[1], table)}]({_md_url(seg[2])})" if safe_url(seg[2]) else _esc_md(seg[1], table))
        elif seg[0] == "anchor":
            out.append(_esc_md(seg[1], table))
        elif seg[0] == "ref":
            out.append(f"[{int(seg[1])}]")
        elif seg[0] == "b":
            out.append(f"**{_esc_md(seg[1], table)}**")
        elif seg[0] == "code":
            f = _fence(seg[1], 1)
            pad = " " if str(seg[1]).startswith("`") or str(seg[1]).endswith("`") else ""
            out.append(f"{f}{pad}{str(seg[1]).replace(chr(10), ' ')}{pad}{f}")
    return "".join(out)


def _guard_line(s: str) -> str:
    """段落开头像 Markdown 结构（# 、> 、- 、1. ）时转义，避免原文注入版式。"""
    m = _LINE_START.match(s)
    if not m:
        return s
    lead, tok = m.group(1), m.group(2)
    num = re.match(r"(\d+)([.)])", tok)
    if num:
        return lead + num.group(1) + "\\" + s[len(lead) + len(num.group(1)):]
    return lead + "\\" + s[len(lead):]


def to_md(blocks: Iterable[Block], hoff: int = 0) -> str:
    lines: list[str] = []
    for b in blocks:
        lines += _md_block(b, hoff)
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def _md_block(b: Block, hoff: int) -> list[str]:
    t = b["t"]
    if t == "h":
        return ["#" * max(1, min(6, b["level"] + hoff)) + " " + md_inline(b["text"]), ""]
    if t == "p":
        return [_guard_line(md_inline(b["text"])), ""]
    if t == "quote":
        return ["> " + md_inline(b["text"]) + (f" —— {_esc_md(b['cite'])}" if b.get("cite") else ""), ""]
    if t in ("ol", "ul"):
        return [(f"{i}. " if t == "ol" else "- ") + md_inline(x) for i, x in enumerate(b["items"], start=1)] + [""]
    if t == "code":
        f = _fence(b["text"])
        return [f + (b.get("lang") or ""), b["text"].rstrip("\n"), f, ""]
    if t == "table":
        out = ["| " + " | ".join(_esc_md(x, True) for x in b["headers"]) + " |",
               "|" + "|".join("---" for _ in b["headers"]) + "|"]
        out += ["| " + " | ".join(md_inline(c, True) for c in row) + " |" for row in b["rows"]]
        return out + [""]
    if t == "details":
        return [f"**{_esc_md(b['summary'])}**", ""] + [ln for x in b["blocks"] for ln in _md_block(x, hoff)]
    if t == "note":
        return ["> " + md_inline(b["text"]), ""]
    if t == "card":
        if b.get("md"):                                  # 只在 HTML 里有版式意义的卡片（如数据卡）给一行文字
            return [_guard_line(_esc_md(b["md"])), ""]
        return [ln for x in b["blocks"] for ln in _md_block(x, hoff)]
    if t == "img":
        ok = _ASSET.match(b["src"] or "")
        return ([f"![{_esc_md(b['alt'])}]({b['src']})"] if ok else []) + \
            ([f"*{_esc_md(b['caption'])}*"] if b.get("caption") else []) + [""]
    if t == "hr":
        return ["---", ""]
    return []


# ---------------- HTML ----------------
def e(x: Any) -> str:
    return escape(str(x if x is not None else ""), quote=True)


def html_inline(x: Inline) -> str:
    if isinstance(x, str):
        return e(x)
    out = []
    for seg in x:
        if isinstance(seg, str):
            out.append(e(seg))
        elif seg[0] == "link":
            out.append(f'<a href="{e(seg[2])}" target="_blank" rel="noopener noreferrer">{e(seg[1])}</a>'
                       if safe_url(seg[2]) else e(seg[1]))
        elif seg[0] == "anchor":
            out.append(f'<a href="#{e(seg[2])}">{e(seg[1])}</a>' if seg[2] else e(seg[1]))
        elif seg[0] == "ref":
            out.append(f'<sup class="ref">[{int(seg[1])}]</sup>')
        elif seg[0] == "b":
            out.append(f"<b>{e(seg[1])}</b>")
        elif seg[0] == "code":
            out.append(f"<code>{e(seg[1])}</code>")
    return "".join(out)


def to_html(blocks: Iterable[Block], hoff: int = 0) -> str:
    return "".join(_html_block(b, hoff) for b in blocks)


def _id(b: Block) -> str:
    return f' id="{e(b["id"])}"' if b.get("id") else ""


def _rows(rows: list[list[Inline]]) -> str:
    return "".join("<tr>" + "".join(f"<td>{html_inline(c)}</td>" for c in r) + "</tr>" for r in rows)


def _html_block(b: Block, hoff: int) -> str:
    t = b["t"]
    if t == "h":
        n = max(2, min(6, b["level"] + hoff))
        return f"<h{n}{_id(b)}>{html_inline(b['text'])}</h{n}>"
    if t == "p":
        return f"<p>{html_inline(b['text'])}</p>"
    if t == "quote":
        cite = f"<cite>{e(b['cite'])}</cite>" if b.get("cite") else ""
        return f"<blockquote><p>{html_inline(b['text'])}</p>{cite}</blockquote>"
    if t in ("ol", "ul"):
        return f"<{t}>" + "".join(f"<li>{html_inline(x)}</li>" for x in b["items"]) + f"</{t}>"
    if t == "code":
        text = b["text"]
        pre = f'<pre class="code"><code>{e(text)}</code></pre>'
        if len(text) > 600 or text.count("\n") > 14:
            return f"<details class=fold><summary>展开全文（{len(text)} 字）</summary>{pre}</details>"
        return pre
    if t == "table":
        head = "<tr>" + "".join(f"<th>{e(x)}</th>" for x in b["headers"]) + "</tr>"
        show, rows = int(b.get("show") or 8), b["rows"]
        out = f'<div class="tw"><table>{head}{_rows(rows[:show])}</table></div>'
        if len(rows) > show:
            out += (f"<details class=fold><summary>其余 {len(rows) - show} 行</summary>"
                    f'<div class="tw"><table>{head}{_rows(rows[show:])}</table></div></details>')
        return out
    if t == "details":
        return (f"<details{' open' if b.get('open') else ''}><summary>{e(b['summary'])}</summary>"
                f"{to_html(b['blocks'], hoff)}</details>")
    if t == "note":
        return f'<p class="{e(b.get("cls") or "muted")}">{html_inline(b["text"])}</p>'
    if t == "card":
        return f'<div class="card {e(b.get("cls") or "")}"{_id(b)}>{to_html(b["blocks"], hoff)}</div>'
    if t == "img":
        if not _ASSET.match(b["src"] or ""):
            return ""
        cap = f"<figcaption>{e(b['caption'])}</figcaption>" if b.get("caption") else ""
        return f'<figure><img src="{e(b["src"])}" alt="{e(b["alt"])}" loading="lazy">{cap}</figure>'
    if t == "hr":
        return "<hr>"
    return ""
