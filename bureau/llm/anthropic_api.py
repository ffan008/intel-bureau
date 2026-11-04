"""anthropic 提供方：Anthropic Messages API（base_url 可改）。"""

from __future__ import annotations

import time
from typing import Any

import httpx

from bureau.llm.base import LLMError, LLMProvider, LLMResult, estimate_cost
from bureau.llm.openai_compat import _http_error


class AnthropicProvider(LLMProvider):
    name = "anthropic"
    label = "Anthropic Messages API"

    def __init__(self, *args: Any, transport: httpx.AsyncBaseTransport | None = None, **kw: Any) -> None:
        super().__init__(*args, **kw)
        self.transport = transport

    @property
    def base_url(self) -> str:
        return str(self.cfg.get("base_url") or "https://api.anthropic.com").rstrip("/")

    @property
    def api_key(self) -> str:
        return str(self.secrets.get("api_key") or "")

    def ready(self) -> tuple[bool, str]:
        if not self.api_key:
            return False, "没有填写 API Key"
        if not self.model:
            return False, "没有填写模型名"
        return True, f"Anthropic · {self.model}"

    async def complete_json(self, system: str, user: str, schema: dict[str, Any] | None = None, *,
                            max_tokens: int = 4096, temperature: float = 0.2, task: str | None = None,
                            context: dict[str, Any] | None = None) -> LLMResult:
        ok, why = self.ready()
        if not ok:
            raise LLMError(why, hint="在「智能体」页面填写 Anthropic API Key 和模型名")
        body = {"model": self.model, "max_tokens": max_tokens, "temperature": temperature, "system": system,
                "messages": [{"role": "user", "content": user}]}
        headers = {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=httpx.Timeout(float(self.cfg.get("timeout_sec") or 120), connect=10),
                                     transport=self.transport) as client:
            try:
                resp = await client.post(f"{self.base_url}/v1/messages", json=body, headers=headers)
            except httpx.TimeoutException as exc:
                raise LLMError("Anthropic 接口超时", retryable=True) from exc
            except httpx.HTTPError as exc:
                raise LLMError(f"无法连接 Anthropic 接口：{exc.__class__.__name__}") from exc
        if resp.status_code >= 400:
            raise _http_error(resp)
        try:
            data = resp.json()
            text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
        except (ValueError, TypeError) as exc:
            raise LLMError("Anthropic 接口返回格式不正确") from exc
        usage = data.get("usage") or {}
        tin, tout = int(usage.get("input_tokens") or 0), int(usage.get("output_tokens") or 0)
        return LLMResult(text=text, usage={"input_tokens": tin, "output_tokens": tout},
                         cost=estimate_cost(tin, tout, self.cfg.get("price_in_per_m", 0), self.cfg.get("price_out_per_m", 0)),
                         provider=self.name, model=str(data.get("model") or self.model),
                         latency=time.perf_counter() - t0)
