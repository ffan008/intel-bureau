"""流水线内部数据结构与运行上下文。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from bureau.core.logging import RunLogger


@dataclass
class CleanMsg:
    id: int                      # 数据库 id
    ref: str                     # 本次运行内的编号，如 m123
    group_key: str
    group_name: str
    platform: str
    native_id: str
    sender: str
    sent_at: str                 # ISO
    ts: int
    kind: str
    text: str                    # 清洗、脱敏后的文本（证据校验以它为准）
    urls: list[str] = field(default_factory=list)
    reply_to: str | None = None  # 被引用消息的 native_id
    reply_ref: str | None = None
    spread_groups: list[str] = field(default_factory=list)   # 同一段文本出现过的其它群 key
    dup_count: int = 0
    group_weight: float = 1.0
    thread_id: str = ""
    raw_text: str = ""           # v2：数据库原文（未脱敏），提示词原文、提取码从这里截取
    media: dict[str, Any] | None = None     # v2：图片 / 文件候选 {kind, name, attachment}

    @property
    def source_text(self) -> str:
        return self.text + ("\n" + "\n".join(self.urls) if self.urls else "")

    def as_offline(self) -> dict[str, Any]:
        return {"ref": self.ref, "text": self.text, "sender": self.sender, "ts": self.ts, "urls": self.urls,
                "reply_ref": self.reply_ref, "thread_id": self.thread_id,
                "media": (self.media or {}).get("kind"), "raw_text": self.raw_text or self.text}


@dataclass
class Thread:
    id: str
    group_key: str
    msgs: list[CleanMsg] = field(default_factory=list)

    @property
    def speakers(self) -> int:
        return len({m.sender for m in self.msgs})

    @property
    def chars(self) -> int:
        return sum(len(m.text) for m in self.msgs)


@dataclass
class Chunk:
    id: str
    group_key: str
    group_name: str
    platform: str
    msgs: list[CleanMsg]
    text: str
    hash: str
    priority: float = 0.0
    route: str = "llm"           # llm / offline


@dataclass
class Candidate:
    chunk_id: str
    group_key: str
    title: str
    hook: str
    summary: str
    category: str
    kind: str
    steps: list[str]
    tools: list[str]
    links: list[dict[str, str]]
    evidence: list[dict[str, str]]          # [{msg: ref, quote}]
    participants: list[str]
    scores: dict[str, float]
    risk_flags: list[str]
    tags: list[str]
    refs: list[str] = field(default_factory=list)
    provider: str = ""
    # ---- v2（§4 extract 的扩展字段） ----
    topic: str = ""
    sop_steps: list[str] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)       # [{msg, excerpt, purpose}]
    data_points: list[dict[str, Any]] = field(default_factory=list)   # [{label, value, unit, msg, self_reported}]
    quotes: list[dict[str, Any]] = field(default_factory=list)        # [{msg, quote}]
    tool_notes: list[dict[str, Any]] = field(default_factory=list)    # [{tool, scene, verdict, msg}]
    media_refs: list[dict[str, Any]] = field(default_factory=list)    # [{msg, why}]
    privacy: bool = False


@dataclass
class Item:
    id: str
    title: str
    hook: str
    summary: str
    category: str
    kind: str
    steps: list[str]
    tools: list[str]
    links: list[dict[str, str]]
    evidence: list[dict[str, str]]          # 先是 {msg, quote}，核验后补全为 Evidence DTO
    participants: list[str]
    llm_scores: dict[str, float]
    risk_flags: list[str]
    tags: list[str]
    refs: set[str] = field(default_factory=set)
    candidates: int = 1
    scores: dict[str, float] = field(default_factory=dict)
    score: float = 0.0
    trend: str = "new"
    memory_id: int | None = None
    memory_title: str | None = None
    memory_first_seen: str | None = None
    rank: int = 0
    is_headline: bool = False
    is_feature: bool = False
    unverified: list[str] = field(default_factory=list)
    heat_raw: dict[str, float] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    feature: dict[str, Any] = field(default_factory=dict)
    keywords: set[str] = field(default_factory=set)       # 全部词（关联上升信号、计算新信息比例）
    core: list[str] = field(default_factory=list)         # 核心词（TF-IDF 前 12 + 标签 + 工具），存入话题记忆
    # ---- v2：一个 Item 是跨群合并后的一个话题 ----
    topic: str = ""
    points: list[dict[str, Any]] = field(default_factory=list)       # 话题下的各个要点 {title, hook, summary, group_key}
    sop_steps: list[str] = field(default_factory=list)
    prompts: list[dict[str, Any]] = field(default_factory=list)      # 核验后：{text, msg, sender, sent_at, ...}
    data_points: list[dict[str, Any]] = field(default_factory=list)
    quotes: list[dict[str, Any]] = field(default_factory=list)
    tool_notes: list[dict[str, Any]] = field(default_factory=list)
    media_refs: list[dict[str, Any]] = field(default_factory=list)
    privacy: bool = False
    seq: int = 0                                         # 专题序号（从 1 开始，由代码决定）
    article: dict[str, Any] = field(default_factory=dict)            # compose 写出的专题（结构化 + body_md）
    research: list[dict[str, Any]] = field(default_factory=list)     # [{n, title, url, excerpt}]
    media: list[dict[str, Any]] = field(default_factory=list)        # 取回并处理后的媒体（MediaDTO 雏形）
    kb_id: str | None = None


@dataclass
class StageResult:
    metrics: dict[str, Any] = field(default_factory=dict)
    message: str = ""
    status: str = "done"         # done / skipped


class StopPipeline(Exception):
    """阶段要求提前结束（如窗口内没有消息）；后续阶段标为 skipped，运行仍算成功。"""


@dataclass
class RunContext:
    app: Any
    run_id: str
    trigger: str
    schedule_id: str | None
    dry_run: bool
    demo: bool
    start: datetime
    end: datetime
    platforms: list[str]
    group_keys: list[str]
    channel_ids: list[str] | None
    top_n: int
    settings: dict[str, Any]
    log: RunLogger
    progress: Callable[[str, dict[str, Any], str | None], None] = lambda *_: None
    # ---- 产出 ----
    groups: list[dict[str, Any]] = field(default_factory=list)
    raw: list[dict[str, Any]] = field(default_factory=list)
    clean: list[CleanMsg] = field(default_factory=list)
    by_ref: dict[str, CleanMsg] = field(default_factory=dict)
    stats: dict[str, Any] = field(default_factory=dict)
    stats_internal: dict[str, Any] = field(default_factory=dict)
    threads: list[Thread] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    items: list[Item] = field(default_factory=list)
    judgments: list[dict[str, Any]] = field(default_factory=list)
    report: dict[str, Any] = field(default_factory=dict)
    payload: Any = None
    deliveries: list[dict[str, Any]] = field(default_factory=list)
    llm_provider: str = "offline"
    llm_reason: str = ""
    totals: dict[str, Any] = field(default_factory=dict)
    failed_groups: list[str] = field(default_factory=list)
    budget_capped: int = 0               # 因达到单次费用上限而改用离线提取的块数
    budget_warned: bool = False
    # ---- v2 ----
    media: list[dict[str, Any]] = field(default_factory=list)       # 被引用的图片与文档（处理后）
    resources: list[dict[str, Any]] = field(default_factory=list)   # 资源库条目（ResourceDTO）
    digests: list[dict[str, Any]] = field(default_factory=list)     # 分群摘要（GroupDigestDTO）
    v2: dict[str, Any] = field(default_factory=dict)                # 其它 v2 中间结果（overview 摘要、计数、跳过原因）

    @property
    def tz(self) -> str:
        return self.app.tz

    @property
    def scope(self) -> str:
        return "demo" if self.demo else "live"

    def cfg(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.settings
        for part in dotted.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    def budget_exhausted(self) -> tuple[bool, bool]:
        """单次运行的模型费用是否已达上限（llm.max_cost_cny，0 或未设置表示不限）。
        返回 (是否已达上限, 是否第一次发现)，调用方据此只告警一次。"""
        try:
            cap = float(self.cfg("llm.max_cost_cny", 0) or 0)
        except (TypeError, ValueError):
            cap = 0.0
        if cap <= 0 or float(self.totals.get("cost_cny", 0.0)) < cap:
            return False, False
        first = not self.budget_warned
        self.budget_warned = True
        return True, first

    def add_usage(self, tokens_in: int, tokens_out: int, cost: float) -> None:
        self.totals["tokens_in"] = int(self.totals.get("tokens_in", 0)) + int(tokens_in)
        self.totals["tokens_out"] = int(self.totals.get("tokens_out", 0)) + int(tokens_out)
        self.totals["cost_cny"] = round(float(self.totals.get("cost_cny", 0.0)) + float(cost), 4)
