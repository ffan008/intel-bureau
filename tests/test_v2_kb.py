"""知识库合并与版本、连跑两次合并更新、schema 迁移只增不改（v1 代码可在新结构上运行）、话题合并。"""

from __future__ import annotations

import sqlite3

from bureau.core.db import Database
from bureau.core.schema import LATEST_VERSION, SCHEMA_V1
from bureau.core.store import Store
from bureau.core.store.kb import merge_body, split_updates
from bureau.pipeline.merge import cluster, topic_groups
from tests.factories import cand
from tests.v2_helpers import make_demo_app, run_demo


def _art(title: str, body: str, kws: list[str], sources: list[dict] | None = None) -> dict:
    return {"title": title, "category": "03 AI 创作实战", "tags": ["漫剧"], "hook": "h", "risk_flags": [],
            "fingerprint": "", "keywords": kws, "links": [], "body_md": body,
            "sources": sources or [{"group_name": "群A", "sender": "甲", "sent_at": "2026-10-29T10:00:00+08:00"}]}


def test_kb_merge_versions_and_update_sections(app):
    st = app.store
    kws = ["漫剧", "首尾帧", "即梦", "分镜", "镜头"]
    body1 = "# 01-即梦首尾帧做漫剧\n> 分类：…\n## 背景与群内讨论\n第一天的内容。\n"
    kb_id, status = st.kb_upsert("live", _art("即梦首尾帧做漫剧", body1, kws), day="2026-10-29", report_id="r1")
    assert status == "created"
    # 同一天重跑：同一条，正文刷新，不重复追加
    kb2, status = st.kb_upsert("live", _art("即梦首尾帧做漫剧", body1.replace("第一天", "第一天（重跑）"), kws),
                               day="2026-10-29", report_id="r1b")
    assert (kb2, status) == (kb_id, "merged") and "## 2026-10-29 更新" not in st.kb_get(kb_id)["body_md"]
    # 第二天、标题不同但核心词重叠：合并，追加「{日期} 更新」，来源合并
    body3 = "# 02-漫剧镜头一致性\n## 关键做法\n1. 固定种子\n"
    kb3, status = st.kb_upsert("live", _art("漫剧镜头一致性", body3, ["漫剧", "首尾帧", "镜头", "种子"],
                                            [{"group_name": "群B", "sender": "乙", "sent_at": "2026-10-30T09:00:00+08:00"}]),
                               day="2026-10-30", report_id="r2")
    assert (kb3, status) == (kb_id, "merged")
    row = st.kb_get(kb_id)
    assert "第一天（重跑）的内容" in row["body_md"] and "## 2026-10-30 更新" in row["body_md"]
    assert "### 关键做法" in row["body_md"]                                           # 更新一节里标题降一级
    assert {s["group_name"] for s in row["sources"]} == {"群A", "群B"}
    vs = st.kb_versions(kb_id)
    assert len(vs) == 3 and "新建" in vs[0]["note"] and "同日重跑" in vs[1]["note"] and "合并更新" in vs[2]["note"]
    # 不相干的话题新建；同一次运行里两篇不会并进同一条
    other, status = st.kb_upsert("live", _art("公众号流量主", "# x\n", ["公众号", "流量主", "阅读"]), day="2026-10-30",
                                 report_id="r2")
    assert status == "created" and other != kb_id
    claimed = {kb_id}
    k4, status = st.kb_upsert("live", _art("漫剧另一篇", "# y\n", kws), day="2026-10-30", report_id="r2", claimed=claimed)
    assert status == "created" and k4 != kb_id
    assert st.kb_counts("live", "2099-01-01")["total"] == 3 and st.kb_list("demo")[1] == 0     # scope 隔离
    rows, total = st.kb_list("live", q="首尾帧")
    assert total >= 1 and rows[0]["id"] == kb_id


def test_merge_body_pure():
    base, ups = split_updates("# t\n正文\n\n## 2026-10-30 更新\n\n新内容\n")
    assert base == "# t\n正文" and ups == {"2026-10-30": "新内容"}
    again = merge_body("# t\n正文\n\n## 2026-10-30 更新\n\n旧\n", "2026-10-29", "# 新标题\n## 做法\n改过", "2026-10-30")
    assert again.count("## 2026-10-30 更新") == 1 and "### 做法" in again and "旧" not in again


def test_second_run_merges_into_kb(tmp_path):
    app = make_demo_app(tmp_path / "kb")
    try:
        first = run_demo(app)
        second = run_demo(app)
        m1 = {s["name"]: s for s in first["stages"]}["archive"]["metrics"]
        m2 = {s["name"]: s for s in second["stages"]}["archive"]["metrics"]
        assert m1["kb_new"] >= 8 and m1["kb_merged"] == 0
        assert m2["kb_new"] == 0 and m2["kb_merged"] == m1["kb_new"]                   # 第二次全部是合并更新
        rows, total = app.store.kb_list("demo", limit=100)
        assert total == m1["kb_new"] and all(r["n_versions"] == 2 for r in rows)
        r2 = app.store.get_report(second["report_id"])
        assert all(a["kb_id"] for a in r2["v2_data"]["articles"])
    finally:
        app.close()


def test_migration_adds_only_and_v1_code_still_works(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA_V1)
    conn.execute("INSERT INTO reports(id, run_id, title, date_label, window_label, window_start, window_end, created_at) "
                 "VALUES('rpt-old','run-old','旧报告','2026-10-28','w','s','e','2026-10-28T08:00:00+08:00')")
    conn.execute("PRAGMA user_version=1")
    conn.commit()
    conn.close()
    db = Database(path, backup_dir=tmp_path / "backups")
    try:
        assert db.user_version == LATEST_VERSION == 2
        assert {"kb_articles", "kb_versions"} <= set(db.tables()) and db.kb_fts_enabled
        assert list((tmp_path / "backups").glob("bureau-v1-*.db"))                       # 迁移前已备份
        store = Store(db)
        old = store.get_report("rpt-old")
        assert old["title"] == "旧报告" and old["v2_data"] == {}                         # 已有数据不变
        # v1 代码的写法（显式列清单、不带 v2_data）在新结构上照常可用
        store.save_report({"id": "rpt-v1", "run_id": "r", "title": "t", "date_label": "d", "window_label": "w",
                           "window_start": "s", "window_end": "e"}, [])
        assert store.get_report("rpt-v1")["v2_data"] == {}
        from bureau.core.dto import report_dto
        dto = report_dto(old, [])
        assert dto["articles"] == [] and dto["resources"] == [] and dto["media"] == [] and dto["groups"] == []
        assert dto["sections"] == {} and dto["section_counts"] == {}
    finally:
        db.close()


def test_topic_merge_cross_group_and_flag_isolation():
    cs = [cand("即梦首尾帧做漫剧的流程", tags=["漫剧", "首尾帧", "分镜"], group="wechat:a"),
          cand("漫剧试点：首尾帧每集五小时", tags=["漫剧", "首尾帧", "试点"], group="feishu:b"),
          cand("漫剧分镜表怎么写", tags=["漫剧", "分镜", "景别"], group="qq:c"),
          cand("公众号流量主复盘", tags=["公众号", "流量主"], group="wechat:a"),
          cand("代过学生认证", tags=["学生认证", "漫剧", "首尾帧"], risks=["违法高危"], group="qq:c")]
    points, _ = cluster(cs, 0.35)
    topics = [sorted(i for k in t for i in points[k]) for t in topic_groups(cs, points)]
    assert [0, 1, 2] in topics                                                          # 三个群的同一话题合并
    assert [3] in topics and [4] in topics                                              # 违法高危不与普通话题合并
