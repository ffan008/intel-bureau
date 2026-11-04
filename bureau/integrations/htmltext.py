"""HTML → 粗略 Markdown（只用标准库 html.parser，不加依赖）。research 抓网页和 media 解析 .html 共用。

保留：标题、段落、列表、引用、代码块、链接、简单表格；丢弃 script/style/nav/footer/form 等。
同时收集 <title> 和 <meta>（og:title、og:description、author 等）。``root_id`` 可指定正文容器
（如公众号的 js_content），找到时只输出容器内的内容。
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

_SKIP = {"script", "style", "noscript", "template", "svg", "canvas", "iframe", "nav", "footer", "form",
         "button", "select", "textarea", "object", "audio", "video", "map", "head"}
_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "source", "track", "wbr"}
_BLOCK = {"p", "div", "section", "article", "main", "header", "aside", "figure", "figcaption", "dl", "dt", "dd",
          "table", "thead", "tbody", "tfoot", "address", "details", "summary"}
_HEAD = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}
MAX_HTML_CHARS = 3_000_000


@dataclass
class HtmlDoc:
    title: str | None
    markdown: str
    meta: dict[str, str] = field(default_factory=dict)


class _Converter(HTMLParser):
    def __init__(self, root_id: str | None) -> None:
        super().__init__(convert_charrefs=True)
        self.segs: list[tuple[str, bool]] = []      # (文本, 是否在根容器内)
        self.root_id = root_id
        self.root_tag: str | None = None
        self.root_depth = 0
        self.root_found = False
        self.skip_depth = 0
        self.in_title = False
        self.title_parts: list[str] = []
        self.meta: dict[str, str] = {}
        self.pre = 0
        self.links: list[tuple[str, int]] = []
        self.lists: list[list] = []                  # [标签, 序号]
        self.in_cell = False

    def emit(self, s: str) -> None:
        if s:
            self.segs.append((s, self.root_tag is not None))

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        if tag == "meta":
            key = (a.get("property") or a.get("name") or a.get("itemprop") or "").strip().lower()
            if key and a.get("content") and key not in self.meta:
                self.meta[key] = a["content"].strip()
            return
        if tag == "title":
            self.in_title = not self.title_parts
            return
        if self.root_id and not self.root_found and a.get("id") == self.root_id and tag not in _VOID:
            self.root_tag, self.root_depth, self.root_found = tag, 0, True
        if self.root_tag == tag and tag not in _VOID:
            self.root_depth += 1
        if tag in _SKIP:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in _HEAD:
            self.emit("\n\n" + _HEAD[tag])
        elif tag == "br":
            self.emit("\n")
        elif tag == "hr":
            self.emit("\n\n---\n\n")
        elif tag == "pre":
            self.pre += 1
            self.emit("\n\n```\n")
        elif tag == "code" and not self.pre:
            self.emit("`")
        elif tag == "blockquote":
            self.emit("\n\n> ")
        elif tag in ("ul", "ol"):
            self.lists.append([tag, 0])
            self.emit("\n")
        elif tag == "li":
            indent = "  " * max(len(self.lists) - 1, 0)
            if self.lists and self.lists[-1][0] == "ol":
                self.lists[-1][1] += 1
                self.emit(f"\n{indent}{self.lists[-1][1]}. ")
            else:
                self.emit(f"\n{indent}- ")
        elif tag == "a":
            self.links.append((a.get("href", "").strip(), len(self.segs)))
        elif tag == "tr":
            self.emit("\n|")
        elif tag in ("td", "th"):
            self.in_cell = True
            self.emit(" ")
        elif tag in _BLOCK:
            self.emit("\n\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        if tag not in _VOID:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
            return
        if tag in _SKIP:
            self.skip_depth = max(self.skip_depth - 1, 0)
        elif not self.skip_depth:
            if tag in _HEAD:
                self.emit("\n\n")
            elif tag == "pre" and self.pre:
                self.pre -= 1
                self.emit("\n```\n\n")
            elif tag == "code" and not self.pre:
                self.emit("`")
            elif tag in ("ul", "ol") and self.lists:
                self.lists.pop()
                self.emit("\n")
            elif tag == "a" and self.links:
                href, start = self.links.pop()
                text = "".join(s for s, _ in self.segs[start:]).strip()
                if (href.lower().startswith(("http://", "https://")) and text and len(text) < 200
                        and "\n" not in text and "](" not in text):
                    in_root = self.segs[start][1] if start < len(self.segs) else self.root_tag is not None
                    del self.segs[start:]
                    self.segs.append((f"[{text}]({href})", in_root))
            elif tag in ("td", "th"):
                self.in_cell = False
                self.emit(" |")
            elif tag in _BLOCK or tag == "blockquote":
                self.emit("\n\n")
        if self.root_tag == tag and tag not in _VOID:
            self.root_depth -= 1
            if self.root_depth <= 0:
                self.root_tag = None

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
            return
        if self.skip_depth or not data:
            return
        if self.pre:
            self.emit(data)
            return
        text = re.sub(r"\s+", " ", data)
        if self.in_cell:
            text = text.replace("|", "｜")
        self.emit(text)


_LIST_LINE = re.compile(r"^\s*(?:[-*] |\d+\. |\|)")


def _tidy(text: str) -> str:
    out: list[str] = []
    in_code = False
    for ln in text.replace("\r", "").split("\n"):
        if ln.strip().startswith("```"):
            in_code = not in_code
            out.append(ln.strip())
        elif in_code:
            out.append(ln.rstrip())
        elif _LIST_LINE.match(ln):
            out.append(ln.rstrip())
        else:
            out.append(ln.strip())
    s = "\n".join(out)
    s = re.sub(r"\n(?:[ \t]*\n){2,}", "\n\n", s)
    s = re.sub(r"(?m)^\s*(?:-|\d+\.)\s*$\n?", "", s)     # 空列表项
    return s.strip()


_WX_VARS = {"msg_title": "wx:msg_title", "msg_desc": "wx:msg_desc", "nickname": "wx:nickname",
            "author": "wx:author"}


def html_to_markdown(source: str, *, root_id: str | None = None) -> HtmlDoc:
    """HTML → (标题, 粗略 Markdown, meta)。不抛异常，解析失败时尽量返回已得到的部分。"""
    src = (source or "")[:MAX_HTML_CHARS]
    conv = _Converter(root_id)
    try:
        conv.feed(src)
        conv.close()
    except Exception:  # noqa: BLE001 — html.parser 遇到极端畸形输入时兜底
        pass
    root_text = "".join(s for s, in_root in conv.segs if in_root)
    body = root_text if conv.root_found and root_text.strip() else "".join(s for s, _ in conv.segs)
    meta = dict(conv.meta)
    # 公众号页面把标题、作者等写在内联脚本变量里
    for var, key in _WX_VARS.items():
        m = re.search(r"\bvar\s+" + var + r"\s*=\s*(?:htmlDecode\()?\s*[\"']([^\"'\n]{1,300})[\"']", src)
        if m and key not in meta:
            meta[key] = html.unescape(m.group(1)).strip()
    title = re.sub(r"\s+", " ", "".join(conv.title_parts)).strip() or None
    return HtmlDoc(title=title, markdown=_tidy(body), meta=meta)
