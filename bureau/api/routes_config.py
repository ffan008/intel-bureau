"""设置、模型测试、提示词、演示数据。"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from fastapi import APIRouter, Depends, Request

from bureau.api.deps import get_ctx, json_body
from bureau.api.errors import ApiError
from bureau.core.app import AppContext
from bureau.core.constants import RISK_POLICIES
from bureau.core.security import is_unchanged_secret, mask_secret
from bureau.llm.base import LLMError, parse_json_text
from bureau.llm.factory import PROVIDERS, build_provider, llm_status, provider_schemas
from bureau.llm.prompts import PROMPT_NAMES, load_prompt, save_prompt, validate_prompt

router = APIRouter(prefix="/api")
SECTIONS = ("app", "llm", "pipeline", "interests", "privacy", "research", "media")
SECRET_KEYS = {"openai_compat": ("api_key",), "anthropic": ("api_key",)}
# v2：联网研究的密钥（research.deepseek_api_key 留空时复用 llm.openai_compat.api_key）
RESEARCH_SECRET_KEYS = ("deepseek_api_key", "github_token")
# 出现在 settings.yaml 里就算泄露的键名（真正的密钥只能走上面的 SECRET_KEYS 进 secrets.yaml）
SECRET_LIKE = {"api_key", "apikey", "key", "secret", "secret_key", "token", "access_token", "password", "passwd",
               "auth_code", "authorization"}


def _find_secret_like(tree: Any, path: str = "") -> str | None:
    """在补丁里找疑似密钥的键（值非空且不是掩码），返回其路径。"""
    if not isinstance(tree, dict):
        return None
    for k, v in tree.items():
        p = f"{path}.{k}" if path else str(k)
        if str(k).lower() in SECRET_LIKE and v not in (None, "") and not is_unchanged_secret(v):
            return p
        found = _find_secret_like(v, p)
        if found:
            return found
    return None


def settings_view(ctx: AppContext) -> dict[str, Any]:
    s = ctx.config.settings
    out: dict[str, Any] = {k: s.get(k, {}) for k in SECTIONS}
    llm = out["llm"]
    for prov, keys in SECRET_KEYS.items():
        sec = ctx.config.secret(f"llm.{prov}", {}) or {}
        block = llm.setdefault(prov, {})
        for k in keys:
            block[k] = mask_secret(sec.get(k))
    research = out["research"] = dict(out.get("research") or {})
    rsec = ctx.config.secret("research", {}) or {}
    for k in RESEARCH_SECRET_KEYS:
        research[k] = mask_secret(rsec.get(k))
    out["llm_providers"] = provider_schemas()
    out["llm_status"] = llm_status(ctx)
    return out


def apply_settings(ctx: AppContext, patch: dict[str, Any]) -> None:
    unknown = [k for k in patch if k not in SECTIONS]
    if unknown:
        raise ApiError(400, "unknown_section", f"不能修改：{'、'.join(unknown)}", f"可修改的部分：{'、'.join(SECTIONS)}")
    for k, v in patch.items():
        if not isinstance(v, dict):
            raise ApiError(400, "invalid_settings", f"{k} 必须是对象")
    llm = patch.get("llm") or {}
    if "provider" in llm and llm["provider"] not in ("auto", *PROVIDERS):
        raise ApiError(400, "invalid_provider", f"未知的模型提供方：{llm['provider']}")
    # llm 下的对象只能是提供方的配置块（llm.<提供方>），防止写到 llm.providers.* 这类不会生效的位置
    bad_blocks = [k for k, v in llm.items() if isinstance(v, dict) and k not in PROVIDERS]
    if bad_blocks:
        raise ApiError(400, "invalid_settings", f"llm 下不认识的配置块：{'、'.join(bad_blocks)}",
                       f"提供方配置请写在 llm.<提供方> 下，可用：{'、'.join(PROVIDERS)}")
    if "max_cost_cny" in llm:
        v = llm["max_cost_cny"]
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise ApiError(400, "invalid_budget", "max_cost_cny 必须是不小于 0 的数字（0 表示不限）")
    secrets_patch: dict[str, Any] = {}
    deletes: list[str] = []
    for prov, keys in SECRET_KEYS.items():
        block = llm.get(prov)
        if not isinstance(block, dict):
            continue
        for k in keys:
            if k in block:
                v = block.pop(k)
                if v is None:
                    deletes.append(f"llm.{prov}.{k}")
                elif not is_unchanged_secret(v):
                    secrets_patch.setdefault(prov, {})[k] = str(v).strip()
    research = patch.get("research") or {}
    research_secrets: dict[str, Any] = {}
    for k in RESEARCH_SECRET_KEYS:
        if k in research:
            v = research.pop(k)
            if v is None:
                deletes.append(f"research.{k}")
            elif not is_unchanged_secret(v):
                research_secrets[k] = str(v).strip()
    _validate_v2(patch)
    leaked = _find_secret_like(patch)
    if leaked:
        raise ApiError(400, "secret_in_settings", f"「{leaked}」看起来是密钥，不能写进 settings.yaml",
                       "密钥请在对应的配置表单里填写，工作台会把它单独存进 secrets.yaml")
    priv = patch.get("privacy") or {}
    if "retention_days" in priv and (not isinstance(priv["retention_days"], int) or priv["retention_days"] < 1):
        raise ApiError(400, "invalid_retention", "retention_days 必须是正整数")
    app_p = patch.get("app") or {}
    if "host" in app_p and app_p["host"] not in ("127.0.0.1", "localhost"):
        raise ApiError(400, "invalid_host", "服务只允许监听本机（127.0.0.1）")
    if "fx_level" in app_p and app_p["fx_level"] not in ("high", "medium", "low", "off"):
        raise ApiError(400, "invalid_fx", "fx_level 只能是 high / medium / low / off")
    # 全部校验通过后再落盘，避免校验失败时密钥已经写进去
    for path in deletes:
        ctx.config.delete_secret(path)
    if secrets_patch:
        ctx.config.update_secrets({"llm": secrets_patch})
    if research_secrets:
        ctx.config.update_secrets({"research": research_secrets})
    ctx.config.update_settings({k: v for k, v in patch.items() if v})


def _num(sec: str, key: str, v: Any, lo: float, hi: float, *, integer: bool = True) -> None:
    ok = not isinstance(v, bool) and isinstance(v, (int, float)) and (not integer or float(v).is_integer())
    if not ok or not lo <= float(v) <= hi:
        raise ApiError(400, "invalid_settings", f"{sec}.{key} 必须是 {lo:g}~{hi:g} 之间的{'整数' if integer else '数字'}")


def _validate_v2(patch: dict[str, Any]) -> None:
    """v2 新增设置项的取值范围（docs/V2_KNOWLEDGE.md §6）。"""
    pipe = patch.get("pipeline") or {}
    if "risk_policy" in pipe and pipe["risk_policy"] not in RISK_POLICIES:
        raise ApiError(400, "invalid_risk_policy", f"risk_policy 只能是 {' / '.join(RISK_POLICIES)}",
                       "label：只标注不扣分（推荐）；flag：标注并降权；drop：剔除")
    for key, lo, hi, integer in (("max_features", 8, 15, True), ("risk_penalty", 0, 5, False), ("top_n", 1, 20, True),
                                 ("group_digest_min_msgs", 0, 100000, True), ("group_digest_max", 1, 50, True)):
        if key in pipe:
            _num("pipeline", key, pipe[key], lo, hi, integer=integer)
    research = patch.get("research") or {}
    if "provider" in research and research["provider"] not in ("deepseek", "none"):
        raise ApiError(400, "invalid_settings", "research.provider 只能是 deepseek / none")
    for key, lo, hi in (("max_searches", 0, 500), ("max_fetches", 0, 500), ("per_article_queries", 1, 3)):
        if key in research:
            _num("research", key, research[key], lo, hi)
    media = patch.get("media") or {}
    if "ocr" in media and media["ocr"] not in ("windows", "llm", "off"):
        raise ApiError(400, "invalid_settings", "media.ocr 只能是 windows / llm / off")
    for key, lo, hi, integer in (("max_images", 0, 500, True), ("max_files", 0, 200, True), ("max_file_mb", 0.1, 200, False)):
        if key in media:
            _num("media", key, media[key], lo, hi, integer=integer)
    for sec in ("research", "media"):
        for key in ("enabled", "github_enrich", "x_enrich"):
            v = (patch.get(sec) or {}).get(key)
            if v is not None and not isinstance(v, bool):
                raise ApiError(400, "invalid_settings", f"{sec}.{key} 必须是 true / false")


@router.get("/settings")
def get_settings(ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    return settings_view(ctx)


@router.put("/settings")
async def put_settings(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    apply_settings(ctx, await json_body(request))
    ctx.overview_cache.clear()
    ctx.bus.publish("overview.dirty", {})
    return settings_view(ctx)


@router.post("/llm/test")
async def llm_test(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """用当前设置做一次最小调用（测试内容不含任何群聊数据）。"""
    body = await json_body(request)
    name = str(body.get("provider") or ctx.config.get("llm.provider") or "auto")
    if name == "auto":
        for cand in ("openai_compat", "anthropic", "claude_code"):
            if build_provider(ctx, cand).ready()[0]:
                name = cand
                break
        else:
            name = "offline"
    if name not in PROVIDERS:
        raise ApiError(400, "invalid_provider", f"未知的模型提供方：{name}")
    p = build_provider(ctx, name)
    ok, why = p.ready()
    if not ok:
        return {"ok": False, "provider": name, "model": p.model, "latency_ms": 0, "detail": why}
    t0 = time.perf_counter()
    try:
        res = await asyncio.wait_for(p.complete_json(
            "你是连通性测试助手。只输出 JSON。", '请原样输出 {"ok": true}', {"type": "object", "properties": {
                "ok": {"type": "boolean"}}, "required": ["ok"]}, max_tokens=50, temperature=0, task="ping"), 200)
        parsed = res.parsed if res.parsed is not None else parse_json_text(res.text)
        good = isinstance(parsed, dict) and parsed.get("ok") is True
        detail = "调用成功" if good else f"调用成功，但输出不符合预期：{str(res.text)[:80]}"
        if p.is_cloud and not ctx.config.get("privacy.cloud_llm_consent", False):
            detail += "；注意：尚未同意使用云端模型，正式运行仍使用离线规则提取"
        return {"ok": good, "provider": name, "model": res.model or p.model,
                "latency_ms": int((time.perf_counter() - t0) * 1000), "detail": detail}
    except (LLMError, ValueError, asyncio.TimeoutError) as exc:
        hint = getattr(exc, "hint", None)
        return {"ok": False, "provider": name, "model": p.model, "latency_ms": int((time.perf_counter() - t0) * 1000),
                "detail": f"{exc or '调用超时'}" + (f"（{hint}）" if hint else "")}


@router.get("/prompts")
def get_prompts(ctx: AppContext = Depends(get_ctx)) -> list[dict[str, str]]:
    return [{"name": n, "content": load_prompt(ctx.paths.prompts, n)} for n in PROMPT_NAMES]


@router.put("/prompts/{name}")
async def put_prompt(name: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, str]:
    if name not in PROMPT_NAMES:
        raise ApiError(404, "prompt_not_found", f"没有这个提示词：{name}", f"可选 {' / '.join(PROMPT_NAMES)}")
    body = await json_body(request)
    content = body.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ApiError(400, "empty_prompt", "提示词不能为空")
    errors = validate_prompt(name, content)
    if errors:
        raise ApiError(400, "invalid_prompt", "；".join(errors), "保留模板里的占位符和 <!-- system --> / <!-- user --> 分段")
    save_prompt(ctx.paths.prompts, name, content)
    return {"name": name, "content": load_prompt(ctx.paths.prompts, name)}


@router.post("/demo/seed")
async def demo_seed(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, int]:
    from bureau.demo import seed_demo

    if ctx.runner.busy:
        raise ApiError(409, "run_in_progress", "有运行正在进行，请稍后再写入演示数据")
    body = await json_body(request)
    res = await asyncio.to_thread(seed_demo, ctx, reset=bool(body.get("reset", False)))
    ctx.bus.publish("overview.dirty", {})
    return {"groups": res["groups"], "messages": res["messages"]}


@router.post("/demo/clear")
async def demo_clear(ctx: AppContext = Depends(get_ctx)) -> dict[str, bool]:
    from bureau.demo import clear_demo

    if ctx.runner.busy:
        raise ApiError(409, "run_in_progress", "有运行正在进行，请稍后再清除演示数据")
    await asyncio.to_thread(clear_demo, ctx)
    ctx.bus.publish("overview.dirty", {})
    return {"ok": True}
