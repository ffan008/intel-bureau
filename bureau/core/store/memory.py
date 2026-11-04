"""话题记忆与每日关键词存储。scope 区分 live / demo，互不污染。"""

from __future__ import annotations

from typing import Any

from bureau.core.store.base import jdump, jload


def _decode_mem(row: dict[str, Any]) -> dict[str, Any]:
    row["keywords"] = jload(row.get("keywords"), [])
    row["links"] = jload(row.get("links"), [])
    row["history"] = jload(row.get("history"), [])
    return row


class MemoryMixin:
    db: Any
    now_iso: Any

    def memory_recent(self, scope: str, since_day: str) -> list[dict[str, Any]]:
        rows = self.db.query("SELECT * FROM topic_memory WHERE scope=? AND last_seen>=? ORDER BY last_seen DESC",
                             (scope, since_day))
        return [_decode_mem(r) for r in rows]

    def memory_get(self, mem_id: int) -> dict[str, Any] | None:
        row = self.db.query_one("SELECT * FROM topic_memory WHERE id=?", (mem_id,))
        return _decode_mem(row) if row else None

    def memory_insert(self, scope: str, *, title: str, category: str, keywords: list[str], links: list[str],
                      day: str, item_id: str | None, heat: float, history: list[dict[str, Any]] | None = None,
                      first_seen: str | None = None) -> int:
        hist = history if history is not None else [{"day": day, "title": title, "item_id": item_id}]
        cur = self.db.execute(
            "INSERT INTO topic_memory(scope, title, category, keywords, links, first_seen, last_seen, seen_count, "
            "history, last_item_id, heat) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (scope, title, category, jdump(keywords[:40]), jdump(links[:20]), first_seen or day, day,
             len({h["day"] for h in hist}), jdump(hist[-30:]), item_id, float(heat)))
        return int(cur.lastrowid)

    def memory_touch(self, mem_id: int, *, title: str, keywords: list[str], links: list[str], day: str,
                     item_id: str | None, heat: float) -> None:
        """同一话题再次出现：并入关键词与链接，记录当天（同一天重跑只覆盖不累加）。"""
        mem = self.memory_get(mem_id)
        if mem is None:
            return
        kws = list(dict.fromkeys([*mem["keywords"], *keywords]))[-40:]
        links_all = list(dict.fromkeys([*mem["links"], *links]))[-20:]
        hist = [h for h in mem["history"] if h.get("day") != day]
        hist.append({"day": day, "title": title, "item_id": item_id})
        hist.sort(key=lambda h: h.get("day", ""))
        days = {h["day"] for h in hist}
        self.db.execute(
            "UPDATE topic_memory SET keywords=?, links=?, last_seen=?, seen_count=?, history=?, last_item_id=?, heat=? "
            "WHERE id=?",
            (jdump(kws), jdump(links_all), max(mem["last_seen"], day), len(days), jdump(hist[-30:]), item_id,
             float(heat), mem_id))

    def clear_memory(self, scope: str) -> None:
        with self.db.tx():
            self.db.execute("DELETE FROM topic_memory WHERE scope=?", (scope,))
            self.db.execute("DELETE FROM keyword_daily WHERE scope=?", (scope,))

    # ---------- 每日关键词 ----------
    def keyword_daily_upsert(self, scope: str, day: str, counts: dict[str, int],
                             groups: dict[str, list[str]] | None = None) -> None:
        groups = groups or {}
        with self.db.tx():
            self.db.execute("DELETE FROM keyword_daily WHERE scope=? AND day=?", (scope, day))
            self.db.executemany(
                "INSERT INTO keyword_daily(scope, day, word, count, groups) VALUES(?,?,?,?,?)",
                [(scope, day, w, int(c), jdump(groups.get(w, [])[:5])) for w, c in counts.items()])

    def keyword_daily_days(self, scope: str, days: list[str]) -> dict[str, dict[str, int]]:
        """返回 {day: {word: count}}，只包含有记录的日子。"""
        out: dict[str, dict[str, int]] = {}
        if not days:
            return out
        q = ",".join("?" * len(days))
        for r in self.db.query(f"SELECT day, word, count FROM keyword_daily WHERE scope=? AND day IN ({q})",
                               [scope, *days]):
            out.setdefault(r["day"], {})[r["word"]] = int(r["count"])
        return out
