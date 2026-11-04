"""会话、存活、大屏、SSE、日志、体检。"""

from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse

from bureau import __version__
from bureau.api.deps import get_ctx
from bureau.api.overview import overview
from bureau.core.app import AppContext
from bureau.core.logging import recent_logs
from bureau.core.timeutil import iso

router = APIRouter(prefix="/api")
HEARTBEAT_SEC = 15.0


@router.get("/session")
def session(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return {"token": ctx.config.token, "version": __version__, "mode": ctx.mode()}


@router.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "version": __version__}


@router.get("/overview")
async def get_overview(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return await overview(ctx)


def sse_format(event: str, data: Any) -> str:
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event}\ndata: {payload}\n\n"


@router.get("/events")
async def events(request: Request, ctx: AppContext = Depends(get_ctx)) -> StreamingResponse:
    sub = ctx.bus.subscribe()
    heartbeat = float(getattr(request.app.state, "heartbeat_sec", HEARTBEAT_SEC))

    async def stream() -> AsyncIterator[str]:
        try:
            yield ": connected\n\n"
            yield sse_format("hello", {"server_time": iso(ctx.now(), ctx.tz), "mode": ctx.mode()})
            while True:
                ev = await sub.get(timeout=heartbeat)
                if await request.is_disconnected():
                    break
                if ev is None:
                    yield sse_format("heartbeat", {"server_time": iso(ctx.now(), ctx.tz)})
                else:
                    yield sse_format(ev.type, ev.data)
        except asyncio.CancelledError:
            pass
        finally:
            sub.close()

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"})


@router.get("/logs")
def logs(level: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
    return recent_logs(level, max(1, min(limit, 2000)))


@router.get("/doctor")
async def doctor(ctx: AppContext = Depends(get_ctx)) -> list[dict[str, Any]]:
    from bureau.core.doctor import run_checks

    return await run_checks(ctx)
