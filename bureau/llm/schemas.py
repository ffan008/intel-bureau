"""大模型输出的 pydantic 校验与 JSON Schema（§11）。校验时尽量纠正（截断、夹到 0~5），结构错误才判失败。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _M(BaseModel):
    model_config = ConfigDict(extra="ignore")


class LinkOut(_M):
    url: str
    title: str = ""


class EvidenceOut(_M):
    msg: str
    quote: str


class ScoresOut(_M):
    novelty: float = 0.0
    actionability: float = 0.0
    credibility: float = 0.0

    @field_validator("novelty", "actionability", "credibility", mode="before")
    @classmethod
    def _clamp(cls, v: Any) -> float:
        try:
            return max(0.0, min(5.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


def _str_list(v: Any, limit: int = 20) -> list[str]:
    if v is None:
        return []
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in v if str(x).strip()][:limit]


class ExtractItem(_M):
    title: str = Field(min_length=2)
    hook: str = ""
    summary: str = ""
    category: str = ""
    kind: str = ""
    steps: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    links: list[LinkOut] = Field(default_factory=list)
    evidence: list[EvidenceOut] = Field(default_factory=list)
    participants: list[str] = Field(default_factory=list)
    scores: ScoresOut = Field(default_factory=ScoresOut)
    risk_flags: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    refs: list[str] = Field(default_factory=list)      # offline 提取附带的相关消息编号

    @field_validator("title", mode="before")
    @classmethod
    def _title(cls, v: Any) -> str:
        return str(v or "").strip()[:60]

    @field_validator("hook", mode="before")
    @classmethod
    def _hook(cls, v: Any) -> str:
        return str(v or "").strip()[:40]

    @field_validator("summary", mode="before")
    @classmethod
    def _summary(cls, v: Any) -> str:
        return str(v or "").strip()[:600]

    @field_validator("steps", "tools", "participants", "risk_flags", "tags", "refs", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> list[str]:
        return _str_list(v)


class ExtractOut(_M):
    items: list[ExtractItem] = Field(default_factory=list)
    noise_ratio: float = 0.0

    @field_validator("noise_ratio", mode="before")
    @classmethod
    def _ratio(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class Judgment(_M):
    text: str = Field(min_length=2)
    basis: str = ""
    item_ids: list[str] = Field(default_factory=list)


class FeatureOut(_M):
    id: str
    background: str = ""
    practice: list[str] = Field(default_factory=list)
    scope: str = ""

    @field_validator("practice", mode="before")
    @classmethod
    def _practice(cls, v: Any) -> list[str]:
        return _str_list(v, 12)


class ComposeOut(_M):
    judgments: list[Judgment] = Field(min_length=1)
    features: list[FeatureOut] = Field(default_factory=list)


class MergeOut(_M):
    same: bool
    reason: str = ""


_STR = {"type": "string"}
_STR_ARR = {"type": "array", "items": _STR}

EXTRACT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "title": _STR, "hook": _STR, "summary": _STR, "category": _STR, "kind": _STR,
                "steps": _STR_ARR, "tools": _STR_ARR,
                "links": {"type": "array", "items": {"type": "object", "properties": {"url": _STR, "title": _STR},
                                                     "required": ["url"]}},
                "evidence": {"type": "array", "items": {"type": "object", "properties": {"msg": _STR, "quote": _STR},
                                                        "required": ["msg", "quote"]}},
                "participants": _STR_ARR,
                "scores": {"type": "object", "properties": {"novelty": {"type": "number"},
                                                            "actionability": {"type": "number"},
                                                            "credibility": {"type": "number"}}},
                "risk_flags": _STR_ARR, "tags": _STR_ARR,
            },
            "required": ["title", "hook", "summary", "category", "kind", "evidence"],
        }},
        "noise_ratio": {"type": "number"},
    },
    "required": ["items"],
}

COMPOSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "judgments": {"type": "array", "items": {"type": "object", "properties": {
            "text": _STR, "basis": _STR, "item_ids": _STR_ARR}, "required": ["text", "basis"]}},
        "features": {"type": "array", "items": {"type": "object", "properties": {
            "id": _STR, "background": _STR, "practice": _STR_ARR, "scope": _STR}, "required": ["id"]}},
    },
    "required": ["judgments"],
}

MERGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"same": {"type": "boolean"}, "reason": _STR},
    "required": ["same"],
}


# ======================= v2（docs/V2_KNOWLEDGE.md §4） =======================
def _dict_list(v: Any, limit: int = 12) -> list[dict[str, Any]]:
    if not isinstance(v, list):
        return []
    return [x for x in v if isinstance(x, dict)][:limit]


class PromptRef(_M):
    msg: str
    excerpt: str = ""            # 从原文逐字复制的一段（代码按它定位，再从数据库原文截取）
    purpose: str = ""


class DataPoint(_M):
    label: str = ""
    value: str
    unit: str = ""
    msg: str
    self_reported: bool = True

    @field_validator("value", mode="before")
    @classmethod
    def _value(cls, v: Any) -> str:
        return str(v if v is not None else "").strip()[:24]


class QuoteRef(_M):
    msg: str
    quote: str = ""


class ToolNote(_M):
    tool: str
    scene: str = ""
    verdict: str = ""
    msg: str


class MediaRef(_M):
    msg: str
    why: str = ""


class LinkOutV2(_M):
    url: str
    title: str = ""
    kind: str = ""


class ExtractItemV2(ExtractItem):
    topic: str = ""
    sop_steps: list[str] = Field(default_factory=list)
    prompts: list[PromptRef] = Field(default_factory=list)
    data_points: list[DataPoint] = Field(default_factory=list)
    quotes: list[QuoteRef] = Field(default_factory=list)
    tool_notes: list[ToolNote] = Field(default_factory=list)
    media_refs: list[MediaRef] = Field(default_factory=list)
    privacy: bool = False
    links: list[LinkOutV2] = Field(default_factory=list)       # type: ignore[assignment]

    @field_validator("topic", mode="before")
    @classmethod
    def _topic(cls, v: Any) -> str:
        return str(v or "").strip()[:30]

    @field_validator("sop_steps", mode="before")
    @classmethod
    def _sop(cls, v: Any) -> list[str]:
        return _str_list(v, 15)

    @field_validator("prompts", "data_points", "quotes", "tool_notes", "media_refs", mode="before")
    @classmethod
    def _dicts(cls, v: Any, info: Any) -> list[dict[str, Any]]:
        need = {"data_points": ("msg", "value"), "tool_notes": ("msg", "tool")}.get(info.field_name, ("msg",))
        # 单个子项缺字段时只丢这一项，不让整块输出作废
        return [x for x in _dict_list(v) if all(x.get(k) not in (None, "") for k in need)]


class ExtractOutV2(_M):
    items: list[ExtractItemV2] = Field(default_factory=list)
    noise_ratio: float = 0.0

    @field_validator("noise_ratio", mode="before")
    @classmethod
    def _ratio(cls, v: Any) -> float:
        try:
            return max(0.0, min(1.0, float(v)))
        except (TypeError, ValueError):
            return 0.0


class Finding(_M):
    text: str
    refs: list[int] = Field(default_factory=list)       # 对应 research[].n
    conflict: str = ""

    @field_validator("refs", mode="before")
    @classmethod
    def _refs(cls, v: Any) -> list[int]:
        out = []
        for x in v if isinstance(v, list) else [v]:
            try:
                out.append(int(str(x).strip("[] ")))
            except (TypeError, ValueError):
                continue
        return out[:6]


class MediaNote(_M):
    name: str
    note: str = ""


class ArticleOut(_M):
    title: str = ""
    hook: str = ""
    background: list[str] = Field(default_factory=list)
    quote_msgs: list[str] = Field(default_factory=list)
    practice: list[str] = Field(default_factory=list)
    research: list[Finding] = Field(default_factory=list)
    scope: str = ""
    cost: str = ""
    risk_note: str = ""
    media_notes: list[MediaNote] = Field(default_factory=list)

    @field_validator("background", "quote_msgs", "practice", mode="before")
    @classmethod
    def _lists(cls, v: Any) -> list[str]:
        return _str_list(v, 12)

    @field_validator("research", "media_notes", mode="before")
    @classmethod
    def _dl(cls, v: Any) -> list[dict[str, Any]]:
        return _dict_list(v, 10)


class GroupDigestOut(_M):
    group_key: str
    summary: str = ""
    highlights: list[str] = Field(default_factory=list)

    @field_validator("highlights", mode="before")
    @classmethod
    def _hl(cls, v: Any) -> list[str]:
        return _str_list(v, 3)


class DigestOverview(_M):
    summary: str = ""
    trends: list[Judgment] = Field(default_factory=list)


class DigestOut(_M):
    overview: DigestOverview = Field(default_factory=DigestOverview)
    groups: list[GroupDigestOut] = Field(default_factory=list)


class QueryPlan(_M):
    id: str
    queries: list[str] = Field(default_factory=list)

    @field_validator("queries", mode="before")
    @classmethod
    def _q(cls, v: Any) -> list[str]:
        return _str_list(v, 3)


class QueriesOut(_M):
    plans: list[QueryPlan] = Field(default_factory=list)


_OBJ_ARR = {"type": "array", "items": {"type": "object"}}

EXTRACT_V2_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "items": {"type": "array", "items": {
            "type": "object",
            "properties": {
                **EXTRACT_SCHEMA["properties"]["items"]["items"]["properties"],
                "topic": _STR, "sop_steps": _STR_ARR, "privacy": {"type": "boolean"},
                "links": {"type": "array", "items": {"type": "object", "properties": {"url": _STR, "title": _STR,
                                                                                    "kind": _STR}, "required": ["url"]}},
                "prompts": {"type": "array", "items": {"type": "object", "properties": {
                    "msg": _STR, "excerpt": _STR, "purpose": _STR}, "required": ["msg"]}},
                "data_points": {"type": "array", "items": {"type": "object", "properties": {
                    "label": _STR, "value": _STR, "unit": _STR, "msg": _STR, "self_reported": {"type": "boolean"}},
                    "required": ["value", "msg"]}},
                "quotes": {"type": "array", "items": {"type": "object", "properties": {"msg": _STR, "quote": _STR},
                                                      "required": ["msg"]}},
                "tool_notes": {"type": "array", "items": {"type": "object", "properties": {
                    "tool": _STR, "scene": _STR, "verdict": _STR, "msg": _STR}, "required": ["tool", "msg"]}},
                "media_refs": {"type": "array", "items": {"type": "object", "properties": {"msg": _STR, "why": _STR},
                                                          "required": ["msg"]}},
            },
            "required": ["title", "hook", "summary", "category", "kind", "evidence"],
        }},
        "noise_ratio": {"type": "number"},
    },
    "required": ["items"],
}

ARTICLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": _STR, "hook": _STR, "background": _STR_ARR, "quote_msgs": _STR_ARR, "practice": _STR_ARR,
        "research": {"type": "array", "items": {"type": "object", "properties": {
            "text": _STR, "refs": {"type": "array", "items": {"type": "integer"}}, "conflict": _STR}, "required": ["text"]}},
        "scope": _STR, "cost": _STR, "risk_note": _STR,
        "media_notes": {"type": "array", "items": {"type": "object", "properties": {"name": _STR, "note": _STR},
                                                   "required": ["name"]}},
    },
    "required": ["hook", "background", "practice"],
}

DIGEST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "overview": {"type": "object", "properties": {"summary": _STR, "trends": {"type": "array", "items": {
            "type": "object", "properties": {"text": _STR, "basis": _STR, "item_ids": _STR_ARR}, "required": ["text"]}}}},
        "groups": {"type": "array", "items": {"type": "object", "properties": {
            "group_key": _STR, "summary": _STR, "highlights": _STR_ARR}, "required": ["group_key", "summary"]}},
    },
    "required": ["overview", "groups"],
}

QUERIES_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"plans": {"type": "array", "items": {"type": "object", "properties": {
        "id": _STR, "queries": _STR_ARR}, "required": ["id", "queries"]}}},
    "required": ["plans"],
}

