"""存储层公共部分：JSON 编解码、kv。"""

from __future__ import annotations

import json
from typing import Any, Iterable, Sequence

from bureau.core.db import Database
from bureau.core.timeutil import iso, now


def jdump(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=str)


def jload(text: str | None, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return default


def chunked(seq: Sequence[Any], n: int = 400) -> Iterable[Sequence[Any]]:
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def placeholders(n: int) -> str:
    return ",".join("?" * n)


class StoreBase:
    def __init__(self, db: Database, tz: str = "Asia/Shanghai") -> None:
        self.db = db
        self.tz = tz

    def now_iso(self) -> str:
        return iso(now(self.tz)) or ""

    # ---------- kv ----------
    def kv_get(self, key: str, default: Any = None) -> Any:
        row = self.db.query_one("SELECT value FROM kv WHERE key=?", (key,))
        return jload(row["value"], default) if row else default

    def kv_set(self, key: str, value: Any) -> None:
        self.db.execute(
            "INSERT INTO kv(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, jdump(value), self.now_iso()),
        )

    def kv_delete(self, key: str) -> None:
        self.db.execute("DELETE FROM kv WHERE key=?", (key,))
