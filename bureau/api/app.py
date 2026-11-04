"""create_app()：中间件、全部路由、SSE、静态托管 web/dist（SPA 回退）；没有 dist 时 / 返回中文提示页。"""

from __future__ import annotations

import asyncio
import logging
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, Response

from bureau import __version__
from bureau.api import routes_config, routes_core, routes_kb, routes_reports, routes_runs, routes_sources
from bureau.api.errors import ApiError, install_error_handlers
from bureau.api.middleware import SecurityMiddleware
from bureau.core.app import AppContext

log = logging.getLogger("bureau.api")
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("font/woff2", ".woff2")

PLACEHOLDER = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>情报局工作台</title>
<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;background:#03060f;
color:#eaf6ff;font-family:"Microsoft YaHei UI","PingFang SC",sans-serif}.box{max-width:620px;padding:32px 36px;
border:1px solid rgba(80,200,255,.3);background:rgba(10,22,46,.6)}h1{margin:0 0 12px;font-size:22px;color:#22e4ff}
code{background:#0a1428;padding:2px 6px;color:#2bff9a}p{line-height:1.8;color:#a9c4dd}</style></head><body><div class="box">
<h1>情报局工作台 · 服务已启动</h1><p>后端接口运行正常，但还没有构建前端界面（找不到 <code>web/dist</code>）。</p>
<p>在项目目录运行 <code>scripts/setup.sh</code>（macOS）或 <code>scripts\\setup.ps1</code>（Windows），
或进入 <code>web</code> 目录执行 <code>npm ci</code> 和
<code>npm run build</code>，完成后刷新本页。</p><p>接口自检：<code>GET /api/health</code>；体检：<code>python -m bureau doctor</code>。</p>
</div></body></html>"""


def create_app(ctx: AppContext | None = None, *, background: bool = True) -> FastAPI:
    """background=False 时不启动调度器和健康检查（测试用）。"""
    ctx = ctx or AppContext()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        tasks: list[asyncio.Task[Any]] = []
        lock_free = ctx.runner._lock.acquire()          # 另一个进程在跑流水线时，不要把它的运行标成失败
        if lock_free:
            ctx.runner._lock.release()
            n = ctx.store.mark_stale_runs()
            if n:
                log.warning("有 %s 个运行在上次退出时被中断，已标为失败", n)
        if background:
            from bureau.core.platforms import health_loop
            from bureau.scheduler import BureauScheduler

            ctx.scheduler = BureauScheduler(ctx)
            ctx.scheduler.start()
            tasks.append(asyncio.create_task(ctx.scheduler.catch_up(), name="catchup"))
            tasks.append(asyncio.create_task(health_loop(ctx, float(ctx.config.get("app.health_interval_sec", 300))),
                                             name="health"))
        log.info("工作台 %s 已启动：http://127.0.0.1:%s", __version__, ctx.port)
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            if ctx.scheduler is not None:
                ctx.scheduler.shutdown()
                ctx.scheduler = None
            if ctx.runner.busy and ctx.runner.current_run_id:
                ctx.runner.cancel(ctx.runner.current_run_id)
                await ctx.runner.wait_idle(timeout=5)

    app = FastAPI(title="情报局工作台", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,
                  lifespan=lifespan)
    app.state.ctx = ctx
    install_error_handlers(app)
    for r in (routes_core, routes_sources, routes_runs, routes_reports, routes_config, routes_kb):
        app.include_router(r.router)
    app.add_middleware(SecurityMiddleware, ctx=ctx)
    mount_spa(app, ctx.paths.web_dist)
    return app


def mount_spa(app: FastAPI, dist: Path) -> None:
    @app.api_route("/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def spa(full_path: str, request: Request) -> Response:
        if full_path == "api" or full_path.startswith("api/"):
            raise ApiError(404, "not_found", f"接口不存在：/{full_path}")
        index = dist / "index.html"
        if not index.is_file():
            return HTMLResponse(PLACEHOLDER)
        if full_path:
            target = (dist / full_path).resolve()
            try:
                target.relative_to(dist.resolve())
            except ValueError:
                raise ApiError(404, "not_found", "文件不存在") from None
            if target.is_file():
                cache = "public, max-age=31536000, immutable" if "/assets/" in f"/{full_path}" else "no-cache"
                return FileResponse(target, headers={"Cache-Control": cache})
            if "." in full_path.rsplit("/", 1)[-1]:      # 缺失的静态资源返回 404，不回退到 index
                raise ApiError(404, "not_found", "文件不存在")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
