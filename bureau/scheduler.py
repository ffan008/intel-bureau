"""调度（§15）：APScheduler AsyncIOScheduler；每个定时任务一个 CronTrigger（由 make_trigger 按标准 cron 构造），
misfire_grace_time=3600、coalesce=True。启动时检查因关机错过的运行，错过就补跑一次。"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from apscheduler.events import EVENT_JOB_MISSED, JobExecutionEvent
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from bureau.core.timeutil import iso, parse_iso, tzinfo

log = logging.getLogger("bureau.scheduler")

# 标准 cron 的星期：0 和 7 都是周日，1 是周一 …… 6 是周六。
# APScheduler 3.x 的 from_crontab 把数字 0 当周一，"1-5" 会变成周二到周六，所以这里自己换算成英文缩写。
_STD_DOW_NAMES = {"sun": 0, "mon": 1, "tue": 2, "wed": 3, "thu": 4, "fri": 5, "sat": 6}
_APS_DOW = ("sun", "mon", "tue", "wed", "thu", "fri", "sat")      # 下标为标准 cron 的数字


def _std_dow_value(token: str) -> int:
    t = token.strip().lower()
    if t in _STD_DOW_NAMES:
        return _STD_DOW_NAMES[t]
    if not t.isdigit() or not 0 <= int(t) <= 7:
        raise ValueError(f"星期字段里的「{token}」无效（0~7 或 sun~sat）")
    return int(t) % 7


def std_dow_to_aps(field: str) -> str:
    """把标准 cron 的星期字段（支持 * 、列表、区间、步长、英文缩写，0/7=周日）换算成 APScheduler 的写法。"""
    field = field.strip()
    if field in ("*", "?"):
        return "*"
    days: set[int] = set()
    for part in field.split(","):
        base, _, step_s = part.partition("/")
        step = 1
        if step_s:
            if not step_s.isdigit() or int(step_s) < 1:
                raise ValueError(f"星期字段的步长「{step_s}」无效")
            step = int(step_s)
        if base in ("*", "?"):
            lo, hi = 0, 6
        elif "-" in base:
            a, _, b = base.partition("-")
            lo = _std_dow_value(a)
            hi = 7 if b.strip() == "7" else _std_dow_value(b)
            if hi < lo:
                raise ValueError(f"星期区间「{base}」首尾颠倒；跨周末请写成列表，如 fri,sat,sun")
        else:
            lo = hi = _std_dow_value(base)
            if step_s:
                hi = 6
        days.update(d % 7 for d in range(lo, hi + 1, step))
    if len(days) == 7:
        return "*"
    return ",".join(_APS_DOW[d] for d in sorted(days))


def make_trigger(cron: str, tz: str) -> CronTrigger:
    """校验并构造触发器；cron 不合法时抛 ValueError（中文）。星期字段按标准 cron 解释（0/7=周日）。"""
    try:
        tzinfo(tz)
    except Exception as exc:                                         # noqa: BLE001
        raise ValueError(f"时区无效：{tz}") from exc
    fields = cron.split()
    hint = "（格式：分 时 日 月 周，例如 0 8 * * *）"
    if len(fields) != 5:
        raise ValueError(f"cron 表达式无效：{cron}{hint}")
    minute, hour, dom, month, dow = fields
    if dom not in ("*", "?") and dow not in ("*", "?"):
        # 标准 cron 里两者是"或"，APScheduler 是"且"；为避免触发时间和界面说明不一致，直接拒绝。
        raise ValueError(f"cron 表达式无效：{cron}。「日」和「周」不能同时限定，请只保留其中一个")
    try:
        return CronTrigger(minute=minute, hour=hour, day=dom, month=month, day_of_week=std_dow_to_aps(dow),
                           timezone=tzinfo(tz))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"cron 表达式无效：{cron}{hint}；{exc}") from exc


def next_fire(cron: str, tz: str, after: datetime) -> datetime | None:
    try:
        return make_trigger(cron, tz).get_next_fire_time(None, after)
    except ValueError:
        return None


def missed_fire_time(cron: str, tz: str, *, last_fire: datetime | None, created: datetime | None, now: datetime,
                     max_hours: float = 36) -> datetime | None:
    """自上次触发（或任务创建）以来、now 之前最后一个应触发而未触发的时间；没有则 None。只看 max_hours 以内。"""
    trig = make_trigger(cron, tz)
    floor = now - timedelta(hours=max_hours)
    anchor = max([t for t in (last_fire, created, floor) if t is not None])
    t = trig.get_next_fire_time(None, anchor + timedelta(seconds=1))
    missed = None
    for _ in range(20000):
        if t is None or t > now:
            break
        missed = t
        t = trig.get_next_fire_time(t, t + timedelta(seconds=1))
    return missed


class BureauScheduler:
    def __init__(self, app: Any) -> None:
        self.app = app
        self.sched = AsyncIOScheduler(timezone=tzinfo(app.tz))
        self.started = False
        self._tasks: set[asyncio.Task[Any]] = set()

    def start(self) -> None:
        if self.started:
            return
        self.sched.add_listener(self._on_missed, EVENT_JOB_MISSED)
        self.sched.start()
        self.started = True
        self.reload()

    def shutdown(self) -> None:
        if self.started:
            self.sched.shutdown(wait=False)
            self.started = False
        for t in list(self._tasks):
            t.cancel()

    def reload(self) -> None:
        if not self.started:
            return
        self.sched.remove_all_jobs()
        for s in self.app.store.list_schedules():
            if not s["enabled"]:
                continue
            try:
                trig = make_trigger(s["cron"], s["timezone"])
            except ValueError as exc:
                log.warning("定时任务 %s 无法加载：%s", s["name"], exc)
                continue
            self.sched.add_job(self._fire, trig, args=[s["id"], "schedule"], id=s["id"], name=s["name"],
                               misfire_grace_time=3600, coalesce=True, max_instances=1, replace_existing=True)

    def next_run_at(self, schedule: dict[str, Any]) -> str | None:
        if not schedule.get("enabled"):
            return None
        job = self.sched.get_job(schedule["id"]) if self.started else None
        if job is not None and job.next_run_time is not None:
            return iso(job.next_run_time, self.app.tz)
        nf = next_fire(schedule["cron"], schedule["timezone"], self.app.now())
        return iso(nf, self.app.tz) if nf else None

    def next_run_at_any(self) -> str | None:
        times = [t for t in (self.next_run_at(s) for s in self.app.store.list_schedules()) if t]
        return min(times, key=lambda t: parse_iso(t, self.app.tz)) if times else None  # type: ignore[arg-type,return-value]

    def _on_missed(self, event: JobExecutionEvent) -> None:
        """电脑睡眠超过宽限期时 APScheduler 会跳过这次触发；这里补跑一次。"""
        log.warning("定时任务 %s 错过了 %s 的触发，补跑一次", event.job_id, event.scheduled_run_time)
        self._spawn(self._fire(event.job_id, "catchup"))

    def _spawn(self, coro: Any) -> None:
        task = asyncio.get_event_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _fire(self, schedule_id: str, trigger: str = "schedule") -> str | None:
        from bureau.pipeline.runner import RunBusyError, RunRequest

        s = self.app.store.get_schedule(schedule_id)
        if s is None or not s["enabled"]:
            return None
        self.app.store.mark_schedule_fired(schedule_id, self.app.store.now_iso())
        runner = self.app.runner
        if not await runner.wait_idle(timeout=1800):
            log.warning("定时任务「%s」等待 30 分钟仍有运行在进行，本次跳过", s["name"])
            return None
        req = RunRequest(trigger=trigger, schedule_id=schedule_id, platforms=s["platforms"], group_keys=s["group_keys"],
                         channel_ids=s["channel_ids"], window_hours=s["window_hours"], window_mode=s["window_mode"],
                         dry_run=s["dry_run"], top_n=s["top_n"])
        try:
            dto = await runner.start(req)
        except RunBusyError as exc:
            log.warning("定时任务「%s」未能启动：%s", s["name"], exc)
            return None
        log.info("定时任务「%s」已启动运行 %s（%s）", s["name"], dto["id"], trigger)
        return dto["id"]

    async def catch_up(self, now: datetime | None = None) -> list[str]:
        """启动时补跑：每个任务最多补一次。返回补跑的任务 id。"""
        cfg = self.app.config
        if not cfg.get("app.catchup_enabled", True):
            return []
        now = now or self.app.now()
        max_h = float(cfg.get("app.catchup_max_hours", 36) or 36)
        out = []
        for s in self.app.store.list_schedules():
            if not s["enabled"]:
                continue
            try:
                missed = missed_fire_time(s["cron"], s["timezone"], last_fire=parse_iso(s.get("last_fire_at"), self.app.tz),
                                          created=parse_iso(s.get("created_at"), self.app.tz), now=now, max_hours=max_h)
            except ValueError:
                continue
            if missed is None:
                continue
            log.info("定时任务「%s」错过了 %s 的运行（可能是电脑关机），现在补跑", s["name"], iso(missed, self.app.tz))
            await self._fire(s["id"], "catchup")
            out.append(s["id"])
        return out
