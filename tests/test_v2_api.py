"""v2 接口：报告 v2 字段（旧报告兼容）、assets 防路径穿越、知识库、overview.kb、设置的 research / media 与密钥。"""

from __future__ import annotations

import pytest
import yaml
from fastapi.testclient import TestClient

from bureau.api import create_app
from bureau.pipeline import b2
from tests.v2_helpers import make_demo_app, run_demo

BASE = "http://127.0.0.1:8765"


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    b2.reset()
    app = make_demo_app(tmp_path_factory.mktemp("v2api"))
    dto = run_demo(app)
    with TestClient(create_app(app, background=False), base_url=BASE) as c:
        c.headers["X-Bureau-Token"] = app.config.token
        yield app, c, dto["report_id"]
    app.close()


def test_report_v2_fields_and_v1_compat(env):
    app, c, rid = env
    d = c.get(f"/api/reports/{rid}").json()
    for k in ("sections", "articles", "resources", "media", "groups", "section_counts"):
        assert k in d, k
    a = d["articles"][0]
    for k in ("id", "seq", "title", "hook", "category", "body_md", "risk_flags", "sources", "images", "research_refs"):
        assert k in a, k
    assert {"group_name", "platform", "sender", "sent_at"} <= set(a["sources"][0])
    assert all({"kind", "title", "url", "meta"} <= set(x) for x in d["resources"])
    g = d["groups"][0]
    assert {"group_key", "group_name", "platform", "messages", "summary", "highlights", "counts"} <= set(g)
    # v1 的旧报告（没有 v2 数据）：v2 字段返回空数组 / 空对象
    app.store.save_report({"id": "rpt-v1-old", "run_id": "run-x", "title": "旧", "date_label": "d", "window_label": "w",
                           "window_start": "s", "window_end": "e", "full_md": "# 旧"}, [])
    old = c.get("/api/reports/rpt-v1-old").json()
    assert old["articles"] == [] and old["resources"] == [] and old["media"] == [] and old["groups"] == []
    assert old["sections"] == {} and old["section_counts"] == {}


def test_assets_no_path_traversal(env):
    app, c, rid = env
    d = c.get(f"/api/reports/{rid}").json()
    url = next(m["url"] for m in d["media"] if m["kind"] == "image" and m.get("url"))
    ok = c.get(url)
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png" and ok.content[:4] == b"\x89PNG"
    assert ok.headers["x-content-type-options"] == "nosniff"
    name = url.rsplit("/", 1)[-1]
    tok = app.config.token
    assert c.get(f"/api/reports/{rid}/assets/{name}", headers={"X-Bureau-Token": ""}, params={"token": tok}).status_code == 200
    assert c.get(f"/api/reports/{rid}/assets/{name}", headers={"X-Bureau-Token": ""}).status_code == 401
    for bad in ("..%2F..%2Fbureau.db", "..%5C..%5Cbureau.db", "%2E%2E%2Fsecrets.yaml", "%2E%2E", ".hidden.png",
                "nope.png", f"..%2F{rid}.html", f"..%2F{rid}.json", "x.html", "x.svg", "m1.png%00.html"):
        resp = c.get(f"/api/reports/{rid}/assets/{bad}")
        assert resp.status_code in (400, 404), bad
        assert not resp.content.startswith(b"SQLite") and b"token" not in resp.content
    # 字面量的 ../ 在请求前就被规范化，到不了这个接口（落到别的路由上也不会读到 assets 之外的文件）
    from bureau.api.routes_reports import report_asset
    from bureau.api.errors import ApiError
    for name in ("..", "../bureau.db", "..\\bureau.db", f"../{rid}.json", "sub/x.png"):
        with pytest.raises(ApiError):
            report_asset(rid, name, app)
    assert c.get(f"/api/reports/rpt-v1-old/assets/{name}").status_code == 404          # 别的报告读不到
    assert c.get(f"/api/reports/nope/assets/{name}").status_code == 404
    html = c.get(f"/api/reports/{rid}/export", params={"format": "html", "inline": 1, "token": tok},
                 headers={"X-Bureau-Token": ""})
    assert html.status_code == 200 and f'src="/api/reports/{rid}/assets/' in html.text and "img-src 'self'" in \
        html.headers["content-security-policy"]


