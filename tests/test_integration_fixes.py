"""联调时补的检查：设置防泄密、单次费用上限、大屏演示节奏。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from bureau.api.errors import ApiError
from bureau.api.routes_config import apply_settings
from bureau.core.taxonomy import load_taxonomy
from bureau.llm.cache import LLMCache
from bureau.pipeline.extract import extract_chunk
from bureau.pipeline.models import RunContext
from bureau.pipeline.runner import RunRequest

TZ = ZoneInfo("Asia/Shanghai")


# ---------- 设置：密钥不能落进 settings.yaml ----------

def test_settings_rejects_secret_in_wrong_place(app):
    with pytest.raises(ApiError) as e:
        apply_settings(app, {"llm": {"providers": {"openai_compat": {"api_key": "sk-should-not-leak"}}}})
    assert e.value.status == 400
    with pytest.raises(ApiError) as e:
        apply_settings(app, {"pipeline": {"token": "abc123"}})
    assert e.value.code == "secret_in_settings"
    assert "sk-should-not-leak" not in app.paths.settings.read_text(encoding="utf-8")
    assert "abc123" not in app.paths.settings.read_text(encoding="utf-8")


def test_settings_accepts_provider_key_into_secrets(app):
    apply_settings(app, {"llm": {"provider": "openai_compat", "max_tokens": 2048, "max_cost_cny": 3,
                                 "openai_compat": {"preset": "deepseek", "api_key": "sk-real-key-1234"}}})
    assert "sk-real-key-1234" not in app.paths.settings.read_text(encoding="utf-8")
    assert app.config.secret("llm.openai_compat.api_key") == "sk-real-key-1234"
    assert app.config.get("llm.max_cost_cny") == 3
    # 回传掩码表示不修改
    apply_settings(app, {"llm": {"openai_compat": {"api_key": "••••1234"}}})
    assert app.config.secret("llm.openai_compat.api_key") == "sk-real-key-1234"
    with pytest.raises(ApiError):
        apply_settings(app, {"llm": {"max_cost_cny": -1}})


# ---------- 单次费用上限 ----------

class _Log:
    def __init__(self) -> None:
        self.warns: list[str] = []

    def warn(self, _agent: str, msg: str, *_a) -> None:
        self.warns.append(msg)

    def info(self, *_a) -> None:
        pass


def _rc(app, cost: float, cap: float) -> RunContext:
    settings = dict(app.config.settings)
    settings["llm"] = {**settings.get("llm", {}), "max_cost_cny": cap}
    now = datetime(2026, 10, 28, 8, 0, tzinfo=TZ)
    rc = RunContext(app=app, run_id="t", trigger="manual", schedule_id=None, dry_run=True, demo=True,
                    start=now - timedelta(hours=24), end=now, platforms=[], group_keys=[], channel_ids=None,
                    top_n=5, settings=settings, log=_Log())  # type: ignore[arg-type]
    rc.totals = {"cost_cny": cost}
    return rc


class _Cloud:
    name, model, concurrency = "openai_compat", "m", 1

    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, *_a, **_k):
        self.calls += 1
        return SimpleNamespace(parsed={"items": [], "noise_ratio": 0.5}, text="", usage={"input_tokens": 10,
                               "output_tokens": 5}, cost=0.01, model="m")


class _Offline:
    name = "offline"

    async def complete_json(self, *_a, **_k):
        return SimpleNamespace(parsed={"items": [], "noise_ratio": 1.0})


def _chunk():
    return SimpleNamespace(id="c1", group_key="wechat:demo-x", group_name="测试群", platform="wechat",
                           text="头\n[m1] 08:00 张三：你好", msgs=[], route="llm")


def test_budget_cap_falls_back_to_offline(app):
    tax = load_taxonomy(app.paths.taxonomy)
    cache = LLMCache(app.paths.llm_cache, enabled=False)
    cloud = _Cloud()
    rc = _rc(app, cost=5.0, cap=5.0)                      # 已经用满
    out, used, _ = asyncio.run(extract_chunk(rc, _chunk(), cloud, _Offline(), cache, asyncio.Semaphore(1), tax))
    assert used == "offline" and cloud.calls == 0
    assert rc.budget_capped == 1 and len(rc.log.warns) == 1
    asyncio.run(extract_chunk(rc, _chunk(), cloud, _Offline(), cache, asyncio.Semaphore(1), tax))
    assert rc.budget_capped == 2 and len(rc.log.warns) == 1   # 只告警一次

    rc2 = _rc(app, cost=1.0, cap=5.0)                     # 还没到上限
    _, used2, _ = asyncio.run(extract_chunk(rc2, _chunk(), cloud, _Offline(), cache, asyncio.Semaphore(1), tax))
    assert used2 == "openai_compat" and cloud.calls == 1

    rc3 = _rc(app, cost=99.0, cap=0)                      # 0 表示不限
    _, used3, _ = asyncio.run(extract_chunk(rc3, _chunk(), cloud, _Offline(), cache, asyncio.Semaphore(1), tax))
    assert used3 == "openai_compat"


# ---------- 大屏演示运行的节奏 ----------

def test_background_demo_run_is_paced_but_cli_run_is_not(demo_app, monkeypatch):
    monkeypatch.setenv("BUREAU_DEMO_PACE_MS", "250")

    async def background() -> list[dict]:
        dto = await demo_app.runner.start(RunRequest(demo=True, dry_run=True))
        assert await demo_app.runner.wait_idle(timeout=120)
        return demo_app.store.get_stages(dto["id"])

    stages = asyncio.run(background())
    done = [s for s in stages if s["status"] == "done"]
    assert len(done) == 12
    assert all((s["duration_ms"] or 0) >= 240 for s in done), [(s["name"], s["duration_ms"]) for s in done]

    # 命令行 / 测试直接 await 的运行不放慢；真实（非演示）运行也不放慢。直接看节奏函数，不依赖耗时
    runner = demo_app.runner
    demo_rc = SimpleNamespace(demo=True, cfg=lambda _k, d=None: d)
    live_rc = SimpleNamespace(demo=False, cfg=lambda _k, d=None: d)
    runner._background = False
    assert runner._pace_ms(demo_rc) == 0
    runner._background = True
    assert runner._pace_ms(demo_rc) == 250
    assert runner._pace_ms(live_rc) == 0
    monkeypatch.setenv("BUREAU_DEMO_PACE_MS", "0")
    assert runner._pace_ms(demo_rc) == 0
