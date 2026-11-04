"""消息存储（按 group_key + native_id 去重）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable

from bureau.contracts import RawMessage
from bureau.core.store.base import chunked, jdump, jload, placeholders
from bureau.core.timeutil import ensure_aware, epoch, iso


def _decode_msg(row: dict[str, Any]) -> dict[str, Any]:
    row["mentions"] = jload(row.get("mentions"), [])
    row["attachments"] = jload(row.get("attachments"), [])
    row["is_self"] = bool(row.get("is_self"))
    return row


class MessageMixin:
    db: Any
    now_iso: Any
    tz: str

    def insert_messages(self, msgs: Iterable[RawMessage], *, source: str = "collect") -> tuple[int, int]:
        """批量入库，返回 (新增数, 重复跳过数)。缺失的群会先建一条占位记录。"""
        msgs = list(msgs)
        if not msgs:
            return 0, 0
        ts_now = self.now_iso()
        inserted = 0
        touched: set[str] = set()
        with self.db.tx():
            for m in msgs:
                key = m.group_key
                if key not in touched:
                    self.db.execute(
                        "INSERT OR IGNORE INTO groups(key, platform, native_id, name, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?)",
                        (key, m.platform.value, m.group_native_id, m.group_name or m.group_native_id, ts_now, ts_now))
                    touched.add(key)
                sent = ensure_aware(m.sent_at, self.tz)
                cur = self.db.execute(
                    "INSERT OR IGNORE INTO messages(group_key, platform, native_id, sender_id, sender_name, sent_at, ts, "
                    "kind, text, reply_to, quote_text, mentions, attachments, is_self, source, created_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (key, m.platform.value, m.native_id, m.sender_id, m.sender_name or "", iso(sent, self.tz),
                     epoch(sent), m.kind.value, m.text or "", m.reply_to, m.quote_text, jdump(m.mentions),
                     jdump([a.model_dump(mode="json") for a in m.attachments]), int(m.is_self), source, ts_now))
                if cur.rowcount > 0:
                    inserted += cur.rowcount
                elif any((a.extra or {}).get("fetch") for a in m.attachments):
                    # 已入库的旧消息（v1 采集器写的）没有附件取回信息：重新拉到带 extra.fetch 的版本时补写，其它字段不动
                    self.db.execute(
                        "UPDATE messages SET attachments=? WHERE group_key=? AND native_id=? "
                        "AND attachments NOT LIKE '%\"fetch\"%'",
                        (jdump([a.model_dump(mode="json") for a in m.attachments]), key, m.native_id))
            for key in touched:
                last = self.db.query_one("SELECT sent_at FROM messages WHERE group_key=? ORDER BY ts DESC LIMIT 1", (key,))
                if last:
                    self.db.execute("UPDATE groups SET last_message_at=? WHERE key=?", (last["sent_at"], key))
        return inserted, len(msgs) - inserted

    def messages_in_window(self, keys: list[str], start: datetime, end: datetime) -> list[dict[str, Any]]:
        """[start, end) 内的消息，附带群名、按时间升序。"""
        if not keys:
            return []
        out: list[dict[str, Any]] = []
        s, e = epoch(start), epoch(end)
        for part in chunked(list(keys)):
            rows = self.db.query(
                "SELECT m.*, COALESCE(NULLIF(g.alias, ''), g.name) AS group_name, g.weight AS group_weight "
                f"FROM messages m JOIN groups g ON g.key=m.group_key WHERE m.group_key IN ({placeholders(len(part))}) "
                "AND m.ts>=? AND m.ts<? ORDER BY m.ts, m.id", [*part, s, e])
            out.extend(_decode_msg(r) for r in rows)
        out.sort(key=lambda r: (r["ts"], r["id"]))
        return out

    def count_messages(self, keys: list[str], start: datetime, end: datetime) -> int:
        if not keys:
            return 0
        total = 0
        for part in chunked(list(keys)):
            total += int(self.db.scalar(
                f"SELECT COUNT(*) FROM messages WHERE group_key IN ({placeholders(len(part))}) AND ts>=? AND ts<?",
                [*part, epoch(start), epoch(end)], 0))
        return total

    def message_by_id(self, msg_id: int) -> dict[str, Any] | None:
        row = self.db.query_one(
            "SELECT m.*, COALESCE(NULLIF(g.alias, ''), g.name) AS group_name FROM messages m "
            "JOIN groups g ON g.key=m.group_key WHERE m.id=?", (msg_id,))
        return _decode_msg(row) if row else None

    def message_context(self, msg_id: int, n: int = 5) -> dict[str, list[dict[str, Any]]]:
        row = self.db.query_one("SELECT group_key, ts, id FROM messages WHERE id=?", (msg_id,))
        if not row:
            return {"before": [], "after": []}
        cols = "id, group_key, platform, native_id, sender_name, sent_at, kind, text, reply_to"
        before = self.db.query(
            f"SELECT {cols} FROM messages WHERE group_key=? AND (ts<? OR (ts=? AND id<?)) ORDER BY ts DESC, id DESC LIMIT ?",
            (row["group_key"], row["ts"], row["ts"], row["id"], n))
        after = self.db.query(
            f"SELECT {cols} FROM messages WHERE group_key=? AND (ts>? OR (ts=? AND id>?)) ORDER BY ts, id LIMIT ?",
            (row["group_key"], row["ts"], row["ts"], row["id"], n))
        return {"before": list(reversed(before)), "after": after}

    def search_messages(self, q: str, limit: int = 50) -> list[dict[str, Any]]:
        q = (q or "").strip()
        if not q:
            return []
        if getattr(self.db, "fts_enabled", False) and (self.db.fts_tokenizer != "trigram" or len(q) >= 3):
            phrase = '"' + q.replace('"', '""') + '"'
            return self.db.query(
                "SELECT m.id, m.group_key, m.sender_name, m.sent_at, m.text FROM messages_fts f "
                "JOIN messages m ON m.id=f.rowid WHERE messages_fts MATCH ? ORDER BY m.ts DESC LIMIT ?", (phrase, limit))
        return self.db.query("SELECT id, group_key, sender_name, sent_at, text FROM messages WHERE text LIKE ? "
                             "ORDER BY ts DESC LIMIT ?", (f"%{q}%", limit))

    def purge_messages_before(self, cutoff: datetime) -> int:
        """按保留期删除原始消息（演示群不删）。"""
        return self.db.execute(
            "DELETE FROM messages WHERE ts<? AND group_key IN (SELECT key FROM groups WHERE is_demo=0)",
            (epoch(cutoff),)).rowcount

    def latest_message_ts(self, keys: list[str]) -> int | None:
        if not keys:
            return None
        best = None
        for part in chunked(list(keys)):
            v = self.db.scalar(f"SELECT MAX(ts) FROM messages WHERE group_key IN ({placeholders(len(part))})", list(part))
            if v is not None and (best is None or v > best):
                best = int(v)
        return best

    # ---------- 游标 ----------
    def get_cursor(self, key: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT * FROM cursors WHERE group_key=?", (key,))

    def set_cursor(self, key: str, *, last_ts: str | None, last_native_id: str | None,
                   collector_cursor: str | None) -> None:
        self.db.execute(
            "INSERT INTO cursors(group_key, last_ts, last_native_id, collector_cursor, updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(group_key) DO UPDATE SET last_ts=COALESCE(excluded.last_ts, cursors.last_ts), "
            "last_native_id=COALESCE(excluded.last_native_id, cursors.last_native_id), "
            "collector_cursor=COALESCE(excluded.collector_cursor, cursors.collector_cursor), updated_at=excluded.updated_at",
            (key, last_ts, last_native_id, collector_cursor, self.now_iso()))