def test_kb_endpoints_and_overview(env):
    app, c, rid = env
    lst = c.get("/api/kb").json()
    assert lst["total"] >= 8 and lst["scope"] == "demo" and lst["categories"] and lst["tags"]
    s = lst["items"][0]
    for k in ("id", "title", "category", "tags", "hook", "risk_flags", "updated_at", "created_at", "versions", "sources"):
        assert k in s, k
    one = c.get(f"/api/kb/{s['id']}").json()
    assert one["body_md"] and one["versions"] and {"at", "report_id", "note"} <= set(one["versions"][0])
    assert isinstance(one["related"], list) and one["sources"]
    ver = one["versions"][0]
    assert c.get(f"/api/kb/{s['id']}/versions/{ver['id']}").json()["body_md"]
    assert c.get(f"/api/kb/{s['id']}/versions/999999").status_code == 404
    cat = lst["categories"][0]["name"]
    assert all(x["category"] == cat for x in c.get("/api/kb", params={"category": cat}).json()["items"])
    tag = lst["tags"][0]["name"]
    assert all(tag in x["tags"] for x in c.get("/api/kb", params={"tag": tag}).json()["items"])
    assert c.get("/api/kb", params={"q": "首尾帧"}).json()["total"] >= 1
    assert c.get("/api/kb/nope").status_code == 404 and c.get("/api/kb", params={"scope": "x"}).status_code == 400
    ov = c.get("/api/overview").json()
    assert set(ov["kb"]) == {"total", "updated_today", "new_today"} and ov["kb"]["total"] == lst["total"]


def test_settings_research_media_and_secrets(env):
    app, c, _rid = env
    r = c.put("/api/settings", json={"pipeline": {"risk_policy": "label", "max_features": 10},
                                     "research": {"enabled": True, "max_searches": 20, "deepseek_api_key": "sk-ds-abcdef1234",
                                                  "github_token": "ghp_testtoken9876"},
                                     "media": {"ocr": "off", "max_images": 10}})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["research"]["deepseek_api_key"] == "••••1234" and body["research"]["github_token"] == "••••9876"
    assert "sk-ds-abcdef1234" not in r.text and "ghp_testtoken9876" not in r.text
    assert "deepseek_api_key" not in app.paths.settings.read_text(encoding="utf-8")
    sec = yaml.safe_load(app.paths.secrets.read_text(encoding="utf-8"))
    assert sec["research"] == {"deepseek_api_key": "sk-ds-abcdef1234", "github_token": "ghp_testtoken9876"}
    c.put("/api/settings", json={"research": {"deepseek_api_key": "••••1234"}})          # 掩码 = 不修改
    assert app.config.secret("research.deepseek_api_key") == "sk-ds-abcdef1234"
    c.put("/api/settings", json={"research": {"github_token": None}})                   # null = 删除
    assert app.config.secret("research.github_token") is None
    assert app.config.get("media.max_images") == 10 and app.config.get("pipeline.max_features") == 10
    for bad in ({"pipeline": {"risk_policy": "hide"}}, {"pipeline": {"max_features": 30}}, {"media": {"ocr": "cloud"}},
                {"research": {"per_article_queries": 9}}, {"research": {"provider": "google"}}, {"weird": {}}):
        assert c.put("/api/settings", json=bad).status_code == 400, bad
    for p in ("flag", "drop", "label"):
        assert c.put("/api/settings", json={"pipeline": {"risk_policy": p}}).status_code == 200
    names = [p["name"] for p in c.get("/api/prompts").json()]
    assert {"extract_v2", "article", "digest", "research_queries"} <= set(names)
