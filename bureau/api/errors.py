"""统一错误格式：{"error": {"code", "message", "hint"}}。"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

_DEFAULT_MSG = {400: "请求参数不正确", 401: "未授权", 403: "禁止访问", 404: "资源不存在", 405: "不支持的请求方法",
                409: "冲突", 413: "请求体过大", 422: "请求参数不正确", 500: "服务器内部错误", 501: "功能未实现",
                502: "上游服务出错", 503: "服务暂不可用"}


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, hint: str | None = None) -> None:
        super().__init__(message)
        self.status, self.code, self.message, self.hint = status, code, message, hint


def error_body(code: str, message: str, hint: str | None = None) -> dict[str, Any]:
    err: dict[str, Any] = {"code": code, "message": message}
    if hint:
        err["hint"] = hint
    return {"error": err}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message, exc.hint), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        msg = exc.detail if isinstance(exc.detail, str) and exc.detail and not exc.detail.isascii() else \
            _DEFAULT_MSG.get(exc.status_code, "请求失败")
        return JSONResponse(error_body(f"http_{exc.status_code}", msg), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        errs = exc.errors()
        hint = None
        if errs:
            first = errs[0]
            hint = f"字段 {'.'.join(str(x) for x in first.get('loc', [])[1:]) or '请求体'}：{first.get('msg', '')}"
        return JSONResponse(error_body("invalid_request", "请求参数不正确", hint), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        import logging

        logging.getLogger("bureau.api").exception("未处理的异常：%s", exc)
        return JSONResponse(error_body("internal_error", "服务器内部错误", "查看 data/logs/bureau.log"), status_code=500)
