"""B 的模块缺失时显示"未实现"而不崩溃；SPA 托管与回退；multipart 解析。"""

from __future__ import annotations

import asyncio
import sys

from fastapi.testclient import TestClient

from bureau import channels, collectors
from bureau.api import create_app
from bureau.api.multipart import parse_multipart
from bureau.cli import print_table
from bureau.core.app import AppContext
from bureau.core.doctor import run_checks
from bureau.core.paths import Paths

BASE = "http://127.0.0.1:8765"


def _hide_b_modules(monkeypatch) -> None:
    for k in list(collectors.COLLECTOR_REGISTRY):
        if not k.startswith("demo."):
            monkeypatch.setitem(collectors.COLLECTOR_REGISTRY, k, f"bureau.collectors.not_there_{k.replace('.', '_')}:X")
    for k in list(channels.CHANNEL_REGISTRY):
        if k != "local_archive":
            monkeypatch.setitem(channels.CHANNEL_REGISTRY, k, f"bureau.channels.not_there_{k}:X")
    monkeypatch.setitem(sys.modules, "bureau.integrations.onebot", None)
    monkeypatch.setitem(sys.modules, "bureau.collectors.file_import", None)


def test_missing_b_modules_degrade_gracefully(app, monkeypatch, capsys):
    _hide_b_modules(monkeypatch)
    app.config.update_settings({"sources": {"qq": {"enabled": True}}})
    rows = asyncio.run(run_checks(app))
    by = {r["id"]: r for r in rows}
    assert by["platform.qq"]["status"] == "unconfigured" and "未实现" in by["platform.qq"]["detail"]
    assert by["platform.wechat"]["status"] == "disabled" and "未实现" in by["platform.wechat"]["detail"]
    assert by["module.parse_export"]["status"] == "unconfigured" and "未实现" in by["module.parse_export"]["detail"]
    assert by["module.parse_onebot_event"]["status"] == "unconfigured"
    assert "未实现" in by["channel.kinds"]["detail"]
    print_table(rows)
    assert "未实现" in capsys.readouterr().out
    with TestClient(create_app(app, background=False), base_url=BASE) as c:
        c.headers["X-Bureau-Token"] = app.config.token
        plats = c.get("/api/platforms").json()
        assert all(not a["available"] and "未实现" in a["label"] for p in plats for a in p["adapters"])
        qq = next(p for p in plats if p["platform"] == "qq")
        assert qq["health"] in ("unconfigured", "disabled")
        assert c.post("/api/platforms/qq/test").json()["health"] == "unconfigured"
        kinds = {k["kind"]: k["available"] for k in c.get("/api/channel-kinds").json()}
        assert kinds["local_archive"] and not kinds["pushplus"]
        r = c.post("/api/import", json={"platform": "qq", "group_name": "群", "text": "张三\n2026年10月25日 18:14\n你好"})
        assert r.status_code == 501 and "尚未安装" in r.json()["error"]["message"]
        r = c.post("/api/ingest/onebot", json={"post_type": "message"})
        assert r.status_code == 501
        r = c.post("/api/platforms/qq/refresh-groups")
        assert r.status_code == 501 and r.json()["error"]["code"] == "collector_unavailable"
        assert c.post("/api/channels", json={"kind": "pushplus", "config": {}}).status_code == 501
        assert c.get("/api/overview").status_code == 200
        assert c.get("/api/doctor").status_code == 200


def test_spa_hosting_and_fallback(tmp_path):
    from tests.conftest import make_paths

    p = make_paths(tmp_path)
    paths = Paths(root=tmp_path, data=p.data, config=p.config)
    dist = tmp_path / "web" / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>SPA</title>", encoding="utf-8")
    (dist / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    ctx = AppContext(paths)
    try:
        with TestClient(create_app(ctx, background=False), base_url=BASE) as c:
            assert "SPA" in c.get("/").text
            assert "SPA" in c.get("/reports").text                         # 前端路由回退到 index.html
            js = c.get("/assets/app.js")
            assert js.status_code == 200 and "javascript" in js.headers["content-type"]
            assert "immutable" in js.headers["cache-control"]
            assert c.get("/assets/missing.js").status_code == 404
            assert c.get("/..%2fREADME.md").status_code == 404                # 不能读 dist 之外的文件
            assert c.get("/api/unknown", headers={"X-Bureau-Token": ctx.config.token}).status_code == 404
    finally:
        ctx.close()


def test_placeholder_when_no_dist(tmp_path):
    from tests.conftest import make_paths

    p = make_paths(tmp_path)
    ctx = AppContext(Paths(root=tmp_path, data=p.data, config=p.config))
    try:
        with TestClient(create_app(ctx, background=False), base_url=BASE) as c:
            r = c.get("/")
            assert r.status_code == 200 and "web/dist" in r.text and "npm run build" in r.text
    finally:
        ctx.close()


def test_multipart_parser():
    boundary = "----x"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"platform\"\r\n\r\nqq\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"group_name\"\r\n\r\n水彩手绘研习社\r\n"
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"聊天记录.txt\"\r\n"
            f"Content-Type: text/plain\r\n\r\n张三\n2026年10月25日 18:14\n你好\r\n--{boundary}--\r\n").encode("utf-8")
    fields, files = parse_multipart(f"multipart/form-data; boundary={boundary}", body)
    assert fields == {"platform": "qq", "group_name": "水彩手绘研习社"}
    name, content = files["file"]
    assert name == "聊天记录.txt" and content.decode("utf-8").startswith("张三")
