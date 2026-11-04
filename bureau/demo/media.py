"""演示素材：seed 时生成到 data_dir/demo_media/（3~5 张图片 + 1 个 docx + 1 个 pdf，内容虚构、确定性）。

消息附件写 ``extra.fetch = {"type": "local", "path": …}``，由 B2 的 bureau.media.fetch_media 取回。
PDF 用标准 CJK 字体 STSong-Light（不嵌入）+ ToUnicode 映射手工生成，pypdf 能读出正文，阅读器会用系统字体显示。
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("bureau.demo")

FONT_CANDIDATES = ("C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc",
                   "/System/Library/Fonts/PingFang.ttc", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc")

# 文件名 → (标题, 正文行)。图片里的文字也是 OCR 能读出的"要点"
IMAGES: dict[str, tuple[str, list[str]]] = {
    "storyboard_table.png": ("漫剧分镜表（第 3 集）", ["镜号 | 景别 | 画面描述 | 台词 | 时长", "01 | 中景 | 女孩侧身回头 | 你来了 | 5s",
                                                   "02 | 近景 | 窗边逆光 | — | 5s", "03 | 全景 | 雨夜街口 | 走吧 | 5s",
                                                   "共 12 格 · 首尾帧逐格生成"]),
    "gzh_income.png": ("公众号流量主 · 近 30 天", ["总阅读 9.3 万", "流量主收入 1380 元", "千次阅读约 14.8 元",
                                               "爆款 2 篇：2.1 万 / 1.6 万阅读"]),
    "cc_codex_compare.png": ("重构任务实测对比", ["任务：23 个文件的 Python 重构", "Claude Code：18 分钟，一次跑通",
                                              "Codex：25 分钟，2 次测试未过", "结论：大重构选 Claude Code"]),
    "flux_gguf_workflow.png": ("Flux GGUF 低显存工作流", ["Unet Loader (GGUF) → Q4_K_S", "DualCLIPLoader → t5xxl_fp8",
                                                     "KSampler · 20 步 · euler", "8G 显存实测 1024px 约 75 秒"]),
    "watercolor_avatar.png": ("水彩头像模板 · 前后对比", ["左：通用提示词", "右：四段式模板 + 固定种子",
                                                     "线条更松、留白更多、纸纹更明显"]),
}
DOCX_NAME = "漫剧分镜表模板.docx"
PDF_NAME = "角色LoRA训练参数备忘.pdf"
PDF_LINES = ["角色 LoRA 训练参数备忘（演示文档）", "底模：Flux.1-dev；训练图 30 张，正侧半全身都要有",
             "rank 16，alpha 16，学习率 1e-4，训练 10 个 epoch", "打标：Florence2 自动打标后人工删减描述词",
             "显存：12G 可跑，开启 gradient checkpointing", "验收：同一提示词换 5 个种子，脸部不崩算合格"]


def demo_media_files() -> list[str]:
    return [*IMAGES, DOCX_NAME, PDF_NAME]


def fetch_desc(media_dir: Path | str, name: str) -> dict[str, Any]:
    return {"type": "local", "path": str(Path(media_dir) / name)}


def _font(size: int) -> Any:
    from PIL import ImageFont

    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_image(path: Path, title: str, lines: list[str]) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (960, 600), (14, 22, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([24, 24, 936, 576], outline=(56, 189, 248), width=2)
    d.text((56, 52), title, fill=(230, 237, 247), font=_font(40))
    d.line([56, 120, 904, 120], fill=(48, 66, 106), width=2)
    for i, ln in enumerate(lines):
        d.text((56, 150 + i * 72), ln, fill=(167, 180, 200), font=_font(30))
    d.text((56, 540), "演示数据 · 虚构内容", fill=(115, 133, 160), font=_font(20))
    img.save(path, format="PNG", optimize=True)


def make_docx(path: Path) -> None:
    import docx

    doc = docx.Document()
    doc.add_heading("漫剧分镜表模板（演示）", level=1)
    doc.add_paragraph("用法：先写完整张表，再按镜号批量生成首帧和尾帧；景别一定要写，不然镜头忽远忽近。")
    t = doc.add_table(rows=1, cols=5)
    for c, h in zip(t.rows[0].cells, ("镜号", "景别", "画面描述", "台词", "时长")):
        c.text = h
    for row in (("01", "中景", "女孩侧身回头", "你来了", "5s"), ("02", "近景", "窗边逆光", "—", "5s"),
                ("03", "全景", "雨夜街口", "走吧", "5s")):
        cells = t.add_row().cells
        for c, v in zip(cells, row):
            c.text = v
    doc.add_paragraph("一集 12 格，每格 5 秒；写成「中景，侧身回头」比只写「回头」稳定。")
    doc.save(str(path))


def _hex16(s: str) -> str:
    return s.encode("utf-16-be").hex().upper()


def make_pdf(path: Path, lines: list[str]) -> None:
    """单页 PDF：Type0 / STSong-Light / UniGB-UTF16-H，带 ToUnicode（pypdf 提取文字用）。"""
    content = "BT /F1 16 Tf 56 780 Td 24 TL\n" + "\n".join(f"<{_hex16(ln)}> Tj T*" for ln in lines) + "\nET"
    cmap = ("/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) "
            "/Ordering (UCS) /Supplement 0 >> def /CMapName /Adobe-Identity-UCS def /CMapType 2 def\n"
            "1 begincodespacerange <0000> <FFFF> endcodespacerange\n"
            "1 beginbfrange <0000> <FFFF> <0000> endbfrange\nendcmap CMapName currentdict /CMap defineresource pop end end")
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(content.encode('latin-1'))} >>\nstream\n{content}\nendstream",
        "<< /Type /Font /Subtype /Type0 /BaseFont /STSong-Light /Encoding /UniGB-UTF16-H "
        "/DescendantFonts [6 0 R] /ToUnicode 7 0 R >>",
        "<< /Type /Font /Subtype /CIDFontType0 /BaseFont /STSong-Light /CIDSystemInfo << /Registry (Adobe) "
        "/Ordering (GB1) /Supplement 4 >> /FontDescriptor 8 0 R /DW 1000 >>",
        f"<< /Length {len(cmap.encode('latin-1'))} >>\nstream\n{cmap}\nendstream",
        "<< /Type /FontDescriptor /FontName /STSong-Light /Flags 6 /FontBBox [-25 -254 1000 880] /ItalicAngle 0 "
        "/Ascent 880 /Descent -120 /CapHeight 880 /StemV 93 >>",
    ]
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode("latin-1")
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets).encode("latin-1")
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("latin-1")
    path.write_bytes(bytes(out))


def ensure_demo_media(media_dir: Path) -> list[Path]:
    """生成演示素材（已存在就跳过）。缺 Pillow / python-docx 时跳过对应文件并打日志。"""
    media_dir.mkdir(parents=True, exist_ok=True)
    made = []
    for name, (title, lines) in IMAGES.items():
        p = media_dir / name
        try:
            if not p.exists():
                make_image(p, title, lines)
            made.append(p)
        except Exception as exc:                                     # noqa: BLE001
            log.warning("生成演示图片 %s 失败：%s", name, exc)
    for name, fn in ((DOCX_NAME, make_docx), (PDF_NAME, lambda p: make_pdf(p, PDF_LINES))):
        p = media_dir / name
        try:
            if not p.exists():
                fn(p)
            made.append(p)
        except Exception as exc:                                     # noqa: BLE001
            log.warning("生成演示文档 %s 失败：%s", name, exc)
    return made
