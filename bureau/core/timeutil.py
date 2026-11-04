"""时间工具。内部一律使用带时区的 datetime。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

WEEKDAYS = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]


@lru_cache(maxsize=16)
def tzinfo(name: str = "Asia/Shanghai") -> ZoneInfo:
    return ZoneInfo(name)


def now(tz: str = "Asia/Shanghai") -> datetime:
    return datetime.now(tzinfo(tz))


def ensure_aware(dt: datetime, tz: str = "Asia/Shanghai") -> datetime:
    return dt.replace(tzinfo=tzinfo(tz)) if dt.tzinfo is None else dt


def to_tz(dt: datetime, tz: str = "Asia/Shanghai") -> datetime:
    return ensure_aware(dt, tz).astimezone(tzinfo(tz))


def iso(dt: datetime | None, tz: str | None = None) -> str | None:
    if dt is None:
        return None
    if tz:
        dt = to_tz(dt, tz)
    return dt.isoformat(timespec="seconds")


def parse_iso(s: str | None, tz: str = "Asia/Shanghai") -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        try:
            from dateutil import parser as du
            dt = du.parse(s)
        except (ValueError, OverflowError, ImportError):
            return None
    return ensure_aware(dt, tz)


def epoch(dt: datetime) -> int:
    return int(ensure_aware(dt).timestamp())


def from_epoch(ts: int | float, tz: str = "Asia/Shanghai") -> datetime:
    return datetime.fromtimestamp(ts, tzinfo(tz))


def weekday_cn(dt: datetime) -> str:
    return WEEKDAYS[dt.weekday()]


def date_label(dt: datetime, tz: str = "Asia/Shanghai") -> str:
    d = to_tz(dt, tz)
    return f"{d:%Y-%m-%d}（{weekday_cn(d)}）"


def window_label(start: datetime, end: datetime, tz: str = "Asia/Shanghai") -> str:
    s, e = to_tz(start, tz), to_tz(end, tz)
    if s.year != e.year:
        return f"{s:%Y-%m-%d %H:%M} ~ {e:%Y-%m-%d %H:%M}"
    return f"{s:%m-%d %H:%M} ~ {e:%m-%d %H:%M}"


def floor_minutes(dt: datetime, minutes: int) -> datetime:
    dt = dt.replace(second=0, microsecond=0)
    return dt - timedelta(minutes=dt.minute % minutes)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
