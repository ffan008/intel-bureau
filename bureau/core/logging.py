"""日志：滚动文件 + 内存环形缓冲（供 /api/logs）+ 密钥脱敏。

运行日志（``RunLogger``）同时写 ``run_logs`` 表、发 ``run.log`` 事件、写普通日志。
日志里不得出现密钥、令牌或完整消息正文。
"""

from __future__ import annotations

import collections
import logging
import logging.handlers
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable
from zoneinfo import ZoneInfo

from bureau.core.security import redact_text

LEVEL_NAMES = {logging.DEBUG: "debug", logging.INFO: "info", logging.WARNING: "warn",
               logging.ERROR: "error", logging.CRITICAL: "error"}
LEVEL_VALUES = {"debug": logging.DEBUG, "info": logging.INFO, "warn": logging.WARNING,
                "warning": logging.WARNING, "error": logging.ERROR}

_RING: collections.deque[dict[str, Any]] = collections.deque(maxlen=2000)
_RING_LOCK = threading.Lock()
_SECRET_PROVIDER: list[Callable[[], Iterable[str]]] = []
_TZ = [ZoneInfo("Asia/Shanghai")]
_FILE_HANDLER: list[logging.Handler] = []


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:                                  # noqa: BLE001
            return True
        secrets: list[str] = []
        for provider in _SECRET_PROVIDER:
            try:
                secrets.extend(provider())
            except Exception:                              # noqa: BLE001
                pass
        clean = redact_text(msg, secrets)
        if clean != msg:
            record.msg, record.args = clean, None
        return True


class RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = {
                "ts": datetime.fromtimestamp(record.created, _TZ[0]).isoformat(timespec="seconds"),
                "level": LEVEL_NAMES.get(record.levelno, "info"),
                "source": record.name.removeprefix("bureau.") or "bureau",
                "message": record.getMessage(),
            }
            run_id = getattr(record, "run_id", None)
            stage = getattr(record, "stage", None)
            if run_id:
                entry["run_id"] = run_id
            if stage:
                entry["stage"] = stage
            with _RING_LOCK:
                _RING.append(entry)
        except Exception:                                  # noqa: BLE001
            self.handleError(record)


def setup_logging(log_dir: Path, *, level: str = "info", tz: str = "Asia/Shanghai",
                  secret_provider: Callable[[], Iterable[str]] | None = None,
                  console: bool = False) -> None:
    """幂等：重复调用只更新脱敏来源。"""
    _TZ[0] = ZoneInfo(tz)
    if secret_provider is not None:
        _SECRET_PROVIDER.clear()
        _SECRET_PROVIDER.append(secret_provider)
    root = logging.getLogger()
    if any(isinstance(h, RingHandler) for h in root.handlers):
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%Y-%m-%d %H:%M:%S")
    redact = RedactFilter()
    fh = logging.handlers.RotatingFileHandler(log_dir / "bureau.log", maxBytes=5 * 1024 * 1024,
                                              backupCount=5, encoding="utf-8", delay=True)
    fh.setFormatter(fmt)
    fh.addFilter(redact)
    ring = RingHandler()
    ring.addFilter(redact)
    root.addHandler(fh)
    root.addHandler(ring)
    _FILE_HANDLER.append(fh)
    if console:
        ch = logging.StreamHandler()
        ch.setFormatter(fmt)
        ch.addFilter(redact)
        ch.setLevel(logging.WARNING)
        root.addHandler(ch)
    root.setLevel(LEVEL_VALUES.get(level, logging.INFO))
    # 第三方库日志降噪；httpx 的 INFO 会带完整 URL（可能含密钥），一律压到 WARNING
    for name in ("httpx", "httpcore", "jieba", "asyncio", "watchfiles", "apscheduler", "uvicorn.access"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("apscheduler.scheduler").setLevel(logging.WARNING)


def shutdown_logging() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        if isinstance(h, (RingHandler, logging.handlers.RotatingFileHandler)):
            root.removeHandler(h)
            h.close()
    _FILE_HANDLER.clear()


def recent_logs(level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    min_level = LEVEL_VALUES.get(level or "debug", logging.DEBUG)
    with _RING_LOCK:
        items = list(_RING)
    out = [e for e in items if LEVEL_VALUES.get(e["level"], logging.INFO) >= min_level]
    return out[-max(1, min(limit, 2000)):]


def preview(text: str, n: int = 40) -> str:
    """调试日志里最多保留正文前 40 字。"""
    text = (text or "").replace("\n", " ")
    return text if len(text) <= n else text[:n] + "…"


class RunLogger:
    """一次运行的日志：写库、发 run.log 事件、写普通日志。"""

    def __init__(self, run_id: str, store: Any, bus: Any, tz: str = "Asia/Shanghai") -> None:
        self.run_id = run_id
        self.store = store
        self.bus = bus
        self.tz = ZoneInfo(tz)
        self._log = logging.getLogger("bureau.run")

    def log(self, level: str, source: str, message: str, stage: str | None = None) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "ts": datetime.now(self.tz).isoformat(timespec="seconds"),
            "level": level if level in ("debug", "info", "warn", "error") else "info",
            "source": source,
            "message": message,
            "run_id": self.run_id,
        }
        if stage:
            entry["stage"] = stage
        try:
            self.store.add_run_log(self.run_id, entry["ts"], entry["level"], source, stage, message)
        except Exception as exc:                           # noqa: BLE001
            self._log.warning("写运行日志失败：%s", exc)
        if self.bus is not None:
            self.bus.publish("run.log", entry)
        self._log.log(LEVEL_VALUES.get(entry["level"], logging.INFO), "[%s] %s %s", self.run_id, source, message,
                      extra={"run_id": self.run_id, "stage": stage})
        return entry

    def info(self, source: str, message: str, stage: str | None = None) -> None:
        self.log("info", source, message, stage)

    def warn(self, source: str, message: str, stage: str | None = None) -> None:
        self.log("warn", source, message, stage)

    def error(self, source: str, message: str, stage: str | None = None) -> None:
        self.log("error", source, message, stage)
