"""runner 演示全流程、报告渲染（计数自洽）、锁与取消。"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest

from bureau.core.constants import SECTION_KEYS, SECTION_TITLES, STAGES
from bureau.core.textutil import strip_ws
from bureau.pipeline.runner import RunBusyError, RunRequest


@pytest.fixture
def demo_run(demo_app):
    dto = asyncio.run(demo_app.runner.run(RunRequest(demo=True, dry_run=True)))
    return demo_app, dto


def test_demo_run_completes_all_stages(demo_run):
    app, dto = demo_run
    assert dto["status"] == "success", dto.get("error")
    assert [s["name"] for s in dto["stages"]] == STAGES
    assert all(s["status"] == "done" for s in dto["stages"]), [(s["name"], s["status"]) for s in dto["stages"]]
    assert dto["trigger"] == "demo" and dto["dry_run"] is True
    t = dto["totals"]
    assert t["messages_raw"] > t["messages_clean"] > 0 and t["items"] > 0 and t["llm_provider"] == "offline"
    report = app.store.get_report(dto["report_id"])
    for kind in ("md", "html", "json"):
        assert Path(report["files"][kind]).is_file()
    assert app.store.deliveries_for(dto["report_id"]) == []          # dry_run 不投递
    logs = app.store.run_logs(dto["id"])
    assert any(lg["source"] == "DECODER" for lg in logs)


def test_report_counts_are_consistent(demo_run):
    app, dto = demo_run
    r = app.store.get_report(dto["report_id"])
    items = app.store.report_items(dto["report_id"])
    md = r["full_md"]
    header = re.search(r"情报 (\d+) 条（新 (\d+) · 持续 (\d+) · 重复 (\d+)）", md)
    assert header, md[:300]
    total, new, dev, rep = map(int, header.groups())
    assert total == len(items) == r["items_total"] == new + dev + rep
    assert new == sum(i["trend"] == "new" for i in items) and rep == sum(i["trend"] == "repeat" for i in items)
    eff = re.search(r"有效消息 ([\d,]+) / ([\d,]+)", md)
    assert int(eff.group(1).replace(",", "")) == r["stats"]["messages_clean"]
    assert int(eff.group(2).replace(",", "")) == r["stats"]["messages_raw"]
    heads = [i for i in items if i["is_headline"]]
    assert len(heads) == 5
    # v2：full_md 按 12 个板块分节，标题里的计数与 section_counts 一致；专题从 01 起连续编号
    v2 = r["v2_data"]
    titles = re.findall(r"^## (.+?)（(\d+)）$", md, re.M)
    assert [t for t, _ in titles] == [SECTION_TITLES[k] for k in SECTION_KEYS]
    assert {k: int(n) for k, (_, n) in zip(SECTION_KEYS, titles)} == v2["section_counts"]
    arts = md.split("## 专题文章")[1].split("## 资源库")[0]
    seqs = re.findall(r"^### (\d{2})-", arts, re.M)
    assert seqs == [f"{i:02d}" for i in range(1, len(v2["articles"]) + 1)] and len(seqs) >= 8
    sec1 = md.split("## 今日总览")[1].split("## 专题文章")[0].split("### 今日风向")[1].split("###")[0]
    nums = re.findall(r"^(\d+)\. ", sec1, re.M)
    assert nums == [str(i) for i in range(1, len(nums) + 1)] and 3 <= len(nums) <= 5
    assert [i["rank"] for i in items] == list(range(1, len(items) + 1))
    for h in heads:
        assert h["evidence"], h["title"]
        for ev in h["evidence"]:                                       # 证据是原文子串
            m = app.store.message_by_id(int(ev["message_id"]))
            assert strip_ws(ev["quote"]) in strip_ws(m["text"] + "".join(a.get("url") or "" for a in m["attachments"]))
    assert len(r["summary_md"]) <= 1800 and "今日风向标直达：" in r["summary_md"]
    assert f"今日 {len(v2['articles'])} 篇深度实操拆解" in r["summary_md"]
    assert "**" not in r["summary_text"]
    assert any(set(i["risk_flags"]) & {"合规风险", "账号风险"} for i in items)     # 灰色内容被标出
    # v2 label 策略：风险条目可以进头条和专题；违法高危不能
    assert all("违法高危" not in i["risk_flags"] for i in items if i["is_headline"] or i["is_feature"])


def test_html_is_self_contained(demo_run):
    app, dto = demo_run
    r = app.store.get_report(dto["report_id"])
    html = Path(r["files"]["html"]).read_text(encoding="utf-8")
    assert html.startswith("<!doctype html>") and '<html lang="zh-CN">' in html and "<style>" in html
    assert "<script" not in html.lower()
    # 没有本地外链资源；唯一允许的是同目录 <report_id>_assets/ 下的图片（相对路径）
    rid = re.escape(dto["report_id"])
    assert not re.search(rf'(src|href)="(?!https?://)(?!{rid}_assets/)[^"#]', html)
    assert not re.search(r"<link[^>]+stylesheet", html)
    data = json.loads(Path(r["files"]["json"]).read_text(encoding="utf-8"))
    assert len(data["items"]) == r["items_total"]


def test_second_run_is_idempotent_and_lock(demo_app):
    async def main():
        first = await demo_app.runner.start(RunRequest(demo=True, dry_run=True))
        with pytest.raises(RunBusyError):
            await demo_app.runner.start(RunRequest(demo=True, dry_run=True))
        await demo_app.runner.wait_idle(30)
        second = await demo_app.runner.run(RunRequest(demo=True, dry_run=True))
        return first, second

    first, second = asyncio.run(main())
    a = demo_app.store.report_items(demo_app.store.get_run(first["id"])["report_id"])
    b = demo_app.store.report_items(second["report_id"])
    assert [i["title"] for i in a] == [i["title"] for i in b]           # 同一窗口重跑结果一致
    assert [i["trend"] for i in a] == [i["trend"] for i in b]


def test_cancel_before_and_during(demo_app):
    async def main():
        dto = await demo_app.runner.start(RunRequest(demo=True, dry_run=True))
        assert demo_app.runner.cancel(dto["id"])
        await demo_app.runner.wait_idle(30)
        return demo_app.store.get_run(dto["id"])

    run = asyncio.run(main())
    assert run["status"] == "cancelled"
    assert not demo_app.runner.busy
    again = asyncio.run(demo_app.runner.run(RunRequest(demo=True, dry_run=True)))   # 锁已释放
    assert again["status"] == "success"


def test_non_dry_run_delivers_to_local_archive(demo_app):
    dto = asyncio.run(demo_app.runner.run(RunRequest(demo=True, dry_run=False)))
    assert dto["status"] == "success"
    ds = demo_app.store.deliveries_for(dto["report_id"])
    assert [d["kind"] for d in ds] == ["local_archive"] and ds[0]["ok"]
    assert demo_app.store.memory_recent("demo", "2000-01-01")             # 真实投递后更新话题记忆
