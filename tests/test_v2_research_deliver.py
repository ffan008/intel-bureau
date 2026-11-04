"""研究模块缺失时的兜底、research 的 mock 注入（费用计入、检索词不含群名昵称）、deliver 顺序与 doc_links 注入。"""

from __future__ import annotations

import asyncio

from bureau.contracts import DeliveryResult
from bureau.llm.factory import Resolved
from bureau.pipeline import STAGE_FUNCS, b2
from bureau.pipeline.runner import RunRequest
from tests.v2_helpers import FakeCloud, fake_research_module, install_module, make_demo_app, run_demo

BEFORE = ("collect", "clean", "stats", "segment", "extract", "merge", "score", "verify")


def _prepared(app):
    rc = app.runner.prepare(RunRequest(demo=True, dry_run=True))

    async def go():
        for n in BEFORE:
            await STAGE_FUNCS[n](rc)
    asyncio.run(go())
    return rc


def test_missing_b2_modules_fall_back(tmp_path, monkeypatch):
    install_module(monkeypatch, "bureau.research", None)
    install_module(monkeypatch, "bureau.media", None)
    app = make_demo_app(tmp_path / "nob2", privacy={"cloud_llm_consent": True})
    try:
        assert b2.research_api()[0] is None and b2.media_api()[0] is None
        dto = run_demo(app)
        assert dto["status"] == "success", dto.get("error")
        assert all(s["status"] == "done" for s in dto["stages"])
        logs = [lg["message"] for lg in app.store.run_logs(dto["id"])]
        assert any("跳过媒体子步骤" in m for m in logs) and any("跳过链接增强" in m for m in logs)
        r = app.store.get_report(dto["report_id"])
        arts = r["v2_data"]["articles"]
        assert len(arts) >= 8 and all("## 扩展研究" in a["body_md"] for a in arts)
        assert all("未做联网扩展" in a["body_md"] for a in arts)              # 没有模型：不写扩展研究，其余照常
        assert r["v2_data"]["resources"]                                     # 链接按本地规则分类
    finally:
        app.close()
        b2.reset()


def test_research_mock_injected(tmp_path, monkeypatch):
    queries: list[str] = []
    install_module(monkeypatch, "bureau.research", fake_research_module(queries))
    install_module(monkeypatch, "bureau.media", None)
    app = make_demo_app(tmp_path / "mock", privacy={"cloud_llm_consent": True},
                        research={"per_article_queries": 2, "max_searches": 6, "max_fetches": 4})
    cloud = FakeCloud()
    try:
        rc = _prepared(app)
        monkeypatch.setattr("bureau.pipeline.compose.resolve_provider",
                            lambda _app: Resolved(cloud, "test", "测试用假模型"))
        asyncio.run(STAGE_FUNCS["compose"](rc))
        asyncio.run(STAGE_FUNCS["render"](rc))
        assert 0 < len(queries) <= 6                                          # 受 max_searches 约束
        names = {m.sender for m in rc.clean} | {g["name"] for g in rc.groups}
        for q in queries:                                                     # 检索词里没有群名、昵称、手机号
            assert not any(n in q for n in names if len(n) >= 2), q
            assert "138" not in q
        assert rc.totals["research_searches"] == len(queries)
        assert rc.totals["research_cost_cny"] > 0 and rc.totals["cost_cny"] >= rc.totals["research_cost_cny"]
        researched = [it for it in rc.items if it.research]
        assert researched and all(1 <= len(it.research) <= 5 for it in researched)
        body = next(a["body_md"] for a in rc.report["v2_data"]["articles"] if "[1]" in a["body_md"])
        assert "公开资料说明了参数含义[1]" in body and "https://example.org/doc/" in body
        gh = [x for it in rc.items for x in it.links if x["kind"] == "github"]
        assert gh and gh[0]["meta"].get("stars") == 1234
        assert all(x.get("code") != "zzzz" for it in rc.items for x in it.links)   # 原文里没有的提取码不收
        assert "article" in cloud.tasks and "digest" in cloud.tasks
        assert all(not it.research for it in rc.items if "违法高危" in it.risk_flags)
    finally:
        app.runner._lock.release()
        app.close()
        b2.reset()


def test_deliver_doc_channel_first_and_doc_links(tmp_path, monkeypatch):
    app = make_demo_app(tmp_path / "dlv")
    seen: list[tuple[str, str]] = []

    async def fake_send(_app, ch, payload, **_kw):
        seen.append((ch["kind"], payload.summary_md))
        await asyncio.sleep(0.01)
        url = "https://example.feishu.cn/wiki/DemoToday" if ch["kind"] == "feishu_doc" else None
        return DeliveryResult(ok=True, channel_id=ch["id"], kind=ch["kind"], detail="ok", url=url)

    monkeypatch.setattr("bureau.pipeline.deliver.send_via", fake_send)
    try:
        doc = app.store.create_channel("ch_doc", "feishu_doc", "飞书文档", True, {})
        hook = app.store.create_channel("ch_hook", "wecom_webhook", "企业微信", True, {})
        dto = run_demo(app, dry_run=False, channel_ids=[hook["id"], doc["id"], "ch_local_archive"])
        assert dto["status"] == "success", dto.get("error")
        assert seen[0][0] == "feishu_doc" and len(seen) == 3                  # 文档类通道先投
        assert "今日风向标直达：http://127.0.0.1" in seen[0][1]                 # 投文档时还没有链接
        for kind, summary in seen[1:]:                                        # 其它通道拿到的是带文档链接的推送版
            assert "今日风向标直达：https://example.feishu.cn/wiki/DemoToday" in summary, kind
        r = app.store.get_report(dto["report_id"])
        assert r["v2_data"]["doc_links"] == {"feishu_doc": "https://example.feishu.cn/wiki/DemoToday"}
        assert "example.feishu.cn" in r["summary_md"] and "example.feishu.cn" in r["summary_text"]
        assert len(r["summary_md"]) <= 1800
    finally:
        app.close()
