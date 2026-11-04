"""集成测试共用：假 HTTP（httpx.MockTransport）、假 lark-cli、上下文与样例报告。"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import httpx

from bureau.channels.base import ChannelContext
from bureau.collectors.base import CollectorContext
from bureau.contracts import Platform, ReportPayload

TZ8 = timezone(timedelta(hours=8))


def run(coro):
    return asyncio.run(coro)


def dt(s: str) -> datetime:
    """'2026-10-25 18:14' → 带 +08:00 时区的 datetime。"""
    return datetime.fromisoformat(s).replace(tzinfo=TZ8)


def ts(s: str) -> int:
    return int(dt(s).timestamp())


def collector_ctx(tmp_path: Path, platform: str, settings: dict | None = None,
                  secrets: dict | None = None) -> CollectorContext:
    return CollectorContext(platform=Platform(platform), settings=settings or {}, secrets=secrets or {},
                            data_dir=Path(tmp_path), logger=logging.getLogger("test.collector"))


def channel_ctx(tmp_path: Path, settings: dict | None = None, secrets: dict | None = None,
                channel_id: str = "ch-test") -> ChannelContext:
    return ChannelContext(channel_id=channel_id, name="测试通道", settings=settings or {}, secrets=secrets or {},
                          data_dir=Path(tmp_path), logger=logging.getLogger("test.channel"))


def make_report(**kw: Any) -> ReportPayload:
    base = dict(report_id="r-20261028", run_id="run-1", title="情报局 · 每日风向标 | 2026-10-28（周三）",
                date_label="2026-10-28", window_label="10-27 08:00 ~ 10-28 08:00",
                summary_md="## 今日风向\n- 一条判断\n- 另一条判断", summary_text="今日风向：\n1. 一条判断\n2. 另一条判断",
                full_md="# 完整报告\n\n正文……", dashboard_url="http://127.0.0.1:8765/#/reports/r-20261028")
    base.update(kw)
    return ReportPayload(**base)


class MockHTTP:
    """把 handler 包成 MockTransport，并记录收到的每个请求。"""

    def __init__(self, handler: Callable[[httpx.Request], httpx.Response]) -> None:
        self.requests: list[httpx.Request] = []
        self._handler = handler
        self.transport = httpx.MockTransport(self._handle)

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._handler(request)

    def body(self, i: int = -1) -> Any:
        return json.loads(self.requests[i].content.decode("utf-8"))


def ok_json(data: Any, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=data)


def refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("连接被拒绝", request=request)


class FakeLark:
    """假 lark-cli 运行器：按参数前缀返回预设输出，并记录每次调用的参数、cwd 和 cwd 里的 .md 文件内容。"""

    def __init__(self, routes: list[tuple[tuple[str, ...], Any]]) -> None:
        # routes: [(参数前缀, 响应)]；响应为 (退出码, stdout, stderr) 或 dict（成功信封的 data）或可调用对象
        self.routes = routes
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, argv, timeout, cwd, env):
        args = list(argv[1:])
        files = {}
        if cwd:
            files = {p.name: p.read_text("utf-8") for p in Path(cwd).glob("*.md")}
        self.calls.append({"args": args, "cwd": cwd, "files": files, "timeout": timeout})
        for prefix, resp in self.routes:
            if tuple(args[: len(prefix)]) == prefix:
                if callable(resp):
                    resp = resp(args)
                if isinstance(resp, BaseException):
                    raise resp
                if isinstance(resp, tuple):
                    return resp
                return 0, json.dumps({"ok": True, "identity": "bot", "data": resp}, ensure_ascii=False), ""
        return 1, "", "unknown command"


def lark_error(etype: str, message: str, *, subtype: str = "", code: int | None = None, identity: str = "user",
               exit_code: int = 1, **extra: Any) -> tuple[int, str, str]:
    err = {"type": etype, "subtype": subtype, "message": message, **extra}
    if code is not None:
        err["code"] = code
    return exit_code, "", json.dumps({"ok": False, "identity": identity, "error": err}, ensure_ascii=False)


def auth_status(user_status: str = "ready", bot_status: str = "ready", user_msg: str = "",
                scope: str = "im:chat:read im:message.group_msg:get_as_user") -> tuple[int, str, str]:
    doc = {"appId": "cli_test", "identity": "bot", "identities": {
        "bot": {"status": bot_status, "available": bot_status == "ready", "message": f"Bot identity: {bot_status}"},
        "user": {"status": user_status, "available": user_status == "ready",
                 "message": user_msg or f"User identity: {user_status}", "userName": "测试用户",
                 "openId": "ou_test", "tokenStatus": "valid" if user_status == "ready" else "expired",
                 "scope": scope}}}
    return 0, json.dumps(doc, ensure_ascii=False), ""