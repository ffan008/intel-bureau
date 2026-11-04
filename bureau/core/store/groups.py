"""群（白名单）存储。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bureau.contracts import GroupInfo
from bureau.core.store.base import chunked, jdump, jload, placeholders
from bureau.core.timeutil import epoch


def _decode_group(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row["tags"] = jload(row.get("tags"), [])
    row["extra"] = jload(row.get("extra"), {})
    row["whitelisted"] = bool(row.get("whitelisted"))
    row["is_demo"] = bool(row.get("is_demo"))
    return row


class GroupMixin:
    db: Any
    now_iso: Any

    def upsert_group(self, g: GroupInfo, *, is_demo: bool = False,
                     whitelisted: bool | None = None) -> tuple[dict[str, Any], bool]:
        """插入或更新群信息；不会改动已有的白名单、权重、别名、标签。返回 (群, 是否新建)。"""
        key, ts = g.key, self.now_iso()
        with self.db.tx():
            existing = self.db.query_one("SELECT key, extra FROM groups WHERE key=?", (key,))
            if existing is None:
                self.db.execute(
                    "INSERT INTO groups(key, platform, native_id, name, member_count, avatar_url, whitelisted, "
                    "weight, tags, is_demo, extra, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (key, g.platform.value, g.native_id, g.name or g.native_id, g.member_count, g.avatar_url,
                     int(bool(whitelisted)), 1.0, "[]", int(is_demo), jdump(g.extra or {}), ts, ts),
                )
                created = True
            else:
                extra = jload(existing["extra"], {}) or {}
                extra.update(g.extra or {})
                self.db.execute(
                    "UPDATE groups SET name=COALESCE(NULLIF(?, ''), name), member_count=COALESCE(?, member_count), "
                    "avatar_url=COALESCE(?, avatar_url), extra=?, is_demo=?, updated_at=? WHERE key=?",
                    (g.name or "", g.member_count, g.avatar_url, jdump(extra), int(is_demo), ts, key),
                )
                if whitelisted is not None:
                    self.db.execute("UPDATE groups SET whitelisted=? WHERE key=?", (int(whitelisted), key))
                created = False
        return self.get_group(key), created  # type: ignore[return-value]

    def get_group(self, key: str) -> dict[str, Any] | None:
        return _decode_group(self.db.query_one("SELECT * FROM groups WHERE key=?", (key,)))

    def list_groups(self, *, platform: str | None = None, whitelisted: bool | None = None, q: str | None = None,
                    is_demo: bool | None = None, limit: int | None = None,
                    offset: int = 0) -> tuple[list[dict[str, Any]], int]:
        where, params = ["1=1"], []
        if platform:
            where.append("platform=?")
            params.append(platform)
        if whitelisted is not None:
            where.append("whitelisted=?")
            params.append(int(whitelisted))
        if is_demo is not None:
            where.append("is_demo=?")
            params.append(int(is_demo))
        if q:
            where.append("(name LIKE ? OR alias LIKE ? OR native_id LIKE ?)")
            like = f"%{q}%"
            params += [like, like, like]
        cond = " AND ".join(where)
        total = self.db.scalar(f"SELECT COUNT(*) FROM groups WHERE {cond}", params, 0)
        sql = f"SELECT * FROM groups WHERE {cond} ORDER BY whitelisted DESC, platform, name"
        if limit is not None:
            sql += f" LIMIT {int(limit)} OFFSET {int(offset)}"
        rows = [_decode_group(r) for r in self.db.query(sql, params)]
        return rows, int(total)  # type: ignore[return-value]

    def update_group(self, key: str, **fields: Any) -> dict[str, Any] | None:
        sets, params = [], []
        for k in ("whitelisted", "weight", "alias", "tags"):
            if k in fields and fields[k] is not None:
                v = fields[k]
                if k == "whitelisted":
                    v = int(bool(v))
                elif k == "tags":
                    v = jdump([str(t) for t in v])
                elif k == "weight":
                    v = max(0.0, min(5.0, float(v)))
                sets.append(f"{k}=?")
                params.append(v)
        if sets:
            sets.append("updated_at=?")
            params += [self.now_iso(), key]
            self.db.execute(f"UPDATE groups SET {', '.join(sets)} WHERE key=?", params)
        return self.get_group(key)

    def bulk_whitelist(self, keys: list[str], whitelisted: bool) -> int:
        n = 0
        with self.db.tx():
            for part in chunked(list(keys)):
                cur = self.db.execute(f"UPDATE groups SET whitelisted=?, updated_at=? WHERE key IN ({placeholders(len(part))})",
                                      [int(whitelisted), self.now_iso(), *part])
                n += cur.rowcount
        return n

    def whitelisted_groups(self, *, platforms: list[str] | None = None, keys: list[str] | None = None,
                           is_demo: bool | None = None) -> list[dict[str, Any]]:
        rows, _ = self.list_groups(whitelisted=True, is_demo=is_demo)
        if platforms:
            rows = [r for r in rows if r["platform"] in platforms]
        if keys:
            ks = set(keys)
            rows = [r for r in rows if r["key"] in ks]
        return rows

    def group_activity(self, keys: list[str], end: datetime) -> dict[str, dict[str, int]]:
        """每个群在 end 之前 24 小时和 7 天的消息数。"""
        out: dict[str, dict[str, int]] = {k: {"m24": 0, "m7d": 0} for k in keys}
        if not keys:
            return out
        e = epoch(end)
        s24, s7 = epoch(end - timedelta(hours=24)), epoch(end - timedelta(days=7))
        for part in chunked(list(keys)):
            rows = self.db.query(
                f"SELECT group_key, SUM(CASE WHEN ts>=? THEN 1 ELSE 0 END) AS m24, COUNT(*) AS m7d FROM messages "
                f"WHERE group_key IN ({placeholders(len(part))}) AND ts>=? AND ts<? GROUP BY group_key",
                [s24, *part, s7, e])
            for r in rows:
                out[r["group_key"]] = {"m24": int(r["m24"] or 0), "m7d": int(r["m7d"] or 0)}
        return out

    def touch_group_collected(self, key: str, at_iso: str) -> None:
        self.db.execute("UPDATE groups SET last_collect_at=? WHERE key=?", (at_iso, key))

    def delete_demo_groups(self) -> int:
        with self.db.tx():
            self.db.execute("DELETE FROM messages WHERE group_key IN (SELECT key FROM groups WHERE is_demo=1)")
            return self.db.execute("DELETE FROM groups WHERE is_demo=1").rowcount
