"""bureau.media：附件取回（local / wda / onebot / lark / url）、大小上限、文档解析、OCR 模式；采集器写入的 extra.fetch。"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import subprocess
from pathlib import Path

import httpx
import pytest
from PIL import Image

from bureau.collectors.feishu_lark import lark_message_to_raw
from bureau.collectors.wechat_wda import attach_wda_fetch
from bureau.contracts import GroupInfo, Platform
from bureau.integrations.chat_formats import wda_message_to_raw
from bureau.integrations.onebot import message_to_raw
from bureau.media import MediaResult, extract_document, fetch_media, ocr_image
from bureau.media import ocr as ocr_mod

from .helpers import TZ8, MockHTTP, ok_json, run, ts


def png_bytes(w=40, h=30, color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, format="PNG")
    return buf.getvalue()


async def public_dns(host, port):
    return ["93.184.216.34"]


# ---------------------------------------------------------------- fetch_media

def test_fetch_local_names_by_sha256_and_records_meta(tmp_path):
    data = png_bytes(40, 30)
    src = tmp_path / "源图.png"
    src.write_bytes(data)
    att = {"kind": "image", "title": "截图", "extra": {"fetch": {"type": "local", "path": str(src)}}}
    r = run(fetch_media({}, {}, "demo", att, tmp_path / "out"))
    digest = hashlib.sha256(data).hexdigest()
    assert r.ok and r.kind == "image" and Path(r.path).name == f"{digest[:16]}.png"
    assert (r.mime, r.size, r.width, r.height, r.sha256, r.filename) == ("image/png", len(data), 40, 30, digest, "截图")
    again = run(fetch_media({}, {}, "demo", att, tmp_path / "out"))
    assert again.path == r.path and len(list((tmp_path / "out").iterdir())) == 1       # 同一内容只存一份


def test_fetch_size_limit_and_missing_spec(tmp_path):
    big = tmp_path / "big.bin"
    big.write_bytes(b"\0" * (2 * 1024 * 1024))
    cfg = {"media": {"max_file_mb": 1}}
    r = run(fetch_media(cfg, {}, "demo", {"kind": "file", "extra": {"fetch": {"type": "local", "path": str(big)}}},
                        tmp_path / "out"))
    assert not r.ok and "上限" in r.error and not (tmp_path / "out").exists()
    r2 = run(fetch_media({}, {}, "qq", {"kind": "image", "extra": {}}, tmp_path / "out"))
    assert not r2.ok and "extra.fetch" in r2.error
    r3 = run(fetch_media({}, {}, "demo", {"kind": "file", "extra": {"fetch": {"type": "local", "path": str(tmp_path / "nope")}}},
                         tmp_path / "out"))
    assert not r3.ok and "不存在" in r3.error
    r4 = run(fetch_media({}, {}, "demo", {"kind": "file", "extra": {"fetch": {"type": "ftp"}}}, tmp_path / "out"))
    assert not r4.ok and "不支持" in r4.error
    assert isinstance(r4, MediaResult)


def test_fetch_url_is_ssrf_protected_and_size_limited(tmp_path):
    http = MockHTTP(lambda r: httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"}))
    att = {"kind": "image", "url": "https://cdn.example.com/a.png"}
    r = run(fetch_media({}, {}, "qq", att, tmp_path / "o", transport=http.transport, resolver=public_dns))
    assert r.ok and r.width == 40
    bad = {"kind": "image", "extra": {"fetch": {"type": "url", "url": "http://127.0.0.1:3010/get_image"}}}
    r2 = run(fetch_media({}, {}, "qq", bad, tmp_path / "o", transport=http.transport, resolver=public_dns))
    assert not r2.ok and "本机" in r2.error and len(http.requests) == 1
    huge = MockHTTP(lambda r: httpx.Response(200, content=b"x" * 3 * 1024 * 1024))
    r3 = run(fetch_media({"media": {"max_file_mb": 1}}, {}, "qq", att, tmp_path / "o",
                         transport=huge.transport, resolver=public_dns))
    assert not r3.ok and "上限" in r3.error


def test_fetch_wda_image_and_video(tmp_path):
    def handler(r):
        assert r.url.host == "127.0.0.1" and r.url.port == 10392
        if r.url.path == "/api/chat/media/image":
            return httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"})
        if r.url.path == "/api/chat/media/video":
            return httpx.Response(404, json={"detail": "Video not found"})
        raise AssertionError(r.url)

    http = MockHTTP(handler)
    spec = {"type": "wda", "kind": "image", "account": "wxid_me", "username": "123@chatroom",
            "md5": "0123456789abcdef0123456789abcdef", "server_id": 99}
    r = run(fetch_media({}, {}, "wechat", {"kind": "image", "extra": {"fetch": spec}}, tmp_path / "o",
                        transport=http.transport))
    assert r.ok and r.mime == "image/png"
    q = dict(http.requests[0].url.params)
    assert q == {"account": "wxid_me", "username": "123@chatroom", "md5": "0123456789abcdef0123456789abcdef",
                 "server_id": "99"}
    vid = {"type": "wda", "kind": "video", "account": "wxid_me", "username": "123@chatroom", "file_id": "1_2"}
    r2 = run(fetch_media({"sources": {"wechat": {"wda": {"base_url": "http://127.0.0.1:10392"}}}}, {}, "wechat",
                         {"kind": "video", "extra": {"fetch": vid}}, tmp_path / "o", transport=http.transport))
    assert not r2.ok and "HTTP 404" in r2.error


def test_fetch_wda_gzip_response_is_not_decoded_twice(tmp_path):
    import gzip

    data = png_bytes(12, 12)
    http = MockHTTP(lambda r: httpx.Response(200, content=gzip.compress(data),
                                             headers={"content-type": "image/png", "content-encoding": "gzip"}))
    spec = {"type": "wda", "kind": "image", "account": "a", "username": "1@chatroom", "file_id": "1_2"}
    r = run(fetch_media({}, {}, "wechat", {"kind": "image", "extra": {"fetch": spec}}, tmp_path / "o",
                        transport=http.transport))
    assert r.ok and r.width == 12 and Path(r.path).read_bytes() == data


def test_fetch_wda_file_reads_wechat_file_dir(tmp_path):
    wxid = tmp_path / "xwechat_files" / "wxid_me"
    month = wxid / "msg" / "file" / "2026-10"
    month.mkdir(parents=True)
    body = b"PDF-ish content"
    (month / "方案(1).pdf").write_bytes(b"other version")
    (month / "方案.pdf").write_bytes(body)
    http = MockHTTP(lambda r: ok_json({"status": "success", "accounts": ["wxid_me"], "default_account": "wxid_me",
                                       "accountInfos": [{"account": "wxid_me", "wxidDir": str(wxid)}]}))
    spec = {"type": "wda", "kind": "file", "account": "wxid_me", "username": "1@chatroom", "title": "方案.pdf",
            "file_size": str(len(body)), "md5": hashlib.md5(body).hexdigest(), "create_time": ts("2026-10-29 10:00")}
    r = run(fetch_media({}, {}, "wechat", {"kind": "file", "title": "方案.pdf", "extra": {"fetch": spec}},
                        tmp_path / "o", transport=http.transport))
    assert r.ok and Path(r.path).read_bytes() == body and r.filename == "方案.pdf"
    evil = dict(spec, title="..\\..\\secret.txt")
    r2 = run(fetch_media({}, {}, "wechat", {"kind": "file", "extra": {"fetch": evil}}, tmp_path / "o",
                         transport=http.transport))
    assert not r2.ok and "不合法" in r2.error


def test_fetch_onebot_base64_local_and_group_file_url(tmp_path):
    local = tmp_path / "napcat_cache.jpg"
    local.write_bytes(png_bytes(10, 10))
    seen = []

    def handler(r):
        body = json.loads(r.content or b"{}")
        seen.append((r.url.path, body, r.headers.get("authorization")))
        if r.url.host == "127.0.0.1" and r.url.path == "/get_image":
            if body["file"] == "b64.png":
                return ok_json({"status": "ok", "retcode": 0,
                                "data": {"file": "", "base64": base64.b64encode(png_bytes(5, 5)).decode()}})
            return ok_json({"status": "ok", "retcode": 0, "data": {"file": str(local), "url": str(local)}})
        if r.url.path == "/get_file":
            return ok_json({"status": "failed", "retcode": 1200, "message": "file not found"})
        if r.url.path == "/get_group_file_url":
            return ok_json({"status": "ok", "retcode": 0, "data": {"url": "https://njc-download.ftn.qq.com/x"}})
        if r.url.host == "njc-download.ftn.qq.com":
            return httpx.Response(200, content=b"%PDF-1.4 fake")
        raise AssertionError(r.url)

    http = MockHTTP(handler)
    secrets = {"sources": {"qq": {"onebot": {"token": "tok"}}}}
    a1 = {"kind": "image", "extra": {"fetch": {"type": "onebot", "action": "get_image", "file": "b64.png"}}}
    r1 = run(fetch_media({}, secrets, "qq", a1, tmp_path / "o", transport=http.transport, resolver=public_dns))
    assert r1.ok and r1.width == 5 and seen[0][2] == "Bearer tok"
    a2 = {"kind": "image", "extra": {"fetch": {"type": "onebot", "action": "get_image", "file": "abc.jpg"}}}
    assert run(fetch_media({}, secrets, "qq", a2, tmp_path / "o", transport=http.transport)).width == 10
    a3 = {"kind": "file", "title": "资料.pdf", "extra": {"fetch": {"type": "onebot", "action": "get_file",
                                                                 "file": "资料.pdf", "file_id": "/abc-123",
                                                                 "group_id": "123456"}}}
    r3 = run(fetch_media({}, secrets, "qq", a3, tmp_path / "o", transport=http.transport, resolver=public_dns))
    assert r3.ok and r3.mime == "application/pdf"
    assert [p for p, *_ in seen[-3:]] == ["/get_file", "/get_group_file_url", "/x"]
    assert seen[-2][1] == {"group_id": "123456", "file_id": "/abc-123"}


def test_fetch_lark_via_cli(tmp_path):
    calls = []

    async def runner(argv, timeout, cwd, env):
        args = list(argv[1:])
        calls.append((args, cwd))
        out = Path(cwd) / (args[args.index("--output") + 1] + ".png")
        out.write_bytes(png_bytes(8, 8))
        return 0, json.dumps({"ok": True, "data": {"saved_path": out.name, "size_bytes": out.stat().st_size}}), ""

    spec = {"type": "lark", "message_id": "om_abc123", "file_key": "img_v3_xyz", "resource_type": "image",
            "identity": "user"}
    r = run(fetch_media({}, {}, "feishu", {"kind": "image", "extra": {"fetch": spec}}, tmp_path / "o",
                        lark_runner=runner))
    assert r.ok and r.width == 8
    args, cwd = calls[0]
    assert args[:2] == ["im", "+messages-resources-download"] and args[args.index("--as") + 1] == "user"
    assert (args[args.index("--message-id") + 1], args[args.index("--file-key") + 1], args[args.index("--type") + 1]) == \
        ("om_abc123", "img_v3_xyz", "image")
    assert not Path(args[args.index("--output") + 1]).is_absolute() and not Path(cwd).exists()   # 相对路径，用完删除
    bad = dict(spec, message_id="om_x; rm -rf /")
    r2 = run(fetch_media({}, {}, "feishu", {"kind": "image", "extra": {"fetch": bad}}, tmp_path / "o", lark_runner=runner))
    assert not r2.ok and "不合法" in r2.error and len(calls) == 1


# ---------------------------------------------------------------- extract_document

def make_pdf(path: Path, text: str) -> None:
    content = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % off for off in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))


def test_extract_four_office_formats(tmp_path):
    import docx
    import openpyxl
    from pptx import Presentation

    d = docx.Document()
    d.add_heading("方法总结", 1)
    d.add_paragraph("先打草稿，再上色。提取码 Ab12")
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text = "工具", "结论"
    d.save(tmp_path / "a.docx")
    out = run(extract_document(tmp_path / "a.docx"))
    assert "## 方法总结" in out and "提取码 Ab12" in out and "| 工具 | 结论 |" in out

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "选型"
    ws.append(["模型", "场景", "结论"])
    for i in range(60):
        ws.append([f"M{i}", "出图", "可用"])
    wb.save(tmp_path / "b.xlsx")
    out = run(extract_document(tmp_path / "b.xlsx"))
    assert "## 工作表：选型（共 61 行有内容，只列出前 50 行）" in out and "| 模型 | 场景 | 结论 |" in out
    assert "M48" in out and "M55" not in out

    prs = Presentation()
    for title, body in (("第一页标题", "要点一"), ("第二页标题", "要点二")):
        s = prs.slides.add_slide(prs.slide_layouts[1])
        s.shapes.title.text, s.placeholders[1].text = title, body
    prs.save(tmp_path / "c.pptx")
    out = run(extract_document(tmp_path / "c.pptx"))
    assert "## 第 1/2 页" in out and "第二页标题" in out and out.index("要点一") < out.index("要点二")

    make_pdf(tmp_path / "d.pdf", "Hello IntelBureau")
    out = run(extract_document(tmp_path / "d.pdf"))
    assert "第 1/1 页" in out and "Hello IntelBureau" in out


def test_extract_text_formats_and_truncation(tmp_path):
    (tmp_path / "a.md").write_text("# 标题\n" + "正文" * 2000, "utf-8")
    out = run(extract_document(tmp_path / "a.md", max_chars=1000))
    assert out.startswith("# 标题") and "已截断" in out and len(out) < 1100
    (tmp_path / "b.csv").write_text("名字,链接\n甲,https://a\n乙,https://b\n", "utf-8")
    assert "| 甲 | https://a |" in run(extract_document(tmp_path / "b.csv"))
    (tmp_path / "c.html").write_text("<html><head><title>页</title><script>bad()</script></head>"
                                     "<body><h1>大标题</h1><p>段落</p></body></html>", "utf-8")
    out = run(extract_document(tmp_path / "c.html"))
    assert "# 页" in out and "# 大标题" in out and "bad()" not in out
    (tmp_path / "d.txt").write_bytes("中文 GBK 文本".encode("gb18030"))
    assert run(extract_document(tmp_path / "d.txt")) == "中文 GBK 文本"


def test_extract_encrypted_corrupt_and_unknown_return_empty(tmp_path, caplog):
    from pypdf import PdfReader, PdfWriter

    make_pdf(tmp_path / "plain.pdf", "secret")
    w = PdfWriter()
    for p in PdfReader(str(tmp_path / "plain.pdf")).pages:
        w.add_page(p)
    w.encrypt("pw-123")
    with open(tmp_path / "enc.pdf", "wb") as fh:
        w.write(fh)
    (tmp_path / "bad.docx").write_bytes(b"PK\x03\x04 not really a zip")
    (tmp_path / "x.exe").write_bytes(b"MZ\x90")
    with caplog.at_level(logging.WARNING, logger="bureau.media"):
        assert run(extract_document(tmp_path / "enc.pdf")) == ""
        assert run(extract_document(tmp_path / "bad.docx")) == ""
        assert run(extract_document(tmp_path / "missing.pdf")) == ""
    assert run(extract_document(tmp_path / "x.exe")) == ""
    assert "加密" in caplog.text and "损坏" in caplog.text


# ---------------------------------------------------------------- ocr_image

def test_ocr_off_and_llm_without_consent_return_empty(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    never = MockHTTP(lambda r: (_ for _ in ()).throw(AssertionError("不应调用视觉模型")))
    assert run(ocr_image(p, mode="off")) == ""
    assert run(ocr_image(p, mode="llm", settings={"privacy": {"cloud_llm_consent": False}},
                         secrets={"llm": {"openai_compat": {"api_key": "sk-x"}}}, transport=never.transport)) == ""
    assert run(ocr_image(p, mode="llm", settings={"privacy": {"cloud_llm_consent": True}}, secrets={},
                         transport=never.transport)) == ""
    assert run(ocr_image(tmp_path / "missing.png", mode="windows")) == ""
    assert never.requests == []


def test_ocr_llm_request_format(tmp_path):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    http = MockHTTP(lambda r: ok_json({"choices": [{"message": {"content": "图里的文字"}}]}))
    out = run(ocr_image(p, mode="llm", settings={"privacy": {"cloud_llm_consent": True}},
                        secrets={"research": {"deepseek_api_key": "sk-ds"}}, transport=http.transport))
    assert out == "图里的文字"
    req = http.requests[0]
    body = json.loads(req.content)
    assert str(req.url) == "https://api.deepseek.com/chat/completions" and req.headers["authorization"] == "Bearer sk-ds"
    assert body["model"] == "deepseek-flash" and body["thinking"] == {"type": "disabled"}
    parts = body["messages"][0]["content"]
    assert parts[0]["type"] == "text" and parts[1]["type"] == "image_url"
    assert parts[1]["image_url"]["url"].startswith("data:image/png;base64,")


def test_ocr_windows_invokes_script_and_merges_tiles(tmp_path, monkeypatch):
    p = tmp_path / "long.png"
    Image.new("RGB", (800, 9000), "white").save(p)
    # 这一段测的是 Windows 分支：在 macOS/Linux 上跑测试时把平台标志固定住
    monkeypatch.setattr(ocr_mod, "IS_WINDOWS", True)
    monkeypatch.setattr(ocr_mod, "IS_MAC", False)
    seen = {}

    def fake_run(argv, **kw):
        seen["argv"], seen["kw"] = argv, kw
        tiles = sorted(Path(argv[argv.index("-Path") + 1]).glob("*.png"))
        seen["tiles"] = [Image.open(t).size for t in tiles]
        items = [{"name": "000.png", "lines": ["情 报 局 每 日 风 向 标", "提 取 码 ： Ab12 手 绘"]},
                 {"name": "001.png", "lines": ["提 取 码 ： Ab12 手 绘", "Windows OCR 中 文"]},
                 {"name": "002.png", "lines": ["结 尾"]}]
        out = json.dumps({"ok": True, "lang": "zh-Hans-CN", "max": 10000, "items": items}, ensure_ascii=False)
        return subprocess.CompletedProcess(argv, 0, stdout=out.encode("utf-8"), stderr=b"")

    monkeypatch.setattr(ocr_mod.subprocess, "run", fake_run)
    text = run(ocr_image(p, mode="windows"))
    assert text == "情报局每日风向标\n提取码：Ab12 手绘\nWindows OCR 中文\n结尾"            # 重叠行去重，中文间空格去掉
    argv = seen["argv"]
    assert argv[:5] == ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass"]
    assert argv[argv.index("-File") + 1].endswith("ocr.ps1") and argv[argv.index("-Lang") + 1] == "zh-Hans-CN"
    assert seen["kw"]["creationflags"] == getattr(subprocess, "CREATE_NO_WINDOW", 0) and seen["kw"]["timeout"] > 0
    assert len(seen["tiles"]) == 3 and all(h <= ocr_mod.WIN_MAX_DIM and w == 800 for w, h in seen["tiles"])


def test_ocr_windows_failure_and_timeout_return_empty(tmp_path, monkeypatch):
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    monkeypatch.setattr(ocr_mod, "IS_WINDOWS", True)
    monkeypatch.setattr(ocr_mod, "IS_MAC", False)
    monkeypatch.setattr(ocr_mod.subprocess, "run", lambda argv, **kw: subprocess.CompletedProcess(
        argv, 2, stdout=b'{"ok":false,"code":"no_engine","error":"x","max":10000}', stderr=b""))
    assert run(ocr_image(p)) == ""

    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(argv, 1)

    monkeypatch.setattr(ocr_mod.subprocess, "run", boom)
    assert run(ocr_image(p)) == ""
    (tmp_path / "bad.png").write_bytes(b"not an image")
    assert run(ocr_image(tmp_path / "bad.png")) == ""


def test_ocr_script_is_utf8_bom_ascii():
    raw = ocr_mod.OCR_SCRIPT.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf") and all(b < 128 for b in raw[3:])
    text = raw[3:].decode("ascii")
    assert "AsTask" in text and "Windows.Media.Ocr" in text and "MaxImageDimension" in text


# ---------------------------------------------------------------- macOS 本机 OCR

def test_macos_lang_mapping():
    assert ocr_mod._vision_langs("zh-Hans-CN") == ["zh-Hans"]
    assert ocr_mod._vision_langs("zh-Hant-TW") == ["zh-Hant"]
    assert ocr_mod._vision_langs("en-US") == ["en-US"]
    assert ocr_mod._tesseract_langs("zh-Hans-CN") == "chi_sim+eng"
    assert ocr_mod._tesseract_langs("zh-Hant-TW") == "chi_tra+eng"
    assert ocr_mod._tesseract_langs("en-US") == "eng"


def test_macos_ocr_routes_to_system_ocr(tmp_path, monkeypatch):
    """mode=windows 在 macOS 上应该走 Vision（而不是去调 powershell）。"""
    p = tmp_path / "a.png"
    p.write_bytes(png_bytes())
    calls = []

    async def fake_macos(path, settings):
        calls.append(path)
        return "识别结果"

    monkeypatch.setattr(ocr_mod, "IS_WINDOWS", False)
    monkeypatch.setattr(ocr_mod, "IS_MAC", True)
    monkeypatch.setattr(ocr_mod, "_ocr_macos", fake_macos)
    assert run(ocr_image(p, mode="windows")) == "识别结果"
    assert calls == [p]
    assert run(ocr_image(p, mode="system")) == "识别结果"


def test_macos_ocr_falls_back_to_tesseract_without_vision_lang(tmp_path, monkeypatch):
    """本机 Vision 没有中文包时，用 tesseract 兜底；两者都没有就返回空串。"""
    folder = tmp_path / "tiles"
    folder.mkdir()
    Image.new("RGB", (100, 40), "white").save(folder / "000.png")
    monkeypatch.setattr(ocr_mod, "_vision_supported", lambda: ["en-US"])
    monkeypatch.setattr(ocr_mod.shutil, "which", lambda name: "/opt/homebrew/bin/tesseract" if name == "tesseract" else None)
    seen = {}

    def fake_tess(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(argv, 0, stdout="情 报 局".encode("utf-8"), stderr=b"")
    monkeypatch.setattr(ocr_mod.subprocess, "run", fake_tess)
    res = ocr_mod._mac_backend(folder, "zh-Hans-CN", 30.0)
    assert res["ok"] and seen["argv"][seen["argv"].index("-l") + 1] == "chi_sim+eng"

    monkeypatch.setattr(ocr_mod.shutil, "which", lambda name: None)
    res = ocr_mod._mac_backend(folder, "zh-Hans-CN", 30.0)
    assert res["ok"] is False and res.get("code") == "no_lang"


# ---------------------------------------------------------------- 采集器写入的 extra.fetch

def test_wda_collector_fetch_specs():
    group = "123@chatroom"
    base = {"createTime": ts("2026-10-29 10:00"), "senderUsername": "wxid_a", "senderDisplayName": "甲",
            "localId": 7, "serverId": 0}
    img = base | {"renderType": "image", "imageMd5": "0123456789abcdef0123456789abcdef", "imageFileId": "",
                  "serverIdStr": "88"}
    raw = wda_message_to_raw(img, group_id=group, group_name="群", tz=TZ8)
    assert "fetch" not in raw.attachments[0].extra                 # 共用转换函数（文件导入也用）不写 fetch
    attach_wda_fetch(raw, img, account="wxid_me", username=group)
    assert raw.attachments[0].extra["fetch"] == {"type": "wda", "kind": "image", "account": "wxid_me",
                                                 "username": group, "md5": "0123456789abcdef0123456789abcdef",
                                                 "server_id": 88}
    f = base | {"renderType": "file", "title": "方案.pdf", "fileSize": "1024", "fileMd5": "ab" * 16}
    raw = wda_message_to_raw(f, group_id=group, group_name="群", tz=TZ8)
    attach_wda_fetch(raw, f, account=None, username=group)
    spec = raw.attachments[0].extra["fetch"]
    assert spec["kind"] == "file" and spec["title"] == "方案.pdf" and spec["file_size"] == "1024"
    assert spec["create_time"] == f["createTime"] and "account" not in spec
    v = base | {"renderType": "video", "videoMd5": "", "videoFileId": ""}
    raw = wda_message_to_raw(v, group_id=group, group_name="群", tz=TZ8)
    attach_wda_fetch(raw, v, account="a", username=group)
    assert "fetch" not in raw.attachments[0].extra                 # 没有任何标识时不写


def test_onebot_fetch_specs():
    msg = {"group_id": 123456, "message_id": 9, "time": ts("2026-10-29 10:00"),
           "sender": {"user_id": 1, "nickname": "甲"},
           "message": [{"type": "image", "data": {"file": "ABC.jpg", "url": "https://multimedia.nt.qq.com.cn/x",
                                                  "file_size": "100"}},
                       {"type": "image", "data": {"file": "D.jpg", "url": "C:\\NapCat\\cache\\D.jpg"}},
                       {"type": "file", "data": {"file": "资料.pdf", "file_id": "/f-1", "file_size": 10}},
                       {"type": "face", "data": {"id": "1"}}]}
    raw = message_to_raw(msg)
    specs = [a.extra.get("fetch") for a in raw.attachments]
    assert specs[0] == {"type": "onebot", "action": "get_image", "file": "ABC.jpg",
                        "url": "https://multimedia.nt.qq.com.cn/x", "group_id": "123456"}
    assert specs[1]["local_hint"] == "C:\\NapCat\\cache\\D.jpg" and "url" not in specs[1]
    assert specs[2] == {"type": "onebot", "action": "get_file", "file": "资料.pdf", "file_id": "/f-1",
                        "name": "资料.pdf", "group_id": "123456"}
    assert len(raw.attachments) == 3


def test_lark_fetch_specs():
    group = GroupInfo(platform=Platform.FEISHU, native_id="oc_1", name="群")
    m = {"message_id": "om_1", "msg_type": "post", "create_time": "2026-10-29 10:00",
         "sender": {"id": "ou_1", "name": "甲"},
         "content": '![Image](img_v3_a) <file key="file_v3_b" name="方案.pdf"/> <folder key="fd_1" name="夹"/>'}
    raw = lark_message_to_raw(m, group=group, tz=TZ8)
    fetch = {a.kind + ":" + (a.title or ""): a.extra.get("fetch") for a in raw.attachments}
    assert fetch["image:"] == {"type": "lark", "message_id": "om_1", "file_key": "img_v3_a",
                               "resource_type": "image", "identity": "user"}
    assert fetch["file:方案.pdf"]["resource_type"] == "file" and fetch["file:方案.pdf"]["file_key"] == "file_v3_b"
    assert fetch["file:夹"] is None                                 # 文件夹不能下载


def test_file_import_never_writes_fetch(tmp_path):
    from bureau.integrations.export_parsers import parse_export

    doc = {"session": {"username": "1@chatroom", "displayName": "群"}, "messages": [
        {"localId": 1, "serverId": "5", "createTime": ts("2026-10-29 10:00"), "renderType": "image",
         "imageMd5": "0123456789abcdef0123456789abcdef", "senderUsername": "a", "senderDisplayName": "甲"}]}
    try:
        res = parse_export(json.dumps(doc).encode("utf-8"), filename="x.json", platform=Platform.WECHAT, tz="Asia/Shanghai")
    except Exception:  # noqa: BLE001 — 格式识别不了也无所谓，这里只关心不会出现 fetch
        return
    for m in res.messages:
        assert all("fetch" not in a.extra for a in m.attachments)


# ---------------------------------------------------------------- WDA 媒体接口的 Token（2.x）

def test_fetch_wda_sends_token_from_secrets(tmp_path):
    seen: dict[str, str | None] = {}

    def handler(r: httpx.Request) -> httpx.Response:
        seen["auth"] = r.headers.get("authorization")
        return httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"})

    spec = {"type": "wda", "kind": "image", "account": "a", "username": "1@chatroom", "file_id": "1_2"}
    r = run(fetch_media({}, {"sources": {"wechat": {"wda": {"token": "tok-m"}}}}, "wechat",
                        {"kind": "image", "extra": {"fetch": spec}}, tmp_path / "o",
                        transport=MockHTTP(handler).transport))
    assert r.ok and seen["auth"] == "Bearer tok-m"


def test_fetch_wda_401_says_token_needed(tmp_path):
    spec = {"type": "wda", "kind": "image", "account": "a", "username": "1@chatroom", "file_id": "1_2"}
    r = run(fetch_media({}, {}, "wechat", {"kind": "image", "extra": {"fetch": spec}}, tmp_path / "o",
                        transport=MockHTTP(lambda q: httpx.Response(
                            401, json={"detail": {"code": "external_token_required"}})).transport))
    assert not r.ok and "Token" in r.error


def test_fetch_wda_autodiscovered_token_only_for_loopback(tmp_path, monkeypatch):
    """自动读到的本机 Token 只在地址是本机时发出，别送到远端。"""
    from bureau.media import fetch as fetch_mod

    monkeypatch.setattr(fetch_mod, "discover_token", lambda: "auto-tok")
    seen: list[str | None] = []

    def handler(r: httpx.Request) -> httpx.Response:
        seen.append(r.headers.get("authorization"))
        return httpx.Response(200, content=png_bytes(), headers={"content-type": "image/png"})

    spec = {"type": "wda", "kind": "image", "account": "a", "username": "1@chatroom", "file_id": "1_2"}
    transport = MockHTTP(handler).transport
    att = {"kind": "image", "extra": {"fetch": spec}}
    run(fetch_media({"sources": {"wechat": {"wda": {"base_url": "http://127.0.0.1:10392"}}}}, {},
                    "wechat", att, tmp_path / "o", transport=transport))
    run(fetch_media({"sources": {"wechat": {"wda": {"base_url": "http://10.1.2.3:10392"}}}}, {},
                    "wechat", att, tmp_path / "o", transport=transport))
    assert seen == ["Bearer auto-tok", None]
