"""SQLite 访问层：WAL、迁移、FTS5、线程安全。

所有访问共用一个连接，用 RLock 串行化（``check_same_thread=False``）。
写事务用 ``with db.tx():``，可嵌套。
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator

from bureau.core.schema import FTS_TEMPLATE, KB_FTS_TEMPLATE, LATEST_VERSION, MIGRATIONS

log = logging.getLogger("bureau.db")


class Database:
    def __init__(self, path: Path | str, *, backup_dir: Path | None = None) -> None:
        self.path = str(path)
        self.backup_dir = backup_dir
        self._lock = threading.RLock()
        self._depth = 0
        self.fts_enabled = False
        self.fts_tokenizer = ""
        self.kb_fts_enabled = False
        self.kb_fts_tokenizer = ""
        self.conn = sqlite3.connect(self.path, check_same_thread=False, isolation_level=None, timeout=10)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=10000")
        self.migrate()

    # ---------- 迁移 ----------
    @property
    def user_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> None:
        with self._lock:
            current = self.user_version
            if 0 < current < LATEST_VERSION:
                self._backup(current)
            for idx in range(current, LATEST_VERSION):
                self.conn.execute("BEGIN IMMEDIATE")
                try:
                    for stmt in _split_sql(MIGRATIONS[idx]):
                        self.conn.execute(stmt)
                    self.conn.execute(f"PRAGMA user_version={idx + 1}")
                    self.conn.execute("COMMIT")
                except Exception:
                    self.conn.execute("ROLLBACK")
                    raise
                log.info("数据库迁移到版本 %s", idx + 1)
            self._ensure_fts()
            if self.user_version >= 2:
                self.kb_fts_enabled, self.kb_fts_tokenizer = self._ensure_fts_table("kb_fts", KB_FTS_TEMPLATE)

    def _backup(self, version: int) -> None:
        if self.path == ":memory:" or not self.backup_dir:
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"bureau-v{version}-{stamp}.db"
        try:
            self.conn.execute("PRAGMA wal_checkpoint(FULL)")
            shutil.copyfile(self.path, target)
            log.info("迁移前已备份数据库到 %s", target)
        except OSError as exc:
            log.warning("数据库备份失败：%s", exc)

    def _ensure_fts(self) -> None:
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE name='messages_fts'").fetchone()
        if row:
            self.fts_enabled = True
            self.fts_tokenizer = "trigram" if "trigram" in (row[0] or "") else "unicode61"
            return
        for tokenizer in ("trigram", "unicode61"):
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                for stmt in _split_sql(FTS_TEMPLATE.format(tokenizer=tokenizer), triggers=True):
                    self.conn.execute(stmt)
                self.conn.execute("INSERT INTO messages_fts(messages_fts) VALUES ('rebuild')")
                self.conn.execute("COMMIT")
                self.fts_enabled = True
                self.fts_tokenizer = tokenizer
                return
            except sqlite3.OperationalError as exc:
                self.conn.execute("ROLLBACK")
                log.warning("FTS5（%s）不可用：%s", tokenizer, exc)

    def _ensure_fts_table(self, name: str, template: str) -> tuple[bool, str]:
        """建立外部内容的 FTS5 表（优先 trigram），返回 (是否可用, 分词器)。失败时搜索退回 LIKE。"""
        row = self.conn.execute("SELECT sql FROM sqlite_master WHERE name=?", (name,)).fetchone()
        if row:
            return True, "trigram" if "trigram" in (row[0] or "") else "unicode61"
        for tokenizer in ("trigram", "unicode61"):
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                for stmt in _split_sql(template.format(tokenizer=tokenizer), triggers=True):
                    self.conn.execute(stmt)
                self.conn.execute(f"INSERT INTO {name}({name}) VALUES ('rebuild')")
                self.conn.execute("COMMIT")
                return True, tokenizer
            except sqlite3.OperationalError as exc:
                self.conn.execute("ROLLBACK")
                log.warning("%s（%s）不可用：%s", name, tokenizer, exc)
        return False, ""

    # ---------- 访问 ----------
    @contextmanager
    def tx(self) -> Iterator["Database"]:
        with self._lock:
            outer = self._depth == 0
            if outer:
                self.conn.execute("BEGIN IMMEDIATE")
            self._depth += 1
            try:
                yield self
            except BaseException:
                self._depth -= 1
                if outer:
                    self.conn.execute("ROLLBACK")
                raise
            else:
                self._depth -= 1
                if outer:
                    self.conn.execute("COMMIT")

    def execute(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Iterable[Any]]) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.executemany(sql, rows)

    def query(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def query_one(self, sql: str, params: Iterable[Any] | dict[str, Any] = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self.conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    def scalar(self, sql: str, params: Iterable[Any] | dict[str, Any] = (), default: Any = None) -> Any:
        with self._lock:
            row = self.conn.execute(sql, params).fetchone()
            return row[0] if row and row[0] is not None else default

    def tables(self) -> list[str]:
        return [r["name"] for r in self.query("SELECT name FROM sqlite_master WHERE type IN ('table') ORDER BY name")]

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.close()
            except sqlite3.Error:
                pass


def _split_sql(script: str, *, triggers: bool = False) -> list[str]:
    """按分号切分 SQL 脚本；触发器体内的分号要保留（以 END; 结尾）。"""
    out: list[str] = []
    buf: list[str] = []
    in_trigger = False
    for line in script.splitlines():
        s = line.strip()
        if not s:
            continue
        buf.append(line)
        if s.upper().startswith("CREATE TRIGGER"):
            in_trigger = True
        if in_trigger:
            if s.upper() == "END;":
                out.append("\n".join(buf))
                buf, in_trigger = [], False
            continue
        if s.endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return [x.strip().rstrip(";") if not x.strip().upper().endswith("END;") else x.strip() for x in out]
