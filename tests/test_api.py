"""API：鉴权、Host 校验、overview 结构、设置掩码、定时任务、通道、导入与上报兜底。"""

from __future__ import annotations

import time

import pytest
import yaml
from fastapi.testclient import TestClient

from bureau.api import create_app

BASE = "http://127.0.0.1:8765"


@pytest.fixture
def client(app):
    with TestClient(create_app(app, background=False), base_url=BASE) as c:
        c.token = c.get("/api/session").json()["token"]
        c.headers.update({"X-Bureau-Token": c.token})
        yield c


def test_auth_and_host(app):
    with TestClient(create_app(app, background=False), base_url=BASE) as c:
        assert c.get("/api/health").json()["ok"] is True
        s = c.get("/api/session").json()
        assert s["token"] and s["mode"] in ("live", "demo")
        assert c.get("/api/overview").status_code == 401
        assert c.get("/api/overview", headers={"X-Bureau-Token": "wrong"}).status_code == 401
        err = c.get("/api/groups").json()["error"]
        assert err["code"] == "unauthorized" and err["hint"]
        ok = c.get("/api/overview", headers={"X-Bureau-Token": s["token"]})
        assert ok.status_code == 200
        assert c.get("/api/health", headers={"Host": "evil.com"}).status_code == 403
        assert c.get("/api/session", headers={"Host": "evil.com:8765"}).status_code == 403
        assert c.get("/api/overview", headers={"Host": "localhost:8765", "X-Bureau-Token": s["token"]}).status_code == 200
        assert c.get(f"/api/events?token=wrong").status_code == 401
        assert c.get("/api/overview", params={"token": s["token"]}).status_code == 401   # 普通接口不接受 ?token=
        h = ok.headers
        assert h["x-content-type-options"] == "nosniff" and h["x-frame-options"] == "DENY"
        assert h["referrer-policy"] == "no-referrer" and "default-src 'self'" in h["content-security-policy"]
        assert "access-control-allow-origin" not in h


def test_overview_empty_structure(client):
    ov = client.get("/api/overview").json()
    for k in ("generated_at", "mode", "window", "kpis", "platforms", "stats", "constellation", "headlines", "agents", "ticker", "llm"):
        assert k in ov, k
    assert ov["mode"] == "live" and ov["headlines"] == [] and ov["ticker"] == []
    assert ov["constellation"] == {"nodes": [], "links": []}
    k = ov["kpis"]
    assert all(k[x] == 0 for x in ("messages_24h", "messages_delta", "intel_today", "intel_delta", "groups_active",
                                   "groups_whitelisted", "snr", "signals_rising"))
    st = ov["stats"]
    assert st["keywords"] == [] and st["rising"] == [] and st["top_groups"] == [] and st["by_platform"] == []
    assert len(st["hourly"]) == 24 and len(st["heat_7x24"]) == 168
    assert [a["code"] for a in ov["agents"]] == ["SCOUT", "SWEEPER", "ANALYST", "DECODER", "STRATEGIST", "AUDITOR",
                                                 "WRITER", "COURIER"]
    assert [p["platform"] for p in ov["platforms"]] == ["wechat", "qq", "feishu"]
    assert ov["llm"]["provider"] == "offline" and ov["llm"]["cloud_consent"] is False


def test_overview_demo_is_full(app):
    from bureau.demo import seed_demo
    from bureau.pipeline.runner import RunRequest
    import asyncio

    seed_demo(app, scale=1.0)
    asyncio.run(app.runner.run(RunRequest(demo=True, dry_run=True)))
    with TestClient(create_app(app, background=False), base_url=BASE) as c:
        ov = c.get("/api/overview", headers={"X-Bureau-Token": app.config.token}).json()
    assert ov["mode"] == "demo"
    assert 30 <= len(ov["constellation"]["nodes"]) <= 60
    assert 60 <= len(ov["stats"]["keywords"]) <= 80
    assert 3 <= len(ov["stats"]["rising"]) <= 6
    assert len(ov["headlines"]) == 5 and all(h["evidence"] for h in ov["headlines"])
    assert len(ov["ticker"]) >= 10
    assert {p["health"] for p in ov["platforms"]} == {"ok"}
    assert ov["kpis"]["groups_whitelisted"] == 9 and ov["kpis"]["intel_today"] > 0
    assert ov["latest_report"]["items_total"] == ov["kpis"]["intel_today"]


