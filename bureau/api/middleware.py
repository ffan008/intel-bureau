"""安全中间件（纯 ASGI，不缓冲 SSE）：Host 校验（防 DNS 重绑定）、令牌校验、安全响应头。"""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import parse_qs

from bureau.api.errors import error_body
from bureau.core.security import host_allowed, token_ok

PUBLIC_API = {"/api/session", "/api/health", "/api/ingest/onebot"}
CSP = "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; font-src 'self' data:"
SECURITY_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"content-security-policy", CSP.encode()),
]


def _query_token_allowed(path: str, method: str) -> bool:
    """SSE 用 ?token=；报告导出和报告图片（<img src> 无法带请求头）也允许。"""
    if method not in ("GET", "HEAD"):
        return False
    if path == "/api/events":
        return True
    parts = path.split("/")
    # /api/reports/{id}/export  ·  /api/reports/{id}/assets/{name}
    return len(parts) >= 5 and parts[1:3] == ["api", "reports"] and (
        (len(parts) == 5 and parts[4] == "export") or (len(parts) == 6 and parts[4] == "assets"))


class SecurityMiddleware:
    def __init__(self, app: Any, *, ctx: Any) -> None:
        self.app = app
        self.ctx = ctx

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers") or []}
        extra = self.ctx.config.get("app.allowed_hosts", []) or []
        if not host_allowed(headers.get("host"), self.ctx.port, extra):
            await self._reject(send, 403, "host_not_allowed", "不允许的 Host 头",
                               f"请通过 http://127.0.0.1:{self.ctx.port} 访问工作台")
            return
        path: str = scope.get("path", "")
        if path.startswith("/api/") and path not in PUBLIC_API:
            provided = headers.get("x-bureau-token")
            if not provided and _query_token_allowed(path, scope.get("method", "GET")):
                qs = parse_qs(scope.get("query_string", b"").decode("latin-1"))
                provided = (qs.get("token") or [None])[0]
            if not token_ok(provided, self.ctx.config.token):
                await self._reject(send, 401, "unauthorized", "缺少或错误的访问令牌",
                                   "先请求 GET /api/session 获取 token，再在请求头 X-Bureau-Token 里带上")
                return

        async def send_wrapper(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start":
                hs = list(message.get("headers") or [])
                names = {k.lower() for k, _ in hs}
                hs += [(k, v) for k, v in SECURITY_HEADERS if k not in names]
                if path.startswith("/api/") and b"cache-control" not in names:
                    hs.append((b"cache-control", b"no-store"))
                message["headers"] = hs
            await send(message)

        await self.app(scope, receive, send_wrapper)

    @staticmethod
    async def _reject(send: Any, status: int, code: str, message: str, hint: str) -> None:
        body = json.dumps(error_body(code, message, hint), ensure_ascii=False).encode("utf-8")
        await send({"type": "http.response.start", "status": status,
                    "headers": [(b"content-type", b"application/json; charset=utf-8"),
                                (b"content-length", str(len(body)).encode()), *SECURITY_HEADERS]})
        await send({"type": "http.response.body", "body": body})
