"""v2 测试公共部分：一次跑完的演示运行（模块级复用）、假的 B2 研究模块、假的云端模型。"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bureau.pipeline import b2

# 演示数据里虚构的、带个人手机号的隐私消息（bureau/demo/threads_v2.py privacy_doxx）
PRIVACY_PHONE = "13800138000"
PRIVACY_MARK = "滨江区某某小区"


def make_demo_app(base: Path, **settings: Any) -> Any:
    """独立的 data / config 目录；OCR 关闭（Windows OCR 慢且依赖本机组件），模型固定离线。"""
    from bureau.core.app import AppContext
    from bureau.demo import seed_demo
    from tests.conftest import make_paths

    app = AppContext(make_paths(base))
    patch = {"media": {"ocr": "off"}, "llm": {"provider": "offline"}}
    for k, v in settings.items():
        patch.setdefault(k, {}).update(v)
    app.config.update_settings(patch)
    seed_demo(app, scale=0.35)
    return app


def run_demo(app: Any, **kw: Any) -> dict[str, Any]:
    from bureau.pipeline.runner import RunRequest

    return asyncio.run(app.runner.run(RunRequest(demo=True, dry_run=kw.pop("dry_run", True), **kw)))


def html_of(app: Any, report: dict[str, Any]) -> str:
    return Path(report["files"]["html"]).read_text(encoding="utf-8")


# ---------------- 假的 bureau.research（签名按 docs/V2_KNOWLEDGE.md §5） ----------------
@dataclass
class FakeCtx:
    settings: dict
    secrets: dict
    data_dir: Path
    max_searches: int
    max_fetches: int
    used_searches: int = 0
    used_fetches: int = 0
    cost_usd: float = 0.0
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("test.research"))


def fake_research_module(queries: list[str]) -> types.ModuleType:
    from pydantic import BaseModel

    class Hit(BaseModel):
        title: str
        url: str
        summary: str = ""
        content: str | None = None
        site: str | None = None

    class Page(BaseModel):
        url: str
        title: str | None = None
        markdown: str
        ok: bool = True

    class Meta(BaseModel):
        url: str
        kind: str
        title: str | None = None
        description: str | None = None
        meta: dict = {}
        code: str | None = None
        ok: bool = True

    async def web_search(ctx: FakeCtx, query: str, *, count: int = 5) -> list[Hit]:
        queries.append(query)
        ctx.used_searches += 1
        ctx.cost_usd += 0.01
        n = len(queries)
        return [Hit(title=f"公开资料 {n}", url=f"https://example.org/doc/{n}", summary="官方文档说明了参数的含义。")]

    async def fetch_page(ctx: FakeCtx, url: str, *, max_chars: int = 12000) -> Page:
        ctx.used_fetches += 1
        return Page(url=url, title="公开资料", markdown="官方文档：推荐分辨率 1024，步数 20。")

    async def enrich_link(ctx: FakeCtx, url: str, *, context_text: str = "") -> Meta:
        kind = "github" if "github.com" in url else "web"
        return Meta(url=url, kind=kind, title="假的标题" if kind == "github" else None,
                    meta={"stars": 1234, "language": "Python"} if kind == "github" else {},
                    code="zzzz")                   # 原文里没有的提取码：必须被丢弃

    def classify_link(url: str) -> str:
        return "github" if "github.com" in url else "web"

    mod = types.ModuleType("bureau.research")
    mod.ResearchContext = FakeCtx               # type: ignore[attr-defined]
    mod.web_search, mod.fetch_page = web_search, fetch_page                # type: ignore[attr-defined]
    mod.enrich_link, mod.classify_link = enrich_link, classify_link        # type: ignore[attr-defined]
    return mod


def install_module(monkeypatch: Any, name: str, mod: Any) -> None:
    """注入（或用 None 屏蔽）B2 的模块，并清掉懒加载缓存。"""
    monkeypatch.setitem(sys.modules, name, mod)
    b2.reset()


class FakeCloud:
    """假的云端模型：按 task 返回合格的 JSON；不发任何网络请求。"""
    name, label, model, concurrency, is_cloud = "openai_compat", "假模型", "fake-1", 2, True

    def __init__(self) -> None:
        self.tasks: list[str] = []

    async def complete_json(self, system: str, user: str, schema: Any = None, **kw: Any) -> Any:
        task = kw.get("task")
        self.tasks.append(task)
        if task == "research_queries":
            parsed: Any = {"plans": []}               # 让代码按话题和工具名拼检索词
        elif task == "article":
            parsed = {"title": "", "hook": "群友实测的做法", "background": ["群内讨论了具体做法。"],
                      "quote_msgs": [], "practice": ["按群内步骤操作"],
                      "research": [{"text": "公开资料说明了参数含义", "refs": [1]}], "scope": "适合个人创作者",
                      "cost": "", "risk_note": "", "media_notes": []}
        elif task == "digest":
            parsed = {"overview": {"summary": "今天主要在聊做法和工具", "trends": []}, "groups": []}
        else:
            parsed = {"items": [], "noise_ratio": 1.0}
        return types.SimpleNamespace(parsed=parsed, text="", usage={"input_tokens": 10, "output_tokens": 5},
                                     cost=0.0, model="fake-1")
