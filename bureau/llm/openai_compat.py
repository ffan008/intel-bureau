"""openai_compat 提供方：任意 OpenAI 兼容的 /chat/completions 接口，带国内常用预设。"""

from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlparse

import httpx

from bureau.core.security import is_loopback
from bureau.llm.base import LLMError, LLMProvider, LLMResult, estimate_cost

PRESETS: dict[str, dict[str, str]] = {
    # 官方文档（api-docs.deepseek.com，2026-10-30 核对）：OpenAI 格式的 base_url 不带 /v1，模型名 deepseek-flash / deepseek-v4-pro
    "deepseek": {"label": "DeepSeek", "base_url": "https://api.deepseek.com", "model": "deepseek-flash"},
    "dashscope": {"label": "通义千问（DashScope 兼容模式）", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                  "model": "qwen-plus"},
    "moonshot": {"label": "Kimi（月之暗面）", "base_url": "https://api.moonshot.cn/v1", "model": "moonshot-v1-32k"},
    "zhipu": {"label": "智谱 GLM", "base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    "siliconflow": {"label": "硅基流动", "base_url": "https://api.siliconflow.cn/v1", "model": "Qwen/Qwen2.5-72B-Instruct"},
    "openrouter": {"label": "OpenRouter", "base_url": "https://openrouter.ai/api/v1", "model": "deepseek/deepseek-chat"},
    "ollama": {"label": "本地 Ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:7b"},
    "custom": {"label": "自定义", "base_url": "", "model": ""},
}


class OpenAICompatProvider(LLMProvider):
    name = "openai_compat"
    label = "OpenAI 兼容接口"

    def __init__(self, *args: Any, transport: httpx.AsyncBaseTransport | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.transport = transport

    @property
    def preset(self) -> dict[str, str]:
        return PRESETS.get(str(self.cfg.get("preset") or "deepseek"), PRESETS["custom"])

    @property
    def base_url(self) -> str:
        return str(self.cfg.get("base_url") or self.preset["base_url"]).rstrip("/")

    @property
    def model(self) -> str:
        return str(self.cfg.get("model") or self.preset["model"])

    @property
    def api_key(self) -> str:
        return str(self.secrets.get("api_key") or "")

    @property
    def is_cloud(self) -> bool:
        host = urlparse(self.base_url).hostname
        return not is_loopback(host)

    @property
    def is_deepseek(self) -> bool:
        """DeepSeek 官方接口（预设或手填地址）。只有它认识 thinking 参数。"""
        host = (urlparse(self.base_url).hostname or "").lower()
        return host == "api.deepseek.com" or host.endswith(".deepseek.com")

    def ready(self) -> tuple[bool, str]:
        if not self.base_url:
            return False, "没有填写接口地址"
        if not self.model:
            return False, "没有填写模型名"
        if self.is_cloud and not self.api_key:
            return False, "没有填写 API Key"
        return True, f"{self.preset['label']} · {self.model}"

    async def complete_json(self, system: str, user: str, schema: dict[str, Any] | None = None, *,
                            max_tokens: int = 4096, temperature: float = 0.2, task: str | None = None,
                            context: dict[str, Any] | None = None) -> LLMResult:
        ok, why = self.ready()
        if not ok:
            raise LLMError(why, hint="在「智能体」页面填写接口地址、模型和 API Key")
        body: dict[str, Any] = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        if self.cfg.get("json_mode", True):
            body["response_format"] = {"type": "json_object"}
        if self.is_deepseek:
            # DeepSeek 默认开启思考模式：推理内容计入 max_tokens，会把 JSON 截断，temperature 也不生效
            body["thinking"] = {"type": "enabled" if str(self.cfg.get("thinking") or "disabled") == "enabled"
                                else "disabled"}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        timeout = httpx.Timeout(float(self.cfg.get("timeout_sec") or 120), connect=10)
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout, transport=self.transport) as client:
            try:
                resp = await client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
                if resp.status_code == 400 and any(k in body and k in resp.text for k in ("response_format", "thinking")):
                    for k in ("response_format", "thinking"):
                        if k in resp.text:
                            body.pop(k, None)
                    resp = await client.post(f"{self.base_url}/chat/completions", json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise LLMError("模型接口超时", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"无法连接模型接口：{exc.__class__.__name__}", hint=f"检查地址 {self.base_url}") from exc
        latency = time.perf_counter() - t0
        if resp.status_code >= 400:
            raise _http_error(resp)
        try:
            data = resp.json()
            text = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("模型接口返回格式不正确") from exc
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
        cost = estimate_cost(tin, tout, self.cfg.get("price_in_per_m", 0), self.cfg.get("price_out_per_m", 0))
        return LLMResult(text=text, usage={"input_tokens": tin, "output_tokens": tout}, cost=cost,
                         provider=self.name, model=str(data.get("model") or self.model), latency=latency)


def _http_error(resp: httpx.Response) -> LLMError:
    code = resp.status_code
    if code in (401, 403):
        return LLMError(f"API Key 无效或没有权限（HTTP {code}）", hint="检查 API Key 是否填写正确、是否已开通该模型")
    if code == 402:
        return LLMError("账户余额不足（HTTP 402）", hint="到服务商控制台充值")
    if code == 404:
        return LLMError("接口地址或模型不存在（HTTP 404）", hint="检查 base_url 和模型名")
    if code == 429:
        return LLMError("请求过于频繁或额度用完（HTTP 429）", hint="稍后再试，或调低并发", retryable=True)
    return LLMError(f"模型接口出错（HTTP {code}）", retryable=code >= 500)
