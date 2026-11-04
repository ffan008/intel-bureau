"""采集器接口。由 Lead 维护。

采集器只做一件事：从平台只读地取出群列表和消息，转换成 ``RawMessage``。
它不碰数据库、不做白名单判断（调用方只会传入白名单群）。
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, ClassVar

from bureau.contracts import ConfigField, FetchResult, GroupInfo, HealthStatus, Platform


@dataclass
class CollectorContext:
    platform: Platform
    settings: dict[str, Any]                       # settings.yaml 中 sources.<platform>.<adapter> 的非密钥配置
    secrets: dict[str, Any]                        # secrets.yaml 中 sources.<platform>.<adapter> 的密钥
    data_dir: Path                                 # <项目目录>\data
    tz: str = "Asia/Shanghai"
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("bureau.collector"))


class Collector(ABC):
    key: ClassVar[str]                             # 注册表键，如 "qq.onebot"
    label: ClassVar[str]                           # 中文名，如 "NapCatQQ（OneBot 11）"
    platforms: ClassVar[tuple[Platform, ...]]      # 支持的平台
    supports_realtime: ClassVar[bool] = False

    def __init__(self, ctx: CollectorContext) -> None:
        self.ctx = ctx

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        """前端表单字段。type="secret" 的字段会存进 secrets.yaml。"""
        return []

    @abstractmethod
    async def health(self) -> HealthStatus:
        """快速检查（≤5 秒）。不可用时给出中文 detail 和 hint。"""

    @abstractmethod
    async def list_groups(self) -> list[GroupInfo]:
        """列出账号所在的全部群（不分白名单）。"""

    @abstractmethod
    async def fetch_messages(
        self,
        group: GroupInfo,
        since: datetime,
        until: datetime,
        *,
        cursor: str | None = None,
        limit: int = 5000,
    ) -> FetchResult:
        """拉取 [since, until) 内的消息，按时间升序返回。

        达到 limit 时返回已拿到的部分并设置 complete=False。
        出错时抛出异常，异常信息要是可读的中文。
        """

    async def aclose(self) -> None:
        """释放 HTTP 客户端等资源。"""
        return None
