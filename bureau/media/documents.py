"""文档正文提取：pdf（pypdf）、docx（python-docx）、xlsx（openpyxl）、pptx（python-pptx）、txt、md、csv、html。

- 超过 max_chars 截断，并在末尾注明原文大约多少字。
- 加密（无法用空密码打开）或损坏的文件返回空串并记日志；不抛异常。
- Office 文件先检查 zip 解压后的总大小，防止压缩炸弹。
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import zipfile
from pathlib import Path

from bureau.integrations.htmltext import html_to_markdown
from bureau.integrations.netsafe import decode_text

log = logging.getLogger("bureau.media")

MAX_READ_BYTES = 50 * 1024 * 1024
MAX_UNZIPPED = 300 * 1024 * 1024
XLSX_MAX_ROWS = 50
XLSX_MAX_COLS = 30
CSV_MAX_ROWS = 200
_TEXT_EXT = {".txt", ".md", ".markdown", ".log", ".json", ".yaml", ".yml"}
_HTML_EXT = {".html", ".htm", ".xhtml"}


class _Enough(Exception):
    """输出已经够长，提前结束。"""


class _Out:
    def __init__(self, limit: int) -> None:
        self.parts: list[str] = []
        self.size = 0
        self.limit = limit
        self.more = False

    def add(self, s: str) -> None:
        if not s:
            return
        self.parts.append(s)
        self.size += len(s)
        if self.size > self.limit * 2:     # 多读一些用来估算总长；再多就停
            self.more = True
            raise _Enough


def _sniff(path: Path) -> str:
    ext = path.suffix.lower()
    if ext:
        return ext
    try:
        with path.open("rb") as fh:
            head = fh.read(8)
    except OSError:
        return ""
    if head.startswith(b"%PDF"):
        return ".pdf"
    if head.startswith(b"PK"):
        try:
            with zipfile.ZipFile(path) as z:
                names = set(z.namelist())
        except (zipfile.BadZipFile, OSError):
            return ""
        if "word/document.xml" in names:
            return ".docx"
        if "xl/workbook.xml" in names:
            return ".xlsx"
        if "ppt/presentation.xml" in names:
            return ".pptx"
    return ".txt"


def _zip_ok(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as z:
            total = sum(i.file_size for i in z.infolist())
    except (zipfile.BadZipFile, OSError):
        return False
    return total <= MAX_UNZIPPED


def _pdf(path: Path, out: _Out) -> None:
    from pypdf import PdfReader
    reader = PdfReader(str(path))
    if reader.is_encrypted:
        try:
            ok = reader.decrypt("")
        except Exception:  # noqa: BLE001
            ok = 0
        if not ok:
            raise PermissionError("PDF 已加密")
    n = len(reader.pages)
    for i, page in enumerate(reader.pages, 1):
        text = (page.extract_text() or "").strip()
        if text:
            out.add(f"\n\n## 第 {i}/{n} 页\n\n{text}")


def _docx(path: Path, out: _Out) -> None:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    d = docx.Document(str(path))
    body = d.element.body
    for child in body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(child, d)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name if p.style is not None else "") or ""
            m = re.match(r"(?:Heading|标题)\s*(\d)", style)
            if m:
                out.add(f"\n\n{'#' * min(int(m.group(1)) + 1, 6)} {text}")
            elif style.lower().startswith(("list", "列表")):
                out.add(f"\n- {text}")
            else:
                out.add(f"\n\n{text}")
        elif tag == "tbl":
            t = Table(child, d)
            rows = []
            for r in t.rows[:XLSX_MAX_ROWS]:
                cells = [re.sub(r"\s+", " ", c.text).strip().replace("|", "｜") for c in r.cells]
                rows.append("| " + " | ".join(cells) + " |")
            if rows:
                out.add("\n\n" + "\n".join(rows))


def _xlsx(path: Path, out: _Out) -> None:
    import openpyxl
    wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    try:
        for ws in wb.worksheets:
            lines = []
            total = 0
            for row in ws.iter_rows(values_only=True):
                cells = ["" if v is None else re.sub(r"\s+", " ", str(v)).strip().replace("|", "｜")
                         for v in row[:XLSX_MAX_COLS]]
                if not any(cells):
                    continue
                total += 1
                if total <= XLSX_MAX_ROWS:
                    lines.append("| " + " | ".join(cells) + " |")
            if not lines:
                continue
            head = f"\n\n## 工作表：{ws.title}（共 {total} 行有内容"
            head += f"，只列出前 {XLSX_MAX_ROWS} 行）" if total > XLSX_MAX_ROWS else "）"
            out.add(head + "\n\n" + "\n".join(lines))
    finally:
        wb.close()


def _pptx(path: Path, out: _Out) -> None:
    from pptx import Presentation
    prs = Presentation(str(path))
    n = len(prs.slides)
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
                t = shape.text_frame.text.strip()
                if t:
                    texts.append(t)
            if getattr(shape, "has_table", False) and shape.has_table:
                for r in shape.table.rows:
                    cells = [c.text.strip().replace("|", "｜") for c in r.cells]
                    texts.append("| " + " | ".join(cells) + " |")
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        if texts or notes:
            out.add(f"\n\n## 第 {i}/{n} 页\n\n" + "\n".join(texts) + (f"\n\n> 备注：{notes}" if notes else ""))


def _read_text(path: Path) -> str:
    with path.open("rb") as fh:
        data = fh.read(MAX_READ_BYTES)
    return decode_text(data)


def _csv(path: Path, out: _Out) -> None:
    text = _read_text(path)
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",\t;|")
    except csv.Error:
        dialect = csv.excel
    rows = 0
    total = 0
    for row in csv.reader(io.StringIO(text), dialect):
        if not any(c.strip() for c in row):
            continue
        total += 1
        if rows < CSV_MAX_ROWS:
            out.add("| " + " | ".join(c.strip().replace("|", "｜") for c in row[:XLSX_MAX_COLS]) + " |\n")
            rows += 1
    if total > CSV_MAX_ROWS:
        out.add(f"\n（共 {total} 行，只列出前 {CSV_MAX_ROWS} 行）")


def _extract_sync(path: Path, max_chars: int) -> str:
    kind = _sniff(path)
    out = _Out(max_chars)
    try:
        if kind == ".pdf":
            _pdf(path, out)
        elif kind in (".docx", ".docm"):
            if not _zip_ok(path):
                raise ValueError("文件损坏或解压后过大")
            _docx(path, out)
        elif kind in (".xlsx", ".xlsm"):
            if not _zip_ok(path):
                raise ValueError("文件损坏或解压后过大")
            _xlsx(path, out)
        elif kind == ".pptx":
            if not _zip_ok(path):
                raise ValueError("文件损坏或解压后过大")
            _pptx(path, out)
        elif kind in (".csv", ".tsv"):
            _csv(path, out)
        elif kind in _HTML_EXT:
            doc = html_to_markdown(_read_text(path))
            out.add((f"# {doc.title}\n\n" if doc.title else "") + doc.markdown)
        elif kind in _TEXT_EXT:
            out.add(_read_text(path))
        else:
            log.info("不支持的文档类型：%s", kind or "未知")
            return ""
    except _Enough:
        pass
    text = re.sub(r"\n{3,}", "\n\n", "".join(out.parts)).strip()
    if len(text) > max_chars:
        approx = f"约 {len(text)} 字以上" if out.more else f"共约 {len(text)} 字"
        text = text[:max_chars].rstrip() + f"\n\n（文档较长，已截断：只保留前 {max_chars} 字，原文{approx}）"
    return text


async def extract_document(path: Path, *, max_chars: int = 20000) -> str:
    """提取文档正文（Markdown 风格的纯文本）。失败、加密或不支持时返回空串。"""
    p = Path(path)
    try:
        if not p.is_file():
            log.warning("文档不存在，无法提取正文")
            return ""
        return await asyncio.to_thread(_extract_sync, p, max(500, int(max_chars or 20000)))
    except PermissionError:
        log.warning("文档已加密，无法提取正文：%s", p.suffix.lower() or "未知类型")
    except Exception as exc:  # noqa: BLE001 — 各解析库的异常类型很多，统一当作损坏
        log.warning("文档无法解析（可能已损坏）：%s，%s", p.suffix.lower() or "未知类型", type(exc).__name__)
    return ""
