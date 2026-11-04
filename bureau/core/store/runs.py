"""运行、阶段与运行日志存储。"""

from __future__ import annotations

from typing import Any

from bureau.core.constants import STAGES
from bureau.core.store.base import jdump, jload


def _decode_run(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    row["params"] = jload(row.get("params"), {})
    row["totals"] = jload(row.get("totals"), {})
    row["dry_run"] = bool(row.get("dry_run"))
    row["is_demo"] = bool(row.get("is_demo"))
    return row


class RunMixin:
    db: Any
    now_iso: Any

    def create_run(self, run_id: str, *, trigger: str, schedule_id: str | None, dry_run: bool, is_demo: bool,
                   window_start: str, window_end: str, params: dict[str, Any]) -> None:
        ts = self.now_iso()
        with self.db.tx():
            self.db.execute(
                "INSERT INTO runs(id, schedule_id, trigger, status, dry_run, is_demo, window_start, window_end, params, "
                "totals, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, schedule_id, trigger, "queued", int(dry_run), int(is_demo), window_start, window_end,
                 jdump(params), "{}", ts))
            self.db.executemany(
                "INSERT INTO run_stages(run_id, name, seq, status, metrics) VALUES(?,?,?,?,?)",
                [(run_id, name, i, "pending", "{}") for i, name in enumerate(STAGES)])

    def update_run(self, run_id: str, **fields: Any) -> None:
        sets, params = [], []
        for k, v in fields.items():
            if k in ("totals", "params"):
                v = jdump(v)
            elif k == "dry_run":
                v = int(v)
            sets.append(f"{k}=?")
            params.append(v)
        if sets:
            self.db.execute(f"UPDATE runs SET {', '.join(sets)} WHERE id=?", [*params, run_id])

    def update_stage(self, run_id: str, name: str, **fields: Any) -> None:
        sets, params = [], []
        for k, v in fields.items():
            if k == "metrics":
                v = jdump(v)
            sets.append(f"{k}=?")
            params.append(v)
        if sets:
            self.db.execute(f"UPDATE run_stages SET {', '.join(sets)} WHERE run_id=? AND name=?", [*params, run_id, name])

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run = _decode_run(self.db.query_one("SELECT * FROM runs WHERE id=?", (run_id,)))
        if run is None:
            return None
        run["stages"] = self.get_stages(run_id)
        return run

    def get_stages(self, run_id: str) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM run_stages WHERE run_id=? ORDER BY seq", (run_id,))
        for r in rows:
            r["metrics"] = jload(r.get("metrics"), {})
        return rows

    def list_runs(self, limit: int = 20, offset: int = 0, *, schedule_id: str | None = None) -> tuple[list[dict[str, Any]], int]:
        where, params = "", []
        if schedule_id:
            where, params = "WHERE schedule_id=?", [schedule_id]
        total = int(self.db.scalar(f"SELECT COUNT(*) FROM runs {where}", params, 0))
        rows = self.db.query(f"SELECT * FROM runs {where} ORDER BY created_at DESC, rowid DESC LIMIT ? OFFSET ?",
                             [*params, int(limit), int(offset)])
        runs = []
        for r in rows:
            run = _decode_run(r)
            assert run is not None
            run["stages"] = self.get_stages(run["id"])
            runs.append(run)
        return runs, total

    def last_finished_run(self, *, is_demo: bool | None = None) -> dict[str, Any] | None:
        sql, params = "SELECT id FROM runs WHERE status IN ('success','partial','failed','cancelled')", []
        if is_demo is not None:
            sql += " AND is_demo=?"
            params.append(int(is_demo))
        row = self.db.query_one(sql + " ORDER BY finished_at DESC, rowid DESC LIMIT 1", params)
        return self.get_run(row["id"]) if row else None

    def last_success_window_end(self, *, schedule_id: str | None = None) -> str | None:
        """上次成功（含部分成功）的真实运行窗口终点；dry_run 与演示运行不算。"""
        sql = ("SELECT window_end FROM runs WHERE status IN ('success','partial') AND dry_run=0 AND is_demo=0")
        params: list[Any] = []
        if schedule_id:
            sql += " AND schedule_id=?"
            params.append(schedule_id)
        row = self.db.query_one(sql + " ORDER BY window_end DESC LIMIT 1", params)
        return row["window_end"] if row else None

    def last_run_for_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        return self.db.query_one("SELECT id, status, finished_at FROM runs WHERE schedule_id=? "
                                 "ORDER BY created_at DESC, rowid DESC LIMIT 1", (schedule_id,))

    def mark_stale_runs(self) -> int:
        """服务重启时把残留的 queued/running 运行标为失败。"""
        ts = self.now_iso()
        with self.db.tx():
            ids = [r["id"] for r in self.db.query("SELECT id FROM runs WHERE status IN ('queued','running')")]
            for rid in ids:
                self.db.execute("UPDATE runs SET status='failed', error=?, finished_at=? WHERE id=?",
                                ("服务重启，运行被中断", ts, rid))
                self.db.execute("UPDATE run_stages SET status='failed', message='服务重启，运行被中断' "
                                "WHERE run_id=? AND status='running'", (rid,))
        return len(ids)

    def add_run_log(self, run_id: str, ts: str, level: str, source: str, stage: str | None, message: str) -> None:
        self.db.execute("INSERT INTO run_logs(run_id, ts, level, source, stage, message) VALUES(?,?,?,?,?,?)",
                        (run_id, ts, level, source, stage, message))

    def run_logs(self, run_id: str, limit: int = 1000) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT ts, level, source, stage, message, run_id FROM run_logs WHERE run_id=? "
                             "ORDER BY id LIMIT ?", (run_id, int(limit)))
        for r in rows:
            if not r.get("stage"):
                r.pop("stage", None)
        return rows

    def llm_usage_since(self, since_iso: str) -> dict[str, float]:
        rows = self.db.query("SELECT totals FROM runs WHERE created_at>=?", (since_iso,))
        tin = tout = cost = 0.0
        for r in rows:
            t = jload(r["totals"], {}) or {}
            tin += float(t.get("tokens_in") or 0)
            tout += float(t.get("tokens_out") or 0)
            cost += float(t.get("cost_cny") or 0)
        return {"tokens": tin + tout, "tokens_in": tin, "tokens_out": tout, "cost_cny": round(cost, 4)}

    def delete_demo_runs(self) -> int:
        return self.db.execute("DELETE FROM runs WHERE is_demo=1").rowcount
