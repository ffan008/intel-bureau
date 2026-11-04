"""共享数据契约。

采集器、推送通道、流水线和 API 都依赖这里的类型。由 Lead 维护；实现代理不要修改，
需要扩展时在交付说明里提出。
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Platform(str, Enum):
    WECHAT = "wechat"
    QQ = "qq"
    FEISHU = "feishu"
    DEMO = "demo"


PLATFORM_LABELS: dict[Platform, str] = {
    Platform.WECHAT: "微信",
    Platform.QQ: "QQ",
    Platform.FEISHU: "飞书",
    Platform.DEMO: "演示",
}


class MessageKind(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    LINK = "link"
    FILE = "file"
    VIDEO = "video"
    VOICE = "voice"
    STICKER = "sticker"
    CARD = "card"            # 小程序、公众号文章、视频号、名片等卡片
    FORWARD = "forward"      # 合并转发 / 聊天记录
    REPLY = "reply"          # 引用回复（正文仍在 text 里）
    SYSTEM = "system"        # 入群、改名、撤回提示等
    RECALL = "recall"
    REDPACKET = "redpacket"
    OTHER = "other"


class Health(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"
    DISABLED = "disabled"
    UNCONFIGURED = "unconfigured"


class _Model(BaseModel):
    model_config = ConfigDict(extra="ignore", use_enum_values=False)


def group_key(platform: Platform | str, native_id: str) -> str:
    """群的全局唯一键，形如 ``qq:123456``。"""
    p = platform.value if isinstance(platform, Platform) else str(platform)
    return f"{p}:{native_id}"


def split_group_key(key: str) -> tuple[Platform, str]:
    p, _, native = key.partition(":")
    if not native:
        raise ValueError(f"非法的群键：{key!r}")
    return Platform(p), native


class GroupInfo(_Model):
    platform: Platform
    native_id: str                       # 微信 xxx@chatroom、QQ 群号、飞书 oc_xxx
    name: str
    member_count: int | None = None
    avatar_url: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)

    @property
    def key(self) -> str:
        return group_key(self.platform, self.native_id)


class Attachment(_Model):
    kind: Literal["image", "file", "link", "video", "voice", "card"]
    title: str | None = None
    url: str | None = None               # 只保存 http(s) 链接；本地路径放 extra
    extra: dict[str, Any] = Field(default_factory=dict)


class RawMessage(_Model):
    platform: Platform
    group_native_id: str
    group_name: str | None = None
    native_id: str                       # 平台消息 ID，在同一个群内唯一
    sender_id: str | None = None
    sender_name: str                     # 群昵称优先，其次昵称或备注
    sent_at: datetime                    # 必须带时区
    kind: MessageKind = MessageKind.TEXT
    text: str = ""                       # 可读文本；非文本消息用占位描述，如 "[图片]"、"[链接] 标题"
    reply_to: str | None = None          # 被引用消息的 native_id
    quote_text: str | None = None        # 被引用内容摘要
    mentions: list[str] = Field(default_factory=list)
    attachments: list[Attachment] = Field(default_factory=list)
    is_self: bool = False
    raw: dict[str, Any] | None = None    # 平台原始数据（可选，仅调试用；入库前可裁剪）

    @property
    def group_key(self) -> str:
        return group_key(self.platform, self.group_native_id)


class HealthStatus(_Model):
    ok: bool
    state: Health
    detail: str                          # 中文，说明当前状态
    hint: str | None = None              # 中文，说明下一步怎么做
    data: dict[str, Any] = Field(default_factory=dict)   # 如登录账号、版本号


class FetchResult(_Model):
    messages: list[RawMessage] = Field(default_factory=list)
    next_cursor: str | None = None       # 采集器自定义游标，下次增量时传回
    complete: bool = True                # False 表示因上限或错误只拿到一部分
    warnings: list[str] = Field(default_factory=list)


class ConfigField(_Model):
    """前端据此动态生成表单。type 为 secret 的字段存进 secrets.yaml，返回时掩码。"""
    key: str
    label: str
    type: Literal["text", "secret", "number", "bool", "select", "textarea", "url"] = "text"
    required: bool = False
    default: Any = None
    options: list[dict[str, str]] | None = None    # [{"value": "...", "label": "..."}]
    help: str | None = None
    placeholder: str | None = None


class ParsedImport(_Model):
    group: GroupInfo
    messages: list[RawMessage]
    format: str                          # 识别出的格式名，如 "wda_json"、"weflow_json"、"chatlab"、"csv"、"pasted_text"
    warnings: list[str] = Field(default_factory=list)


class HeadlineBrief(_Model):
    title: str
    hook: str
    category: str
    score: float
    trend: Literal["new", "developing", "repeat"] = "new"
    sources: list[str] = Field(default_factory=list)      # 例如 "微信·水彩手绘研习社"
    risk_flags: list[str] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)


class ArticleBrief(_Model):
    """v2：一篇专题知识文章（推送和飞书知识库用）。正文为完整 Markdown。"""
    id: str
    seq: int                             # 当天序号，从 1 开始，由代码生成
    title: str
    hook: str
    category: str
    body_md: str                         # 完整正文（背景 / 群内原话 / 扩展研究 / 步骤 / 提示词 / 资源 / 风险）
    risk_flags: list[str] = Field(default_factory=list)
    risk_note: str | None = None
    sources: list[str] = Field(default_factory=list)      # 例如 "微信·水彩手绘研习社 · 阿杰 · 10-29 09:50"
    image_paths: list[str] = Field(default_factory=list)  # 本地图片路径（相对 assets_dir）
    kb_id: str | None = None             # 对应的知识库条目 ID


class ResourceBrief(_Model):
    """v2：资源库条目（GitHub / X / 公众号 / 网盘 / 其它链接）。"""
    kind: Literal["github", "x", "wechat_article", "netdisk", "video", "doc", "web", "other"]
    title: str
    url: str
    code: str | None = None              # 网盘提取码，原文照录
    meta: dict[str, Any] = Field(default_factory=dict)    # 如 stars / language / likes / words
    note: str | None = None
    shared_by: str | None = None
    group_name: str | None = None
    sent_at: datetime | None = None


class ReportPayload(_Model):
    """交给推送通道的报告。通道自行挑选合适的字段和格式。"""
    report_id: str
    run_id: str
    title: str                           # 如 "情报局 · 每日风向标 | 2026-10-28（周三）"
    date_label: str
    window_label: str
    summary_md: str                      # 推送精简版 Markdown（≤1800 字）
    summary_text: str                    # 纯文本版（QQ 等不支持 Markdown 的通道用）
    full_md: str                         # 完整版 Markdown
    html_path: str | None = None         # 本地完整 HTML 文件路径
    dashboard_url: str | None = None     # 工作台里该报告的地址
    headlines: list[HeadlineBrief] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)
    is_test: bool = False
    # ---- v2 ----
    articles: list[ArticleBrief] = Field(default_factory=list)
    resources: list[ResourceBrief] = Field(default_factory=list)
    sections: dict[str, str] = Field(default_factory=dict)   # 板块 key -> Markdown，key 见 docs/V2_KNOWLEDGE.md §4
    assets_dir: str | None = None        # 报告图片目录（本地绝对路径）
    doc_links: dict[str, str] = Field(default_factory=dict)  # 文档类通道发布后的链接，如 {"feishu_doc": "https://..."}


class DeliveryResult(_Model):
    ok: bool
    channel_id: str
    kind: str
    detail: str                          # 中文
    external_id: str | None = None
    parts: int = 1
    retryable: bool = False
    url: str | None = None               # v2：文档类通道发布后的访问链接（runner 会填进 ReportPayload.doc_links）
