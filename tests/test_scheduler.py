"""调度：错过检测、补跑、cron 校验。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from bureau.scheduler import BureauScheduler, make_trigger, missed_fire_time, next_fire

TZ = ZoneInfo("Asia/Shanghai")


def test_missed_fire_time_rules():
    now = datetime(2026, 10, 28, 10, 0, tzinfo=TZ)
    # 昨天 08:00 跑过，今天 08:00 没跑 → 错过今天 08:00
    assert missed_fire_time("0 8 * * *", "Asia/Shanghai", last_fire=now - timedelta(days=1, hours=2),
                            created=None, now=now) == datetime(2026, 10, 28, 8, 0, tzinfo=TZ)
    # 今天 08:00 已经跑过 → 没有错过
    assert missed_fire_time("0 8 * * *", "Asia/Shanghai", last_fire=now.replace(hour=8), created=None, now=now) is None
    # 今天 09:00 才创建 → 不算错过今天 08:00
    assert missed_fire_time("0 8 * * *", "Asia/Shanghai", last_fire=None, created=now.replace(hour=9), now=now) is None
    # 关机三天：只看 36 小时内，且只补一次（返回最近一次）
    assert missed_fire_time("0 8 * * *", "Asia/Shanghai", last_fire=now - timedelta(days=3), created=None, now=now,
                            max_hours=36) == datetime(2026, 10, 28, 8, 0, tzinfo=TZ)
    # 超过补跑期限
    assert missed_fire_time("0 8 * * *", "Asia/Shanghai", last_fire=now - timedelta(days=3), created=None,
                            now=now.replace(hour=23) + timedelta(days=1), max_hours=6) is None


def test_cron_validation_and_next_fire():
    with pytest.raises(ValueError, match="cron 表达式无效"):
        make_trigger("every day", "Asia/Shanghai")
    with pytest.raises(ValueError, match="时区无效"):
        make_trigger("0 8 * * *", "Mars/Base")
    after = datetime(2026, 10, 28, 9, 0, tzinfo=TZ)
    assert next_fire("0 8 * * *", "Asia/Shanghai", after) == datetime(2026, 10, 29, 8, 0, tzinfo=TZ)
    assert next_fire("0 12,20 * * *", "Asia/Shanghai", after) == datetime(2026, 10, 28, 12, 0, tzinfo=TZ)


def _weekdays(cron: str, n: int = 7) -> list[str]:
    """从 2026-10-25（周日）00:00 起，连续取 n 次触发时间的星期缩写。"""
    trig = make_trigger(cron, "Asia/Shanghai")
    t = datetime(2026, 10, 25, 0, 0, tzinfo=TZ)
    out = []
    prev = None
    for _ in range(n):
        t = trig.get_next_fire_time(prev, t if prev is None else prev + timedelta(seconds=1))
        out.append(t.strftime("%a"))
        prev = t
    return out


def test_weekday_numbers_follow_standard_cron():
    # 标准 cron：1-5 是周一到周五（APScheduler 原生 from_crontab 会算成周二到周六）
    assert _weekdays("0 9 * * 1-5", 5) == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert _weekdays("0 9 * * mon-fri", 5) == ["Mon", "Tue", "Wed", "Thu", "Fri"]
    assert _weekdays("0 9 * * 0", 2) == ["Sun", "Sun"]
    assert _weekdays("0 9 * * 7", 2) == ["Sun", "Sun"]
    assert _weekdays("0 9 * * 6,0", 4) == ["Sun", "Sat", "Sun", "Sat"]
    assert _weekdays("0 9 * * 5-7", 3) == ["Sun", "Fri", "Sat"]
    assert _weekdays("0 9 * * */2", 4) == ["Sun", "Tue", "Thu", "Sat"]
    assert _weekdays("0 9 * * 0-6", 7) == ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]


def test_cron_rejects_ambiguous_or_bad_weekday():
    with pytest.raises(ValueError, match="不能同时限定"):
        make_trigger("0 9 1 * mon", "Asia/Shanghai")
    with pytest.raises(ValueError, match="首尾颠倒"):
        make_trigger("0 9 * * fri-mon", "Asia/Shanghai")
    with pytest.raises(ValueError, match="无效"):
        make_trigger("0 9 * * 8", "Asia/Shanghai")


def test_catch_up_runs_missed_schedule_once(app):
    s = app.store.list_schedules()[0]
    two_days_ago = (app.now() - timedelta(days=2)).isoformat(timespec="seconds")
    app.store.mark_schedule_fired(s["id"], two_days_ago)
    app.db.execute("UPDATE schedules SET created_at=? WHERE id=?", (two_days_ago, s["id"]))

    async def main():
        sched = BureauScheduler(app)
        sched.start()
        try:
            first = await sched.catch_up()
            await app.runner.wait_idle(30)
            second = await sched.catch_up()                       # 刚补跑过，不再重复
            await app.runner.wait_idle(30)
            nxt = sched.next_run_at(app.store.get_schedule(s["id"]))
            return first, second, nxt
        finally:
            sched.shutdown()

    first, second, nxt = asyncio.run(main())
    assert first == [s["id"]] and second == []
    runs, _ = app.store.list_runs(10)
    assert [r["trigger"] for r in runs] == ["catchup"]
    assert runs[0]["schedule_id"] == s["id"] and runs[0]["status"] == "success"   # 没有白名单群，提前结束
    assert nxt and nxt.endswith("+08:00") and "T08:00:00" in nxt
