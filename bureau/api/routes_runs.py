"""运行与定时任务。"""

from __future__ import annotations

import secrets
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from bureau.api.deps import get_ctx, json_body, page
from bureau.api.errors import ApiError
from bureau.core.app import AppContext
from bureau.core.constants import LIVE_PLATFORMS
from bureau.core.dto import run_dto, schedule_dto
from bureau.pipeline.runner import RunBusyError, RunRequest
from bureau.scheduler import make_trigger, next_fire

router = APIRouter(prefix="/api")


def _str_list(v: Any, name: str) -> list[str]:
    if v is None:
        return []
    if not isinstance(v, list):
        raise ApiError(400, "invalid_request", f"{name} 必须是数组")
    return [str(x) for x in v]


async def start_run(ctx: AppContext, req: RunRequest) -> JSONResponse:
    try:
        dto = await ctx.runner.start(req)
    except RunBusyError as exc:
        current = ctx.runner.current_dto()
        raise ApiError(409, "run_in_progress", f"{exc}，请等它结束或先取消",
                       f"当前运行：{current['id']}" if current else None) from None
    return JSONResponse(dto, status_code=202)


@router.post("/runs")
async def create_run(request: Request, ctx: AppContext = Depends(get_ctx)) -> JSONResponse:
    body = await json_body(request)
    platforms = _str_list(body.get("platforms"), "platforms")
    bad = [p for p in platforms if p not in LIVE_PLATFORMS]
    if bad:
        raise ApiError(400, "invalid_platform", f"不支持的平台：{'、'.join(bad)}")
    hours = body.get("window_hours")
    if hours is not None and (not isinstance(hours, (int, float)) or not 1 <= hours <= 744):
        raise ApiError(400, "invalid_window", "window_hours 必须在 1~744 之间")
    demo = body.get("demo")
    demo = (ctx.mode() == "demo") if demo is None else bool(demo)
    channel_ids = body.get("channel_ids")
    req = RunRequest(trigger="manual", platforms=platforms, group_keys=_str_list(body.get("group_keys"), "group_keys"),
                     channel_ids=_str_list(channel_ids, "channel_ids") if channel_ids is not None else None,
                     window_hours=int(hours) if hours else None, window_mode="fixed_hours" if hours else "since_last",
                     dry_run=bool(body.get("dry_run", False)), demo=demo)
    return await start_run(ctx, req)


