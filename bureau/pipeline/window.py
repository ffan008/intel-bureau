"""运行窗口：since_last 取上次成功运行的 until（最多回溯 72 小时），首跑取 24 小时；fixed_hours 固定小时数。"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from bureau.core.timeutil import parse_iso


def compute_window(app: Any, *, demo: bool, window_mode: str = "since_last", window_hours: int | None = None,
                   schedule_id: str | None = None, now: datetime | None = None) -> tuple[datetime, datetime]:
    if demo:
        anchor = app.demo_anchor()
        end = anchor or (now or app.now()).replace(minute=0, second=0, microsecond=0)
        return end - timedelta(hours=int(window_hours or 24)), end
    end = (now or app.now()).replace(second=0, microsecond=0)
    max_back = int(app.config.get("sources.collect.max_lookback_hours", 72) or 72)
    # 定时任务按 window_mode；临时运行指定了 window_hours 就按固定小时数
    fixed = bool(window_hours) and (window_mode == "fixed_hours" or schedule_id is None)
    if fixed:
        hours = min(int(window_hours or 24), 24 * 31)
        return end - timedelta(hours=hours), end
    last = parse_iso(app.store.last_success_window_end(schedule_id=schedule_id), app.tz)
    if last is None and schedule_id is not None:
        last = parse_iso(app.store.last_success_window_end(), app.tz)
    if last is None:
        start = end - timedelta(hours=int(app.config.get("sources.collect.first_run_hours", 24) or 24))
    else:
        start = max(last, end - timedelta(hours=max_back))
    if end - start < timedelta(hours=1):          # 两次运行挨得太近时至少看 1 小时
        start = end - timedelta(hours=1)
    return start, end
