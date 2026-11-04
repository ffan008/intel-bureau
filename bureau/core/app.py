"""应用上下文：把配置、数据库、事件总线、流水线和调度器组装在一起。API 与命令行共用。"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from bureau import __version__
from bureau.core.bus import EventBus
from bureau.core.config import ConfigManager
from bureau.core.db import Database
from bureau.core.logging import setup_logging
from bureau.core.nlp import NLP_INSTANCE
from bureau.core.paths import Paths, resolve_paths
from bureau.core.store import Store
from bureau.core.timeutil import now, parse_iso

log = logging.getLogger("bureau.app")

LOCAL_ARCHIVE_ID = "ch_local_archive"
MORNING_SCHEDULE_ID = "sch_morning"


class AppContext:
    version = __version__

    def __init__(self, paths: Paths | None = None, *, port: int | None = None, console_log: bool = False) -> None:
        self.paths = (paths or resolve_paths()).ensure()
        self.config = ConfigManager(self.paths)
        self.tz: str = self.config.get("app.timezone", "Asia/Shanghai") or "Asia/Shanghai"
        setup_logging(self.paths.logs, tz=self.tz, secret_provider=self.config.secret_values, console=console_log)
        NLP_INSTANCE.configure(self.paths.userdict, self.paths.stopwords, self.paths.jieba_cache)
        self.db = Database(self.paths.db, backup_dir=self.paths.backups)
        self.store = Store(self.db, self.tz)
        self.bus = EventBus(tz=self.tz)
        self.port = int(port or self.config.get("app.port", 8765))
        self.health_cache: dict[str, dict[str, Any]] = {}
        self.scheduler: Any = None
        self._runner: Any = None
        self.overview_cache: dict[str, Any] = {}
        bootstrap_defaults(self)

    @property
    def runner(self) -> Any:
        if self._runner is None:
            from bureau.pipeline.runner import PipelineRunner
            self._runner = PipelineRunner(self)
        return self._runner

    def now(self) -> datetime:
        return now(self.tz)

    def mode(self) -> str:
        """有演示群、且没有真实白名单群时为 demo。"""
        demo_n = int(self.db.scalar("SELECT COUNT(*) FROM groups WHERE is_demo=1", (), 0))
        live_n = int(self.db.scalar("SELECT COUNT(*) FROM groups WHERE is_demo=0 AND whitelisted=1", (), 0))
        return "demo" if demo_n and not live_n else "live"

    def demo_anchor(self) -> datetime | None:
        return parse_iso(self.store.kv_get("demo.anchor"), self.tz)

    def dashboard_url(self) -> str:
        return str(self.config.get("app.dashboard_url") or f"http://127.0.0.1:{self.port}").rstrip("/")

    def close(self) -> None:
        self.db.close()


def bootstrap_defaults(app: AppContext) -> None:
    """新库首次启动：创建「本地归档」通道和默认定时任务「晨报」（每天 08:00）。只做一次。"""
    if app.store.kv_get("bootstrap.v1"):
        return
    channels = app.store.list_channels()
    archive = next((c for c in channels if c["kind"] == "local_archive"), None)
    if archive is None:
        archive = app.store.create_channel(LOCAL_ARCHIVE_ID, "local_archive", "本地归档", True, {})
    if not app.store.list_schedules():
        app.store.create_schedule(MORNING_SCHEDULE_ID, {
            "name": "晨报", "enabled": True, "cron": "0 8 * * *", "timezone": app.tz,
            "window_mode": "since_last", "window_hours": 24, "platforms": ["wechat", "qq", "feishu"],
            "group_keys": [], "channel_ids": [archive["id"]], "top_n": 5, "dry_run": False,
        })
    app.store.kv_set("bootstrap.v1", app.store.now_iso())
    log.info("已创建默认通道「本地归档」和定时任务「晨报」")
