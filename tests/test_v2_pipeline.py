"""v2 演示全流程：板块完整性、纯 CSS 切换、风险不降权、违法高危只进风险板块、隐私剔除、提示词逐字一致、资源分类。"""

from __future__ import annotations

import re

import pytest

from bureau.core.constants import DISCLAIMER, SECTION_KEYS, SECTION_TITLES
from bureau.pipeline import b2
from tests.v2_helpers import PRIVACY_MARK, PRIVACY_PHONE, html_of, make_demo_app, run_demo

ARTICLE_HEADINGS = ("## 背景与群内讨论", "## 关键做法", "## 提示词 / 参数原文", "## 扩展研究", "## 资源",
                    "## 适用范围、成本与数据", "## 风险提示")


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    b2.reset()
    app = make_demo_app(tmp_path_factory.mktemp("v2demo"))
    dto = run_demo(app)
    assert dto["status"] == "success", dto.get("error")
    report = app.store.get_report(dto["report_id"])
    yield app, dto, report, app.store.report_items(dto["report_id"])
    app.close()


def test_twelve_sections_complete(demo):
    app, dto, r, items = demo
    v2 = r["v2_data"]
    assert list(v2["sections"]) == SECTION_KEYS and list(v2["section_counts"]) == SECTION_KEYS
    assert all(v2["sections"][k].strip() for k in SECTION_KEYS)
    html = html_of(app, r)
    ids = re.findall(r'<section class="pane" id="([a-z]+)">', html)
    assert sorted(ids) == sorted(SECTION_KEYS) and ids[-1] == "overview"          # 总览放最后（默认显示）
    for k in SECTION_KEYS:
        assert f'href="#{k}">{SECTION_TITLES[k]}<span class="n">{v2["section_counts"][k]}</span>' in html
    assert len(v2["articles"]) >= 8 and v2["section_counts"]["articles"] == len(v2["articles"])
    kinds = {x["kind"] for x in v2["resources"]}
    assert len(kinds & {"github", "x", "wechat_article", "netdisk", "video", "doc"}) >= 3


def test_articles_follow_template(demo):
    _app, _dto, r, _items = demo
    for a in r["v2_data"]["articles"]:
        body = a["body_md"]
        assert body.startswith(f"# {a['seq']:02d}-"), body[:40]
        assert "> 分类：" in body and "**一句话**：" in body
        pos = [body.find(h + "\n") for h in ARTICLE_HEADINGS]
        assert all(p > 0 for p in pos) and pos == sorted(pos), (a["title"], pos)
        assert DISCLAIMER in body and "\n---\n" in body and "参考：" in body
    assert [a["seq"] for a in r["v2_data"]["articles"]] == list(range(1, len(r["v2_data"]["articles"]) + 1))


def test_html_pure_css_tabs_no_script(demo):
    app, _dto, r, _items = demo
    html = html_of(app, r).lower()
    assert "<script" not in html and "javascript:" not in html
    assert not re.search(r"\son[a-z]+\s*=", html)                       # 没有内联事件处理器
    assert ".pane:target{display:block}" in html and ".pane:target~#overview{display:none}" in html
    assert "max-width:760px" in html and "16px/1.8" in html and "<details" in html
    assert not re.search(r"<link[^>]+stylesheet", html) and "@import" not in html


def test_risk_items_not_downranked_and_have_disclaimer(demo):
    app, _dto, r, items = demo
    from bureau.pipeline.score import total_score

    risky = [i for i in items if set(i["risk_flags"]) & {"合规风险", "账号风险", "金钱风险", "广告引流"}
             and "违法高危" not in i["risk_flags"]]
    assert risky
    weights = app.config.get("pipeline.weights")
    rep = float(app.config.get("pipeline.repeat_penalty"))
    for i in risky:                                                    # label：总分里没有任何风险扣分
        assert i["score"] == total_score(i["scores"], weights, [], i["trend"], 0.0, rep), i["title"]
    for a in r["v2_data"]["articles"]:
        if a["risk_flags"]:
            assert DISCLAIMER in a["body_md"]
    risks_md = r["v2_data"]["sections"]["risks"]
    assert risks_md.count(DISCLAIMER) >= r["v2_data"]["section_counts"]["risks"]   # 每条风险条目末尾都有


def test_illegal_only_in_risks_section(demo):
    app, _dto, r, items = demo
    illegal = [i for i in items if "违法高危" in i["risk_flags"]]
    assert len(illegal) >= 1
    assert not any(i["is_feature"] or i["is_headline"] for i in illegal)
    v2 = r["v2_data"]
    for i in illegal:
        assert not (i["steps"] or i["sop_steps"] or i["links"] or i["prompts"])   # 不写成分步教程
        key = i["title"][:12]
        assert key in v2["sections"]["risks"]
        others = {k: s for k, s in v2["sections"].items() if k != "risks"}
        assert not [k for k, s in others.items() if key in s], key
        assert all(key not in a["body_md"] for a in v2["articles"])
        assert all(key not in j["text"] + j.get("basis", "") for j in r["judgments"])
    html = html_of(app, r)
    panes = dict(re.findall(r'<section class="pane" id="([a-z]+)">(.*?)</section>', html, re.S))
    for i in illegal:
        assert i["title"][:12] in panes["risks"]
        assert all(i["title"][:12] not in body for k, body in panes.items() if k != "risks")


def test_privacy_item_removed(demo):
    app, dto, r, items = demo
    stages = {s["name"]: s for s in dto["stages"]}
    assert stages["score"]["metrics"]["privacy_dropped"] >= 1
    assert PRIVACY_PHONE not in r["full_md"] and PRIVACY_MARK not in r["full_md"]
    assert PRIVACY_PHONE not in html_of(app, r) and PRIVACY_MARK not in html_of(app, r)
    assert all(PRIVACY_MARK not in i["title"] + i["summary"] for i in items)


def test_prompts_verbatim_from_database(demo):
    app, _dto, r, items = demo
    prompts = [p for i in items for p in i["prompts"]]
    assert len(prompts) >= 2
    html = html_of(app, r)
    for p in prompts:
        msg = app.store.message_by_id(int(p["message_id"]))
        assert p["text"] in msg["text"], p["text"][:40]                           # 原文的连续子串，一字不改
        assert p["verbatim"] is True
        assert p["text"] in r["v2_data"]["sections"]["prompts"]
        assert p["text"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") in html
    assert any("【画面风格】" in p["text"] and "\n【构图】" in p["text"] for p in prompts)   # 多行模板保留换行
    assert any("--stylize 150 --v 7" in p["text"] for p in prompts)


def test_netdisk_code_copied_from_original(demo):
    app, _dto, r, _items = demo
    nd = [x for x in r["v2_data"]["resources"] if x["kind"] == "netdisk"]
    assert nd and any(x.get("code") == "a7k2" for x in nd)
    for x in nd:
        if x.get("code"):
            assert x["code"] in r["v2_data"]["sections"]["resources"]
    assert all(x["shared_by"] and x["group_name"] and x["sent_at"] for x in r["v2_data"]["resources"])


def test_assets_copied_and_relative(demo):
    app, _dto, r, _items = demo
    v2 = r["v2_data"]
    imgs = [m for m in v2["media"] if m["kind"] == "image" and m.get("url")]
    assert len(imgs) >= 3
    html = html_of(app, r)
    for src in re.findall(r'<img src="([^"]+)"', html):
        assert src.startswith(f"{r['id']}_assets/")
        assert (app.paths.reports / r["window_end"][:10] / src).is_file() or \
            any((p / src).is_file() for p in app.paths.reports.iterdir() if p.is_dir())
