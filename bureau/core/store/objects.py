"""定时任务与推送通道存储。"""

from __future__ import annotations

from typing import Any

from bureau.core.store.base import jdump, jload

_SCHEDULE_FIELDS = ("name", "enabled", "cron", "timezone", "window_mode", "window_hours", "platforms",
                    "group_keys", "channel_ids", "top_n", "dry_run")
_JSON_LISTS = ("platforms", "group_keys", "channel_ids")


def _decode_schedule(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    for k in _JSON_LISTS:
        row[k] = jload(row.get(k), [])
    row["enabled"] = bool(row.get("enabled"))
    row["dry_run"] = bool(row.get("dry_run"))
    return row


def _decode_channel(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row["config"] = jload(row.get("config"), {})
    row["enabled"] = bool(row.get("enabled"))
    if row.get("last_ok") is not None:
        row["last_ok"] = bool(row["last_ok"])
    return row


class ObjectMixin:
    db: Any
    now_iso: Any

    # ---------- 定时任务 ----------
    def create_schedule(self, sid: str, data: dict[str, Any]) -> dict[str, Any]:
        ts = self.now_iso()
        self.db.execute(
            "INSERT INTO schedules(id, name, enabled, cron, timezone, window_mode, window_hours, platforms, group_keys, "
            "channel_ids, top_n, dry_run, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (sid, data["name"], int(data.get("enabled", True)), data["cron"], data.get("timezone", "Asia/Shanghai"),
             data.get("window_mode", "since_last"), int(data.get("window_hours", 24)),
             jdump(data.get("platforms", [])), jdump(data.get("group_keys", [])), jdump(data.get("channel_ids", [])),
             int(data.get("top_n", 5)), int(bool(data.get("dry_run", False))), ts, ts))
        return self.get_schedule(sid)  # type: ignore[return-value]

    def update_schedule(self, sid: str, data: dict[str, Any]) -> dict[str, Any] | None:
        sets, params = [], []
        for k in _SCHEDULE_FIELDS:
            if k not in data or data[k] is None:
                continue
            v = data[k]
            if k in _JSON_LISTS:
                v = jdump(list(v))
            elif k in ("enabled", "dry_run"):
                v = int(bool(v))
            sets.append(f"{k}=?")
            params.append(v)
        if sets:
            sets.append("updated_at=?")
            params += [self.now_iso(), sid]
            self.db.execute(f"UPDATE schedules SET {', '.join(sets)} WHERE id=?", params)
        return self.get_schedule(sid)

    def get_schedule(self, sid: str) -> dict[str, Any] | None:
        return _decode_schedule(self.db.query_one("SELECT * FROM schedules WHERE id=?", (sid,)))

    def list_schedules(self) -> list[dict[str, Any]]:
        return [_decode_schedule(r) for r in self.db.query("SELECT * FROM schedules ORDER BY created_at")]  # type: ignore[misc]

    def delete_schedule(self, sid: str) -> bool:
        return self.db.execute("DELETE FROM schedules WHERE id=?", (sid,)).rowcount > 0

    def mark_schedule_fired(self, sid: str, at_iso: str) -> None:
        self.db.execute("UPDATE schedules SET last_fire_at=? WHERE id=?", (at_iso, sid))

    # ---------- 推送通道 ----------
    def create_channel(self, cid: str, kind: str, name: str, enabled: bool, config: dict[str, Any]) -> dict[str, Any]:
        ts = self.now_iso()
        self.db.execute("INSERT INTO channels(id, kind, name, enabled, config, created_at, updated_at) "
                        "VALUES(?,?,?,?,?,?,?)", (cid, kind, name, int(enabled), jdump(config), ts, ts))
        return self.get_channel(cid)  # type: ignore[return-value]

    def update_channel(self, cid: str, *, name: str | None = None, enabled: bool | None = None,
                       config: dict[str, Any] | None = None) -> dict[str, Any] | None:
        sets, params = [], []
        if name is not None:
            sets.append("name=?")
            params.append(name)
        if enabled is not None:
            sets.append("enabled=?")
            params.append(int(enabled))
        if config is not None:
            sets.append("config=?")
            params.append(jdump(config))
        if sets:
            sets.append("updated_at=?")
            params += [self.now_iso(), cid]
            self.db.execute(f"UPDATE channels SET {', '.join(sets)} WHERE id=?", params)
        return self.get_channel(cid)

    def get_channel(self, cid: str) -> dict[str, Any] | None:
        return _decode_channel(self.db.query_one("SELECT * FROM channels WHERE id=?", (cid,)))

    def list_channels(self) -> list[dict[str, Any]]:
        return [_decode_channel(r) for r in self.db.query("SELECT * FROM channels ORDER BY created_at")]  # type: ignore[misc]

    def delete_channel(self, cid: str) -> bool:
        return self.db.execute("DELETE FROM channels WHERE id=?", (cid,)).rowcount > 0

    def set_channel_result(self, cid: str, ok: bool, detail: str) -> None:
        self.db.execute("UPDATE channels SET last_ok=?, last_detail=?, last_at=? WHERE id=?",
                        (int(ok), detail[:500], self.now_iso(), cid))
