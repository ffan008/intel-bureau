"""按设置选择提供方。auto：已配置密钥的 API → claude_code（可用时）→ offline。

未经用户同意（privacy.cloud_llm_consent=false）不会选择云端提供方，自动退回 offline（本地 Ollama 不受限）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from bureau.contracts import ConfigField
from bureau.core.taxonomy import load_taxonomy
from bureau.llm.anthropic_api import AnthropicProvider
from bureau.llm.base import LLMProvider
from bureau.llm.claude_code import ClaudeCodeProvider
from bureau.llm.offline import OfflineProvider
from bureau.llm.openai_compat import PRESETS, OpenAICompatProvider

PROVIDERS: dict[str, type[LLMProvider]] = {
    "claude_code": ClaudeCodeProvider,
    "openai_compat": OpenAICompatProvider,
    "anthropic": AnthropicProvider,
    "offline": OfflineProvider,
}
PROVIDER_LABELS = {"auto": "自动选择", **{k: v.label for k, v in PROVIDERS.items()}}
CONSENT_HINT = "群聊内容只会在你同意后发给云端模型；在「智能体」页面打开「允许使用云端模型」"


@dataclass
class Resolved:
    provider: LLMProvider
    requested: str
    reason: str
    blocked_by_consent: bool = False


def build_provider(app: Any, name: str, **kw: Any) -> LLMProvider:
    cls = PROVIDERS[name]
    cfg = dict(app.config.get(f"llm.{name}", {}) or {})
    secrets = dict(app.config.secret(f"llm.{name}", {}) or {})
    fx = float(app.config.get("llm.fx_usd_cny", 7.2) or 7.2)
    if name == "offline":
        return OfflineProvider(cfg, secrets, fx_usd_cny=fx, taxonomy=load_taxonomy(app.paths.taxonomy))
    return cls(cfg, secrets, fx_usd_cny=fx, tmp_dir=app.paths.tmp, **kw)


def resolve_provider(app: Any, override: str | None = None) -> Resolved:
    requested = override or str(app.config.get("llm.provider") or "auto")
    consent = bool(app.config.get("privacy.cloud_llm_consent", False))
    if requested != "auto" and requested in PROVIDERS:
        p = build_provider(app, requested)
        if p.is_cloud and not consent:
            return Resolved(build_provider(app, "offline"), requested, "未同意使用云端模型，已改用离线规则提取",
                            blocked_by_consent=True)
        ok, why = p.ready()
        if not ok:
            return Resolved(build_provider(app, "offline"), requested, f"{p.label}不可用（{why}），已改用离线规则提取")
        return Resolved(p, requested, why)
    blocked = False
    for name in ("openai_compat", "anthropic"):
        p = build_provider(app, name)
        has_key = bool(p.secrets.get("api_key")) or (name == "openai_compat" and not p.is_cloud
                                                      and str(app.config.get("llm.openai_compat.preset")) == "ollama")
        if not has_key:
            continue
        if p.is_cloud and not consent:
            blocked = True
            continue
        ok, why = p.ready()
        if ok:
            return Resolved(p, "auto", why)
    cc = build_provider(app, "claude_code")
    if cc.ready()[0]:
        if consent:
            return Resolved(cc, "auto", cc.ready()[1])
        blocked = True
    reason = "未同意使用云端模型，使用离线规则提取" if blocked else "没有可用的模型，使用离线规则提取"
    return Resolved(build_provider(app, "offline"), "auto", reason, blocked_by_consent=blocked)


def llm_status(app: Any) -> dict[str, Any]:
    r = resolve_provider(app)
    p = r.provider
    return {"provider": p.name, "model": p.model or None, "ready": True, "cloud_consent":
            bool(app.config.get("privacy.cloud_llm_consent", False)), "requested": r.requested, "reason": r.reason,
            "offline_mode": p.name == "offline", "blocked_by_consent": r.blocked_by_consent}


def provider_schemas() -> list[dict[str, Any]]:
    preset_opts = [{"value": k, "label": v["label"]} for k, v in PRESETS.items()]

    def f(**kw: Any) -> dict[str, Any]:
        return ConfigField(**kw).model_dump(exclude_none=True)

    return [
        {"key": "auto", "label": PROVIDER_LABELS["auto"], "config_schema": []},
        {"key": "claude_code", "label": ClaudeCodeProvider.label, "config_schema": [
            f(key="command", label="claude 命令", default="claude", help="不在 PATH 上时填绝对路径"),
            f(key="model", label="模型", placeholder="留空用 CLI 默认模型"),
            f(key="timeout_sec", label="超时（秒）", type="number", default=180),
            f(key="concurrency", label="并发上限", type="number", default=2),
            f(key="use_json_schema", label="使用 --json-schema 约束输出", type="bool", default=True)]},
        {"key": "openai_compat", "label": OpenAICompatProvider.label, "config_schema": [
            f(key="preset", label="预设", type="select", options=preset_opts, default="deepseek"),
            f(key="base_url", label="接口地址", type="url", placeholder="留空用预设地址"),
            f(key="model", label="模型", placeholder="留空用预设模型"),
            f(key="api_key", label="API Key", type="secret", help="本地 Ollama 可不填"),
            f(key="json_mode", label="JSON 模式", type="bool", default=True),
            f(key="thinking", label="思考模式（仅 DeepSeek）", type="select", default="disabled",
              options=[{"value": "disabled", "label": "关闭（推荐：结构化提取更快、更省，输出不会被推理挤掉）"},
                       {"value": "enabled", "label": "开启（模型默认，推理内容会占用输出上限）"}],
              help="DeepSeek 默认开启思考模式，推理内容计入 max_tokens，容易把 JSON 截断"),
            f(key="timeout_sec", label="超时（秒）", type="number", default=120),
            f(key="price_in_per_m", label="输入单价（元/百万 token）", type="number", default=0),
            f(key="price_out_per_m", label="输出单价（元/百万 token）", type="number", default=0)]},
        {"key": "anthropic", "label": AnthropicProvider.label, "config_schema": [
            f(key="base_url", label="接口地址", type="url", default="https://api.anthropic.com"),
            f(key="model", label="模型", required=True),
            f(key="api_key", label="API Key", type="secret", required=True),
            f(key="timeout_sec", label="超时（秒）", type="number", default=120),
            f(key="price_in_per_m", label="输入单价（元/百万 token）", type="number", default=0),
            f(key="price_out_per_m", label="输出单价（元/百万 token）", type="number", default=0)]},
        {"key": "offline", "label": OfflineProvider.label, "config_schema": []},
    ]
