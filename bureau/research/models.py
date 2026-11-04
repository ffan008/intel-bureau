"""research 的数据类型（签名按 docs/V2_KNOWLEDGE.md §5，不要改动字段顺序）。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

from bureau.integrations.netsafe import Resolver

LinkKind = Literal["github", "x", "wechat_article", "netdisk", "video", "doc", "web", "other"]


@dataclass
class ResearchContext:
    """一次运行共用的研究上下文。

    - settings：完整的 settings（含 ``research`` 与 ``privacy`` 两节）；只传 ``research`` 一节也能用，
      但那样就读不到 ``privacy.cloud_llm_consent``，联网搜索会被视为未同意而跳过。
    - secrets：完整的 secrets（读 ``research.deepseek_api_key`` / ``research.github_token`` /
      ``llm.openai_compat.api_key``）。
    - data_dir：缓存写在 ``data_dir/cache/research|enrich/``。
    - used_* / cost_usd 由本模块累加，调用方读取即可。
    - transport / resolver 只给测试注入（httpx.MockTransport 与假 DNS），生产代码不要传。
    """
    settings: dict
    secrets: dict
    data_dir: Path
    max_searches: int
    max_fetches: int
    used_searches: int = 0
    used_fetches: int = 0
    cost_usd: float = 0.0
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("bureau.research"))
    transport: httpx.AsyncBaseTransport | None = field(default=None, repr=False)
    resolver: Resolver | None = field(default=None, repr=False)
    down_hosts: set[str] = field(default_factory=set, repr=False)   # 本次运行中已超时 / 连不上的主机，之后直接跳过


class SearchHit(BaseModel):
    title: str
    url: str
    summary: str = ""
    content: str | None = None
    site: str | None = None
    published_at: str | None = None


class PageContent(BaseModel):
    url: str
    title: str | None
    markdown: str
    ok: bool
    error: str | None = None


class LinkMeta(BaseModel):
    url: str
    kind: LinkKind
    title: str | None = None
    description: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    code: str | None = None
    ok: bool = True
    error: str | None = None