def test_settings_mask_secrets(client, app):
    r = client.put("/api/settings", json={"llm": {"provider": "openai_compat",
                                                  "openai_compat": {"preset": "deepseek", "api_key": "sk-secret-abcd1234"}}})
    assert r.status_code == 200
    body = r.text
    assert "sk-secret-abcd1234" not in body and r.json()["llm"]["openai_compat"]["api_key"] == "••••1234"
    assert yaml.safe_load(app.paths.secrets.read_text(encoding="utf-8"))["llm"]["openai_compat"]["api_key"] == "sk-secret-abcd1234"
    client.put("/api/settings", json={"llm": {"openai_compat": {"api_key": "••••1234"}}})       # 掩码表示不修改
    assert app.config.secret("llm.openai_compat.api_key") == "sk-secret-abcd1234"
    assert app.config.token not in client.get("/api/settings").text
    assert client.put("/api/settings", json={"sources": {}}).status_code == 400
    assert client.put("/api/settings", json={"app": {"host": "0.0.0.0"}}).status_code == 400


def test_schedules_crud(client):
    bad = client.post("/api/schedules", json={"name": "坏任务", "cron": "每天八点"})
    assert bad.status_code == 400 and "cron" in bad.json()["error"]["message"]
    s = client.post("/api/schedules", json={"name": "午报", "cron": "0 12 * * *", "channel_ids": ["ch_local_archive"]}).json()
    assert s["next_run_at"] and s["platforms"] == ["wechat", "qq", "feishu"]
    s2 = client.put(f"/api/schedules/{s['id']}", json={"enabled": False}).json()
    assert s2["enabled"] is False and "next_run_at" not in s2
    assert len(client.get("/api/schedules").json()) == 2
    assert client.delete(f"/api/schedules/{s['id']}").json() == {"ok": True}


def test_channels_and_unimplemented_paths(client):
    kinds = {k["kind"]: k for k in client.get("/api/channel-kinds").json()}
    assert kinds["local_archive"]["available"] and len(kinds) == 10
    assert client.post("/api/channels/ch_local_archive/test").json()["ok"] is True
    assert client.post("/api/channels", json={"kind": "nope"}).status_code == 400
    r = client.post("/api/runs", json={"platforms": ["weibo"]})
    assert r.status_code == 400
    assert client.get("/api/nope").status_code == 404 and client.get("/api/nope").json()["error"]["code"] == "not_found"
    assert client.get("/").status_code == 200


def test_ingest_onebot_whitelist(client, app):
    pytest.importorskip("bureau.integrations.onebot")
    ev = {"post_type": "message", "message_type": "group", "group_id": 123456, "message_id": 99, "time": int(time.time()),
          "user_id": 1, "sender": {"nickname": "群友", "card": ""}, "message": [{"type": "text", "data": {"text": "测试上报消息"}}],
          "raw_message": "测试上报消息"}
    ev["group_name"] = "上报测试群"
    assert client.post("/api/ingest/onebot", json=ev).status_code == 204
    assert app.db.scalar("SELECT COUNT(*) FROM messages", (), 0) == 0          # 非白名单不落库
    g = app.store.get_group("qq:123456")
    assert g is not None and not g["whitelisted"]                              # 只记下群名，方便加白名单
    app.store.update_group("qq:123456", whitelisted=True)
    assert client.post("/api/ingest/onebot", json=ev).status_code == 204
    assert client.post("/api/ingest/onebot", json=ev).status_code == 204       # 重复上报去重
    assert app.db.scalar("SELECT COUNT(*) FROM messages", (), 0) == 1
    assert client.post("/api/ingest/onebot", json={"post_type": "meta_event"}).status_code == 204


def test_run_conflict_returns_409(client, app):
    from bureau.demo import seed_demo

    seed_demo(app, scale=0.35)
    r1 = client.post("/api/runs", json={"demo": True, "dry_run": True})
    r2 = client.post("/api/runs", json={"demo": True, "dry_run": True})
    assert r1.status_code == 202 and r1.json()["status"] == "queued"
    assert r2.status_code == 409 and r2.json()["error"]["code"] == "run_in_progress"
    for _ in range(150):
        if client.get(f"/api/runs/{r1.json()['id']}").json()["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert client.get(f"/api/runs/{r1.json()['id']}").json()["status"] == "success"
    assert client.get(f"/api/runs/{r1.json()['id']}/logs").json()