@router.get("/runs")
def list_runs(limit: int | None = None, offset: int | None = None, schedule_id: str | None = None,
              ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    lim, off = page(limit, offset)
    rows, total = ctx.store.list_runs(lim, off, schedule_id=schedule_id)
    return {"items": [run_dto(r) for r in rows], "total": total}


def _run_or_404(ctx: AppContext, run_id: str) -> dict[str, Any]:
    run = ctx.store.get_run(run_id)
    if run is None:
        raise ApiError(404, "run_not_found", f"运行不存在：{run_id}")
    return run


@router.get("/runs/{run_id}")
def get_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return run_dto(_run_or_404(ctx, run_id))


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    run = _run_or_404(ctx, run_id)
    if run["status"] not in ("queued", "running"):
        raise ApiError(409, "not_running", "该运行已经结束")
    if not ctx.runner.cancel(run_id):
        raise ApiError(409, "not_cancellable", "该运行不在本服务进程中（可能由命令行启动）")
    await ctx.runner.wait_idle(timeout=10)
    return run_dto(_run_or_404(ctx, run_id))


@router.get("/runs/{run_id}/logs")
def run_logs(run_id: str, ctx: AppContext = Depends(get_ctx)) -> list[dict[str, Any]]:
    _run_or_404(ctx, run_id)
    return ctx.store.run_logs(run_id)


# ---------------- 定时任务 ----------------
def _schedule_out(ctx: AppContext, s: dict[str, Any]) -> dict[str, Any]:
    if ctx.scheduler is not None:
        nxt = ctx.scheduler.next_run_at(s)
    else:
        nf = next_fire(s["cron"], s["timezone"], ctx.now()) if s["enabled"] else None
        nxt = nf.isoformat(timespec="seconds") if nf else None
    return schedule_dto(s, next_run_at=nxt, last_run=ctx.store.last_run_for_schedule(s["id"]))


def _validate_schedule(ctx: AppContext, body: dict[str, Any], *, partial: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "name" in body or not partial:
        name = str(body.get("name") or "").strip()
        if not name or len(name) > 40:
            raise ApiError(400, "invalid_name", "任务名不能为空，且不超过 40 字")
        out["name"] = name
    if "cron" in body or "timezone" in body or not partial:
        cron = str(body.get("cron") or "").strip()
        tz = str(body.get("timezone") or ctx.tz)
        if partial and "cron" not in body:
            cron = (ctx.store.get_schedule(body["_id"]) or {}).get("cron", "")
        try:
            make_trigger(cron, tz)
        except ValueError as exc:
            raise ApiError(400, "invalid_cron", str(exc)) from None
        out.update(cron=cron, timezone=tz)
    if "window_mode" in body:
        if body["window_mode"] not in ("since_last", "fixed_hours"):
            raise ApiError(400, "invalid_window_mode", "window_mode 只能是 since_last 或 fixed_hours")
        out["window_mode"] = body["window_mode"]
    if "window_hours" in body:
        h = body["window_hours"]
        if not isinstance(h, (int, float)) or not 1 <= h <= 744:
            raise ApiError(400, "invalid_window", "window_hours 必须在 1~744 之间")
        out["window_hours"] = int(h)
    if "platforms" in body:
        ps = _str_list(body["platforms"], "platforms")
        if [p for p in ps if p not in LIVE_PLATFORMS]:
            raise ApiError(400, "invalid_platform", "platforms 只能包含 wechat / qq / feishu")
        out["platforms"] = ps
    if "group_keys" in body:
        out["group_keys"] = _str_list(body["group_keys"], "group_keys")
    if "channel_ids" in body:
        ids = _str_list(body["channel_ids"], "channel_ids")
        known = {c["id"] for c in ctx.store.list_channels()}
        missing = [i for i in ids if i not in known]
        if missing:
            raise ApiError(400, "unknown_channel", f"通道不存在：{'、'.join(missing)}")
        out["channel_ids"] = ids
    if "top_n" in body:
        n = body["top_n"]
        if not isinstance(n, int) or not 1 <= n <= 20:
            raise ApiError(400, "invalid_top_n", "top_n 必须是 1~20 的整数")
        out["top_n"] = n
    for k in ("enabled", "dry_run"):
        if k in body:
            out[k] = bool(body[k])
    return out


@router.get("/schedules")
def list_schedules(ctx: AppContext = Depends(get_ctx)) -> list[dict[str, Any]]:
    return [_schedule_out(ctx, s) for s in ctx.store.list_schedules()]


@router.post("/schedules")
async def create_schedule(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    data = _validate_schedule(ctx, await json_body(request), partial=False)
    data.setdefault("platforms", list(LIVE_PLATFORMS))
    s = ctx.store.create_schedule(f"sch_{secrets.token_hex(4)}", data)
    if ctx.scheduler:
        ctx.scheduler.reload()
    return _schedule_out(ctx, s)


@router.put("/schedules/{sid}")
async def update_schedule(sid: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    if ctx.store.get_schedule(sid) is None:
        raise ApiError(404, "schedule_not_found", f"定时任务不存在：{sid}")
    body = await json_body(request)
    body["_id"] = sid
    s = ctx.store.update_schedule(sid, _validate_schedule(ctx, body, partial=True))
    if ctx.scheduler:
        ctx.scheduler.reload()
    return _schedule_out(ctx, s)  # type: ignore[arg-type]


@router.delete("/schedules/{sid}")
def delete_schedule(sid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    if not ctx.store.delete_schedule(sid):
        raise ApiError(404, "schedule_not_found", f"定时任务不存在：{sid}")
    if ctx.scheduler:
        ctx.scheduler.reload()
    return {"ok": True}


@router.post("/schedules/{sid}/run")
async def run_schedule(sid: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> JSONResponse:
    s = ctx.store.get_schedule(sid)
    if s is None:
        raise ApiError(404, "schedule_not_found", f"定时任务不存在：{sid}")
    body = await json_body(request)
    dry = bool(body["dry_run"]) if "dry_run" in body else bool(s["dry_run"])
    req = RunRequest(trigger="manual", schedule_id=sid, platforms=s["platforms"], group_keys=s["group_keys"],
                     channel_ids=s["channel_ids"], window_hours=s["window_hours"], window_mode=s["window_mode"],
                     dry_run=dry, top_n=s["top_n"], demo=ctx.mode() == "demo")
    return await start_run(ctx, req)
