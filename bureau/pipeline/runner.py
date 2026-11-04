"""流水线运行器：同一时间只允许一次运行（进程内锁 + 跨进程文件锁）、支持取消与 dry_run、
每个阶段发 run.stage 事件并写 run_stages。"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import time
from dataclasses import dataclass, field
from typing import Any

from bureau.core.constants import STAGE_AGENT, STAGE_LABELS, STAGES
from bureau.core.dto import TOTALS_DEFAULT, run_dto
from bureau.core.logging import RunLogger
from bureau.core.timeutil import iso
from bureau.pipeline import STAGE_FUNCS
from bureau.pipeline.models import RunContext, StopPipeline
from bureau.pipeline.window import compute_window

log = logging.getLogger("bureau.runner")
NON_FATAL = {"compose", "deliver", "archive"}


class RunBusyError(RuntimeError):
    pass


@dataclass
class RunRequest:
    trigger: str = "manual"                  # manual / schedule / catchup / demo
    schedule_id: str | None = None
    platforms: list[str] = field(default_factory=list)
    group_keys: list[str] = field(default_factory=list)
    channel_ids: list[str] | None = None
    window_hours: int | None = None
    window_mode: str = "since_last"
    dry_run: bool = False
    demo: bool = False
    top_n: int | None = None


class FileLock:
    """跨进程锁（命令行 run 与服务进程互斥）。进程退出时操作系统自动释放。"""

    def __init__(self, path: Any) -> None:
        self.path = path
        self.fh: Any = None

    def acquire(self) -> bool:
        fh = open(self.path, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self.fh = fh
        return True

    def release(self) -> None:
        if self.fh is None:
            return
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            self.fh.close()
            self.fh = None


def new_id(prefix: str, app: Any) -> str:
    return f"{prefix}-{app.now():%Y%m%d-%H%M%S}-{secrets.token_hex(2)}"


class PipelineRunner:
    def __init__(self, app: Any) -> None:
        self.app = app
        self._task: asyncio.Task[Any] | None = None
        self._rc: RunContext | None = None
        self._lock = FileLock(app.paths.run_lock)
        self._last_progress: dict[str, float] = {}
        self._cancel_flag = False
        self._started = False
        self._background = False     # True：由 API / 大屏在后台启动；False：命令行或测试直接 await

    @property
    def busy(self) -> bool:
        return self._rc is not None

    @property
    def current_run_id(self) -> str | None:
        return self._rc.run_id if self._rc else None

    def current_dto(self) -> dict[str, Any] | None:
        if self._rc is None:
            return None
        run = self.app.store.get_run(self._rc.run_id)
        return run_dto(run) if run else None

    # ---------- 启动 ----------
    def prepare(self, req: RunRequest) -> RunContext:
        if self._rc is not None:
            raise RunBusyError("已有运行在进行中")
        if not self._lock.acquire():
            raise RunBusyError("另一个进程正在运行流水线")
        try:
            app = self.app
            settings = app.config.settings
            start, end = compute_window(app, demo=req.demo, window_mode=req.window_mode,
                                        window_hours=req.window_hours, schedule_id=req.schedule_id)
            run_id = new_id("run", app)
            trigger = "demo" if req.demo and req.trigger == "manual" else req.trigger
            params = {"platforms": req.platforms, "group_keys": req.group_keys, "channel_ids": req.channel_ids,
                      "window_hours": req.window_hours, "window_mode": req.window_mode, "demo": req.demo}
            app.store.create_run(run_id, trigger=trigger, schedule_id=req.schedule_id, dry_run=req.dry_run,
                                 is_demo=req.demo, window_start=iso(start, app.tz), window_end=iso(end, app.tz),
                                 params=params)
            rc = RunContext(app=app, run_id=run_id, trigger=trigger, schedule_id=req.schedule_id, dry_run=req.dry_run,
                            demo=req.demo, start=start, end=end, platforms=list(req.platforms or []),
                            group_keys=list(req.group_keys or []), channel_ids=req.channel_ids,
                            top_n=int(req.top_n or settings.get("pipeline", {}).get("top_n", 5)), settings=settings,
                            log=RunLogger(run_id, app.store, app.bus, app.tz))
            rc.totals = dict(TOTALS_DEFAULT)
            rc.report["id"] = new_id("rpt", app)
            rc.progress = self._progress
            self._rc = rc
            self._cancel_flag = self._started = False
            return rc
        except Exception:
            self._lock.release()
            raise

    async def start(self, req: RunRequest) -> dict[str, Any]:
        """启动后台运行，立即返回 RunDTO（queued）。"""
        rc = self.prepare(req)
        self._background = True
        self._task = asyncio.create_task(self._execute(rc), name=f"run-{rc.run_id}")
        return run_dto(self.app.store.get_run(rc.run_id))  # type: ignore[arg-type]

    async def run(self, req: RunRequest) -> dict[str, Any]:
        """在当前协程里跑完（命令行和测试用）。"""
        rc = self.prepare(req)
        self._background = False
        self._task = asyncio.current_task()
        await self._execute(rc)
        return run_dto(self.app.store.get_run(rc.run_id))  # type: ignore[arg-type]

    def cancel(self, run_id: str) -> bool:
        """协作式取消：设置标志（阶段之间检查）；任务已开始执行时再打断当前的 await。
        任务还没开始就直接 cancel 会跳过清理逻辑，所以未开始时只设标志。"""
        if self._rc is None or self._rc.run_id != run_id:
            return False
        self._cancel_flag = True
        self._rc.log.warn("RUNNER", "收到取消请求")
        if self._task is not None and self._started and self._task is not asyncio.current_task():
            self._task.cancel()
        return True

    async def wait_idle(self, timeout: float | None = None) -> bool:
        t0 = time.monotonic()
        while self.busy:
            if timeout is not None and time.monotonic() - t0 > timeout:
                return False
            await asyncio.sleep(0.2)
        return True

    # ---------- 执行 ----------
    async def _execute(self, rc: RunContext) -> None:
        app, store = self.app, self.app.store
        self._started = True
        status, error = "success", None
        store.update_run(rc.run_id, status="running", started_at=store.now_iso())
        app.bus.publish("run.started", run_dto(store.get_run(rc.run_id)))  # type: ignore[arg-type]
        mode = "演示" if rc.demo else "实时"
        rc.log.info("RUNNER", f"开始运行（{mode}{'，仅预览' if rc.dry_run else ''}）：窗口 {iso(rc.start, rc.tz)} ~ {iso(rc.end, rc.tz)}")
        stopped: str | None = None
        idx = 0
        try:
            for idx, name in enumerate(STAGES):
                if self._cancel_flag:
                    raise asyncio.CancelledError()
                if stopped is not None:
                    self._finish_stage(rc, name, "skipped", {}, stopped, None, None)
                    continue
                ok, msg = await self._run_stage(rc, name)
                if ok == "stop":
                    stopped = msg
                elif ok == "failed":
                    if name in NON_FATAL:
                        status = "partial"
                    else:
                        status, error, stopped = "failed", f"阶段 {STAGE_LABELS[name]} 失败：{msg}", "前序阶段失败"
            if rc.deliveries and not all(d["ok"] for d in rc.deliveries) and status == "success":
                status = "partial"
        except asyncio.CancelledError:
            status, error = "cancelled", "已取消"
            for name in STAGES[idx:]:
                row = next((s for s in store.get_stages(rc.run_id) if s["name"] == name), None)
                if row and row["status"] in ("pending", "running"):
                    self._finish_stage(rc, name, "skipped" if row["status"] == "pending" else "failed", row["metrics"],
                                       "已取消", None, row.get("started_at"))
            rc.log.warn("RUNNER", "运行已取消")
        except Exception as exc:                                     # noqa: BLE001
            status, error = "failed", f"运行出错：{exc}"
            log.exception("运行 %s 出错", rc.run_id)
        finally:
            store.update_run(rc.run_id, status=status, error=error, finished_at=store.now_iso(),
                             totals=self._totals(rc))
            dto = run_dto(store.get_run(rc.run_id))  # type: ignore[arg-type]
            rc.log.log("info" if status in ("success", "partial") else "warn", "RUNNER",
                       f"运行结束：{ {'success': '成功', 'partial': '部分成功', 'failed': '失败', 'cancelled': '已取消'}[status] }"
                       + (f"（{error}）" if error else ""))
            app.bus.publish("run.finished", dto)
            app.bus.publish("overview.dirty", {})
            app.overview_cache.clear()
            self._rc = None
            self._task = None
            self._lock.release()

    async def _run_stage(self, rc: RunContext, name: str) -> tuple[str, str]:
        store = self.app.store
        t0 = time.perf_counter()
        started = store.now_iso()
        store.update_stage(rc.run_id, name, status="running", started_at=started)
        self._publish_stage(rc, name, "running", {}, f"{STAGE_LABELS[name]}中", started, None, None)
        try:
            res = await STAGE_FUNCS[name](rc)
        except StopPipeline as exc:
            self._finish_stage(rc, name, "done", {}, str(exc), t0, started)
            rc.log.info(STAGE_AGENT[name], f"{exc}，后续阶段跳过", name)
            return "stop", str(exc)
        except asyncio.CancelledError:
            self._finish_stage(rc, name, "failed", {}, "已取消", t0, started)
            raise
        except Exception as exc:                                     # noqa: BLE001
            log.exception("阶段 %s 出错", name)
            rc.log.error(STAGE_AGENT[name], f"{STAGE_LABELS[name]}失败：{exc}", name)
            self._finish_stage(rc, name, "failed", {}, f"出错：{exc}", t0, started)
            return "failed", str(exc)
        pace = self._pace_ms(rc)
        if pace and res.status == "done":
            # 只用于大屏上的演示运行：离线规则几秒内就能跑完 12 个阶段，动画会一闪而过。
            # 这里只是把阶段的"完成"时刻推迟，数据和结果不受影响；真实运行和命令行运行不受影响。
            # Windows 上 asyncio 的计时器精度约 15.6ms，可能提前唤醒，所以循环补足到目标时长
            try:
                while (remain := pace / 1000 - (time.perf_counter() - t0)) > 0:
                    await asyncio.sleep(remain + 0.02)
            except asyncio.CancelledError:
                self._finish_stage(rc, name, "failed", res.metrics, "已取消", t0, started)
                raise
        self._finish_stage(rc, name, res.status, res.metrics, res.message, t0, started)
        return "ok", res.message

    def _pace_ms(self, rc: RunContext) -> int:
        """大屏演示运行的每阶段最短展示时长（毫秒）。环境变量 BUREAU_DEMO_PACE_MS 可覆盖（测试设为 0）。"""
        if not (rc.demo and self._background):
            return 0
        raw = os.environ.get("BUREAU_DEMO_PACE_MS")
        if raw is None:
            raw = rc.cfg("app.demo_stage_min_ms", 1100)
        try:
            return max(0, min(int(raw), 5000))
        except (TypeError, ValueError):
            return 0

    def _finish_stage(self, rc: RunContext, name: str, status: str, metrics: dict[str, Any], message: str,
                      t0: float | None, started: str | None) -> None:
        store = self.app.store
        fields: dict[str, Any] = {"status": status, "metrics": metrics, "message": message}
        dur = None
        if t0 is not None:
            dur = int((time.perf_counter() - t0) * 1000)
            fields.update(finished_at=store.now_iso(), duration_ms=dur)
        store.update_stage(rc.run_id, name, **fields)
        store.update_run(rc.run_id, totals=self._totals(rc))
        self._publish_stage(rc, name, status, metrics, message, started, fields.get("finished_at"), dur)

    def _publish_stage(self, rc: RunContext, name: str, status: str, metrics: dict[str, Any], message: str,
                       started: str | None, finished: str | None, dur: int | None) -> None:
        stage: dict[str, Any] = {"name": name, "agent": STAGE_AGENT[name], "status": status, "metrics": metrics}
        for k, v in (("started_at", started), ("finished_at", finished), ("duration_ms", dur), ("message", message)):
            if v is not None and v != "":
                stage[k] = v
        self.app.bus.publish("run.stage", {"run_id": rc.run_id, "stage": stage})

    def _progress(self, name: str, metrics: dict[str, Any], message: str | None) -> None:
        """阶段内的进度更新（节流到每 0.3 秒一次）。"""
        rc = self._rc
        if rc is None:
            return
        now = time.monotonic()
        if now - self._last_progress.get(name, 0) < 0.3:
            return
        self._last_progress[name] = now
        self.app.store.update_stage(rc.run_id, name, metrics=metrics, message=message or "")
        self._publish_stage(rc, name, "running", metrics, message or "", None, None, None)

    @staticmethod
    def _totals(rc: RunContext) -> dict[str, Any]:
        t = dict(TOTALS_DEFAULT)
        t.update(rc.totals)
        t["items"] = len(rc.items) if rc.items else t.get("items", 0)
        t["llm_provider"] = rc.llm_provider if rc.totals.get("llm_provider") else t.get("llm_provider", "")
        return t
