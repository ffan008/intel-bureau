"""集成层共用的小工具：时区、时间戳、稳定哈希、日志安全的文本截断。"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DEFAULT_TZ = "Asia/Shanghai"
_WS_RE = re.compile(r"\s+")


def get_tz(name: str | None) -> tzinfo:
    """按名字取时区；名字无效时退回 Asia/Shanghai。"""
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo(DEFAULT_TZ)


def local_tz() -> tzinfo:
    """本机当前时区（lark-cli 按本机时区格式化时间，解析时要用同一个）。"""
    return datetime.now().astimezone().tzinfo or timezone.utc


def from_timestamp(value: object, tz: tzinfo) -> datetime | None:
    """Unix 时间戳（秒或毫秒，数字或数字字符串）转带时区的 datetime。"""
    try:
        n = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    if n > 1e12:          # 毫秒
        n /= 1000.0
    try:
        return datetime.fromtimestamp(n, tz=timezone.utc).astimezone(tz)
    except (OverflowError, OSError, ValueError):
        return None


def ensure_aware(dt: datetime, tz: tzinfo) -> datetime:
    """无时区的 datetime 视为 tz 本地时间。"""
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt


def stable_id(*parts: object, length: int = 24) -> str:
    """由若干字段生成稳定的短哈希（同样的输入永远得到同样的结果）。"""
    joined = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()[:length]


def preview(text: str | None, n: int = 40) -> str:
    """日志里最多只写正文前 n 个字（ARCHITECTURE §4）。"""
    s = _WS_RE.sub(" ", text or "").strip()
    return s if len(s) <= n else s[:n] + "…"


def clip(text: str | None, n: int) -> str:
    """把一段文字截到 n 个字以内，超出时以省略号结尾。"""
    s = (text or "").strip()
    return s if len(s) <= n else s[: max(n - 1, 0)] + "…"


def as_str(value: object) -> str:
    """None → ""，其余转字符串并去掉首尾空白。"""
    return "" if value is None else str(value).strip()
