"""推送通道接口。由 Lead 维护。"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from bureau.contracts import ConfigField, DeliveryResult, ReportPayload


@dataclass
class ChannelContext:
    channel_id: str
    name: str
    settings: dict[str, Any]        # 非密钥配置（存在数据库 channels.config）
    secrets: dict[str, Any]         # 密钥配置（存在 secrets.yaml 的 channels.<channel_id>）
    data_dir: Path
    tz: str = "Asia/Shanghai"
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("bureau.channel"))


class Channel(ABC):
    kind: ClassVar[str]             # 如 "feishu_webhook"
    label: ClassVar[str]            # 如 "飞书群机器人（Webhook）"
    platform_label: ClassVar[str]   # 如 "飞书"、"微信"、"QQ"、"邮箱"、"本地"

    def __init__(self, ctx: ChannelContext) -> None:
        self.ctx = ctx

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return []

    def validate(self) -> list[str]:
        """返回中文错误列表；空列表表示配置可用。默认只检查必填项。"""
        errors: list[str] = []
        for f in self.config_schema():
            if not f.required:
                continue
            source = self.ctx.secrets if f.type == "secret" else self.ctx.settings
            value = source.get(f.key)
            if value is None or (isinstance(value, str) and not value.strip()):
                errors.append(f"缺少必填项：{f.label}")
        return errors

    @abstractmethod
    async def send(self, report: ReportPayload) -> DeliveryResult:
        """投递报告。自己处理长度限制、分段、重试（≤2 次）和幂等（用 report_id）。
        不要抛异常：失败时返回 ok=False 和中文 detail。"""

    async def test(self) -> DeliveryResult:
        """发送一条测试消息。默认构造一份 is_test=True 的简短报告并调用 send。"""
        sample = ReportPayload(
            report_id="test",
            run_id="test",
            title="情报局 · 通道测试",
            date_label="测试",
            window_label="—",
            summary_md="**情报局通道测试**\n\n收到这条消息说明推送通道配置正确。",
            summary_text="情报局通道测试：收到这条消息说明推送通道配置正确。",
            full_md="# 情报局 · 通道测试\n\n收到这条消息说明推送通道配置正确。",
            is_test=True,
        )
        return await self.send(sample)

    def result(self, ok: bool, detail: str, **kw: Any) -> DeliveryResult:
        return DeliveryResult(ok=ok, channel_id=self.ctx.channel_id, kind=self.kind, detail=detail, **kw)

    async def aclose(self) -> None:
        return None


def split_text(text: str, limit: int, *, measure: str = "chars") -> list[str]:
    """按段落、再按行切分文本，使每段不超过 limit。

    measure="bytes" 时按 UTF-8 字节计算（企业微信等通道用）。
    单行超长时硬切。
    """

    def size(s: str) -> int:
        return len(s.encode("utf-8")) if measure == "bytes" else len(s)

    if size(text) <= limit:
        return [text]

    parts: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf.strip():
            parts.append(buf.rstrip("\n"))
        buf = ""

    for line in text.splitlines(keepends=True):
        if size(buf) + size(line) <= limit:
            buf += line
            continue
        flush()
        while size(line) > limit:
            if measure == "bytes":
                # 回退到合法的 UTF-8 边界
                piece = line.encode("utf-8")[:limit].decode("utf-8", errors="ignore")
            else:
                piece = line[:limit]
            if not piece:          # limit 小于单个字符的字节数时，至少前进一个字符
                piece = line[:1]
            parts.append(piece)
            line = line[len(piece):]
        buf = line
    flush()
    return parts
