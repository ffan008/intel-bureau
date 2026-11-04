"""安全网：本目录的测试不得启动真实子进程（lark-cli）或发出未经 MockTransport 的 HTTP 请求。

推送通道的测试如果漏注入假实现，会直接失败，而不是真的给账号发消息。
"""

from __future__ import annotations

import subprocess

import httpx
import pytest


@pytest.fixture(autouse=True)
def _no_real_side_effects(monkeypatch):
    def no_subprocess(*args, **kwargs):
        raise AssertionError(f"测试试图启动真实子进程：{args[0] if args else kwargs}")

    monkeypatch.setattr(subprocess, "run", no_subprocess)

    real_init = httpx.AsyncClient.__init__

    def guarded_init(self, *args, **kwargs):
        if kwargs.get("transport") is None:
            raise AssertionError("测试试图发出真实 HTTP 请求（没有注入 MockTransport）")
        real_init(self, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "__init__", guarded_init)
    yield
