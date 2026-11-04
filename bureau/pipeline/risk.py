"""v2 风险策略（docs/V2_KNOWLEDGE.md §2）。

- label（新默认）：只标注、附免责声明，不扣分；带风险标签的条目照常进头条和专题。
- flag（v1 行为，兼容旧配置）：按 pipeline.risk_penalty 扣分，合规 / 账号 / 金钱 / 广告引流类不进头条和专题。
- drop：直接剔除带严重风险标签的条目。
不论哪种策略：「违法高危」只进风险板块，不成为专题、不做联网扩展、不写步骤；「隐私」整条剔除并计数。
"""

from __future__ import annotations

from typing import Any

from bureau.core.constants import (RISK_FLAGS_V2, RISK_ILLEGAL, RISK_POLICIES, SERIOUS_RISKS, SERIOUS_RISKS_V2)
from bureau.pipeline.models import Item, RunContext


def policy_of(rc: RunContext) -> str:
    p = str(rc.cfg("pipeline.risk_policy", "label") or "label").strip().lower()
    return p if p in RISK_POLICIES else "label"


def penalty_of(rc: RunContext, policy: str) -> float:
    """label 下不扣分（不管 risk_penalty 写了多少）；flag 下按配置扣分。"""
    if policy != "flag":
        return 0.0
    try:
        return max(0.0, float(rc.cfg("pipeline.risk_penalty", 0) or 0))
    except (TypeError, ValueError):
        return 0.0


def is_illegal(it: Any) -> bool:
    return RISK_ILLEGAL in (it.risk_flags or [])


def blocks_feature(it: Item, policy: str) -> bool:
    """不能进头条和专题：违法高危永远不能；flag 策略下沿用 v1 的四类严重风险。"""
    if is_illegal(it):
        return True
    return policy == "flag" and bool(set(it.risk_flags) & SERIOUS_RISKS)


def dropped_by_policy(it: Item, policy: str) -> bool:
    return policy == "drop" and bool(set(it.risk_flags) & SERIOUS_RISKS_V2)


def has_risk(flags: list[str]) -> bool:
    return any(f in RISK_FLAGS_V2 for f in flags or [])


def sanitize_illegal(it: Item) -> None:
    """违法高危：只保留要点和群内原话（记录在讨论什么），去掉步骤、链接、提示词、媒体等可照做的内容。"""
    it.steps, it.sop_steps, it.links, it.prompts = [], [], [], []
    it.media_refs, it.tool_notes, it.data_points, it.quotes = [], [], [], []
    for p in it.points:
        p["steps"] = []
