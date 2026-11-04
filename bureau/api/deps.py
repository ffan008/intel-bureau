"""路由依赖与小工具。"""

from __future__ import annotations

from typing import Any

from fastapi import Request

from bureau.api.errors import ApiError
from bureau.core.app import AppContext


def get_ctx(request: Request) -> AppContext:
    return request.app.state.ctx


async def json_body(request: Request) -> dict[str, Any]:
    """读取 JSON 对象请求体；空请求体返回 {}。"""
    raw = await request.body()
    if not raw.strip():
        return {}
    import json

    try:
        data = json.loads(raw)
    except ValueError:
        raise ApiError(400, "invalid_json", "请求体不是合法的 JSON") from None
    if not isinstance(data, dict):
        raise ApiError(400, "invalid_json", "请求体必须是 JSON 对象")
    return data


def as_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("1", "true", "yes", "on")


def page(limit: int | None, offset: int | None, default: int = 20, cap: int = 500) -> tuple[int, int]:
    lim = default if limit is None else max(1, min(int(limit), cap))
    return lim, max(0, int(offset or 0))
