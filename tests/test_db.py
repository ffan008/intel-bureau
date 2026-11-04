"""数据库迁移、去重、FTS、默认通道与定时任务。"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from bureau.contracts import GroupInfo, Platform, RawMessage
from bureau.core.db import Database
from bureau.core.schema import LATEST_VERSION
from bureau.core.store import Store

TZ = ZoneInfo("Asia/Shanghai")
EXPECTED = {"groups", "messages", "cursors", "runs", "run_stages", "run_logs", "reports", "intel_items",
            "topic_memory", "keyword_daily", "schedules", "channels", "deliveries", "kv"}


def _msg(i: int, text: str = "测试消息内容", group: str = "g1") -> RawMessage:
    return RawMessage(platform=Platform.QQ, group_native_id=group, group_name="测试群", native_id=str(i),
                      sender_name=f"用户{i % 3}", sent_at=datetime(2026, 10, 27, 10, 0, tzinfo=TZ) + timedelta(minutes=i),
                      text=text)


def test_migration_creates_all_tables(paths):
    db = Database(paths.db)
    try:
        assert db.user_version == LATEST_VERSION
        assert EXPECTED <= set(db.tables())
        cols = {r["name"] for r in db.query("PRAGMA table_info(groups)")}
        assert "is_demo" in cols
        assert db.query_one("PRAGMA journal_mode")["journal_mode"].lower() == "wal"
        assert db.fts_enabled
    finally:
        db.close()
    db2 = Database(paths.db)                      # 二次打开不重复迁移
    assert db2.user_version == LATEST_VERSION
    db2.close()


def test_insert_dedupe_and_fts(paths):
    db = Database(paths.db)
    store = Store(db)
    try:
        store.upsert_group(GroupInfo(platform=Platform.QQ, native_id="g1", name="测试群"), whitelisted=True)
        ins, dup = store.insert_messages([_msg(i, f"第{i}条：Claude Code 的技能写法") for i in range(10)])
        assert (ins, dup) == (10, 0)
        ins, dup = store.insert_messages([_msg(i) for i in range(5, 15)])
        assert (ins, dup) == (5, 5)
        assert db.scalar("SELECT COUNT(*) FROM messages") == 15
        hits = store.search_messages("技能写法")
        assert len(hits) == 10
        g = store.get_group("qq:g1")
        assert g["whitelisted"] and g["last_message_at"]
    finally:
        db.close()


def test_reinsert_backfills_attachment_fetch_only(paths):
    """v1 采集器入库的旧消息没有 extra.fetch；重新拉到带 fetch 的版本时只补写附件，正文等字段不变，也不算新增。"""
    from bureau.contracts import Attachment, MessageKind

    db = Database(paths.db)
    store = Store(db)
    try:
        old = _msg(1, "[图片]")
        old.kind = MessageKind.IMAGE
        old.attachments = [Attachment(kind="image", title="a.png")]
        assert store.insert_messages([old]) == (1, 0)
        new = _msg(1, "改过的正文不应写入")
        new.kind = MessageKind.IMAGE
        new.attachments = [Attachment(kind="image", title="a.png", extra={"fetch": {"type": "local", "path": "x.png"}})]
        assert store.insert_messages([new]) == (0, 1)
        row = db.query_one("SELECT text, attachments FROM messages WHERE native_id='1'")
        assert row["text"] == "[图片]"
        assert '"fetch"' in row["attachments"] and "x.png" in row["attachments"]
        newer = _msg(1, "[图片]")
        newer.attachments = [Attachment(kind="image", extra={"fetch": {"type": "local", "path": "y.png"}})]
        store.insert_messages([newer])                      # 已有 fetch 的不再覆盖
        assert "x.png" in db.query_one("SELECT attachments FROM messages WHERE native_id='1'")["attachments"]
    finally:
        db.close()


def test_threaded_writes(paths):
    db = Database(paths.db)
    store = Store(db)
    store.upsert_group(GroupInfo(platform=Platform.QQ, native_id="g1", name="测试群"))
    errors: list[Exception] = []

    def worker(base: int) -> None:
        try:
            store.insert_messages([_msg(base + i) for i in range(50)])
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(k * 1000,)) for k in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert db.scalar("SELECT COUNT(*) FROM messages") == 200
    db.close()


def test_bootstrap_defaults(app):
    chans = app.store.list_channels()
    assert [c["kind"] for c in chans] == ["local_archive"]
    scheds = app.store.list_schedules()
    assert len(scheds) == 1 and scheds[0]["name"] == "晨报" and scheds[0]["cron"] == "0 8 * * *"
    assert scheds[0]["channel_ids"] == [chans[0]["id"]]
    # 删除后不会重建
    app.store.delete_schedule(scheds[0]["id"])
    from bureau.core.app import bootstrap_defaults

    bootstrap_defaults(app)
    assert app.store.list_schedules() == []
