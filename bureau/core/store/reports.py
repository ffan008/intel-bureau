"""报告、情报条目与投递记录存储。"""

from __future__ import annotations

from typing import Any

from bureau.core.store.base import jdump, jload

_SUMMARY_COLS = ("id, run_id, title, date_label, window_label, window_start, window_end, is_demo, dry_run, "
                 "items_total, headlines, files, created_at")


def _decode_report(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    for k, d in (("headlines", []), ("judgments", []), ("stats", {}), ("files", {}), ("v2_data", {})):
        if k in row:
            row[k] = jload(row.get(k), d)
    row["is_demo"] = bool(row.get("is_demo"))
    row["dry_run"] = bool(row.get("dry_run"))
    return row


class ReportMixin:
    db: Any
    now_iso: Any

    def save_report(self, report: dict[str, Any], items: list[dict[str, Any]]) -> None:
        """保存报告及条目（同 id 覆盖）。report 需含 id/run_id/title/... 字段；items 是 IntelItemDTO 字典。"""
        ts = report.get("created_at") or self.now_iso()
        with self.db.tx():
            self.db.execute("DELETE FROM intel_items WHERE report_id=?", (report["id"],))
            self.db.execute("DELETE FROM reports WHERE id=?", (report["id"],))
            self.db.execute(
                "INSERT INTO reports(id, run_id, title, date_label, window_label, window_start, window_end, is_demo, "
                "dry_run, items_total, headlines, judgments, stats, full_md, summary_md, summary_text, files, created_at) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (report["id"], report["run_id"], report["title"], report["date_label"], report["window_label"],
                 report["window_start"], report["window_end"], int(bool(report.get("is_demo"))),
                 int(bool(report.get("dry_run"))), len(items), jdump(report.get("headlines", [])),
                 jdump(report.get("judgments", [])), jdump(report.get("stats", {})), report.get("full_md", ""),
                 report.get("summary_md", ""), report.get("summary_text", ""), jdump(report.get("files", {})), ts))
            self.db.executemany(
                "INSERT INTO intel_items(id, report_id, rank, title, category, kind, score, trend, is_headline, "
                "is_feature, data, created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                [(it["id"], report["id"], it["rank"], it["title"], it["category"], it["kind"], it["score"], it["trend"],
                  int(it["is_headline"]), int(it["is_feature"]), jdump(it), ts) for it in items])
            if report.get("v2_data"):           # v2：板块、专题、资源、媒体、分群摘要（见 core/dto.report_dto）
                self.db.execute("UPDATE reports SET v2_data=? WHERE id=?", (jdump(report["v2_data"]), report["id"]))

    def update_report_v2(self, report_id: str, patch: dict[str, Any]) -> None:
        """合并更新 v2_data 的顶层键（如投递后补上的 doc_links）。"""
        with self.db.tx():
            row = self.db.query_one("SELECT v2_data FROM reports WHERE id=?", (report_id,))
            if row is None:
                return
            data = jload(row["v2_data"], {}) or {}
            data.update(patch)
            self.db.execute("UPDATE reports SET v2_data=? WHERE id=?", (jdump(data), report_id))

    def update_report_summary(self, report_id: str, summary_md: str, summary_text: str) -> None:
        self.db.execute("UPDATE reports SET summary_md=?, summary_text=? WHERE id=?", (summary_md, summary_text, report_id))

    def get_report(self, report_id: str) -> dict[str, Any] | None:
        return _decode_report(self.db.query_one("SELECT * FROM reports WHERE id=?", (report_id,)))

    def list_reports(self, limit: int = 20, offset: int = 0, q: str | None = None,
                     is_demo: bool | None = None) -> tuple[list[dict[str, Any]], int]:
        where, params = ["1=1"], []
        if q:
            where.append("(title LIKE ? OR full_md LIKE ?)")
            params += [f"%{q}%", f"%{q}%"]
        if is_demo is not None:
            where.append("is_demo=?")
            params.append(int(is_demo))
        cond = " AND ".join(where)
        total = int(self.db.scalar(f"SELECT COUNT(*) FROM reports WHERE {cond}", params, 0))
        rows = self.db.query(f"SELECT {_SUMMARY_COLS} FROM reports WHERE {cond} ORDER BY created_at DESC, rowid DESC "
                             "LIMIT ? OFFSET ?", [*params, int(limit), int(offset)])
        return [_decode_report(r) for r in rows], total  # type: ignore[misc]

    def latest_report(self, *, is_demo: bool | None = None, offset: int = 0) -> dict[str, Any] | None:
        rows, _ = self.list_reports(limit=1, offset=offset, is_demo=is_demo)
        return rows[0] if rows else None

    def report_items(self, report_id: str) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT data FROM intel_items WHERE report_id=? ORDER BY rank", (report_id,))
        return [jload(r["data"], {}) for r in rows]

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT data FROM intel_items WHERE id=?", (item_id,))
        return jload(row["data"], {}) if row else None

    def update_report_files(self, report_id: str, files: dict[str, str]) -> None:
        self.db.execute("UPDATE reports SET files=? WHERE id=?", (jdump(files), report_id))

    # ---------- 投递 ----------
    def add_delivery(self, *, report_id: str, run_id: str | None, channel_id: str, channel_name: str, kind: str,
                     ok: bool, detail: str, external_id: str | None = None, parts: int = 1) -> None:
        self.db.execute(
            "INSERT INTO deliveries(report_id, run_id, channel_id, channel_name, kind, ok, detail, external_id, parts, "
            "created_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (report_id, run_id, channel_id, channel_name, kind, int(ok), detail, external_id, parts, self.now_iso()))

    def deliveries_for(self, report_id: str) -> list[dict[str, Any]]:
        """每个通道最近一次的投递结果。"""
        rows = self.db.query("SELECT * FROM deliveries WHERE report_id=? ORDER BY id", (report_id,))
        latest: dict[str, dict[str, Any]] = {}
        for r in rows:
            r["ok"] = bool(r["ok"])
            latest[r["channel_id"]] = r
        return list(latest.values())

    def recent_deliveries(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM deliveries ORDER BY id DESC LIMIT ?", (int(limit),))
        for r in rows:
            r["ok"] = bool(r["ok"])
        return rows

    def delete_demo_reports(self) -> int:
        with self.db.tx():
            ids = [r["id"] for r in self.db.query("SELECT id FROM reports WHERE is_demo=1")]
            for rid in ids:
                self.db.execute("DELETE FROM deliveries WHERE report_id=?", (rid,))
                self.db.execute("DELETE FROM intel_items WHERE report_id=?", (rid,))
                self.db.execute("DELETE FROM reports WHERE id=?", (rid,))
        return len(ids)
