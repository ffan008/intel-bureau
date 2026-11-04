"""联网搜索与网页正文：DeepSeek Search / Fetch API，Fetch 不可用时直接 GET 网页（带 SSRF 防护）。

按 https://api-docs.deepseek.com/guides/search 、/api/search 、/api/fetch 核实（2026-10-30）：
- ``POST https://api.deepseek.com/v1/tools/search``，``Authorization: Bearer <key>``，body
  ``{query(1~128 字), count(1~50，默认 10), need_content(bool), ori_question?, localization?}`` →
  ``{results: [{rerank_score, title, url, snippet, summary, content, site_name, site_icon, date, authority}]}``。
- ``POST https://api.deepseek.com/v1/tools/fetch``，body ``{url}`` → ``{title, content(Markdown)}``。
- 错误为 OpenAI 格式 ``{error: {message, type, param, code}}``；400 参数错、401 key 无效、402 余额不足、
  403 被安全策略拒绝、404 抓不到可用内容、408/429/5xx 可等待后重试。
- 计费：两者都按"成功请求"计，每千次 0.75 美元；只有 HTTP 200 且有结果（Search 的 results 非空、
  Fetch 有正文）才计费。QPS：Search 100、Fetch 25（另有按域名的限制）。
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import httpx

from bureau.integrations.htmltext import html_to_markdown
from bureau.integrations.netsafe import FetchError, HostResolveError, UnsafeURLError, check_url, safe_get
from bureau.research.cache import JsonCache
from bureau.research.models import PageContent, ResearchContext, SearchHit

SEARCH_URL = "https://api.deepseek.com/v1/tools/search"
FETCH_URL = "https://api.deepseek.com/v1/tools/fetch"
PRICE_PER_CALL_USD = 0.75 / 1000          # Search 与 Fetch 同价：每千次成功请求 0.75 美元
RETRY_DELAY = 2.0                          # 429 / 5xx 之后等多久再试一次（测试里改成 0）
API_TIMEOUT = 30.0
PAGE_TIMEOUT = 15.0
PAGE_MAX_BYTES = 2 * 1024 * 1024
MAX_QUERY_CHARS = 128
SEARCH_TTL = 12 * 3600
FETCH_TTL = 24 * 3600
CACHE_CHARS = 60000                        # 缓存里最多保存的正文字数

_PHONE = re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9]\d(?:[- ]?\d{4}){2}(?!\d)")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_STATUS_CN = {
    400: "请求参数不正确", 401: "DeepSeek API Key 无效或缺失", 402: "DeepSeek 账户余额不足，请充值",
    403: "该网页被 DeepSeek 的安全策略拒绝抓取", 404: "DeepSeek 没能抓到这个网页的可用内容",
    408: "请求超时", 413: "请求体过大", 429: "请求过于频繁（QPS 超限）", 500: "DeepSeek 服务内部错误",
    504: "DeepSeek 下游请求超时",
}


# ---------------------------------------------------------------- 设置与密钥

def research_settings(ctx: ResearchContext) -> dict[str, Any]:
    s = ctx.settings or {}
    sec = s.get("research")
    return sec if isinstance(sec, dict) else s


def cloud_consent(ctx: ResearchContext) -> bool:
    s = ctx.settings or {}
    privacy = s.get("privacy") if isinstance(s.get("privacy"), dict) else {}
    return bool(privacy.get("cloud_llm_consent", s.get("cloud_llm_consent", False)))


def api_key(ctx: ResearchContext) -> str:
    sec = ctx.secrets or {}
    key = str(((sec.get("research") or {}).get("deepseek_api_key")) or "").strip()
    if not key:
        key = str((((sec.get("llm") or {}).get("openai_compat") or {}).get("api_key")) or "").strip()
    return key


def deepseek_unavailable(ctx: ResearchContext) -> str | None:
    """返回不能调用 DeepSeek 的原因（中文）；可以调用时返回 None。"""
    rs = research_settings(ctx)
    if rs.get("enabled") is False:
        return "联网研究已关闭（research.enabled=false）"
    if str(rs.get("provider") or "deepseek").strip().lower() == "none":
        return "联网研究提供方为 none"
    if not cloud_consent(ctx):
        return "未同意使用云端服务（privacy.cloud_llm_consent=false）"
    if not api_key(ctx):
        return "没有配置 DeepSeek API Key（research.deepseek_api_key 或 llm.openai_compat.api_key）"
    return None


def clean_query(query: str) -> tuple[str, bool]:
    """去掉手机号、邮箱，压缩空白，截到 128 字。返回 (检索词, 是否删除过隐私内容)。"""
    q = str(query or "")
    scrubbed = _PHONE.sub(" ", q)
    scrubbed = _EMAIL.sub(" ", scrubbed)
    q2 = re.sub(r"\s+", " ", scrubbed).strip()[:MAX_QUERY_CHARS].strip()
    return q2, scrubbed != q


# ---------------------------------------------------------------- HTTP

def _error_message(resp: httpx.Response) -> str:
    base = _STATUS_CN.get(resp.status_code, f"HTTP {resp.status_code}")
    try:
        msg = str(((resp.json() or {}).get("error") or {}).get("message") or "")
    except (ValueError, AttributeError):
        msg = ""
    key_like = re.compile(r"sk-[A-Za-z0-9]{6,}")
    msg = key_like.sub("***", msg)[:120]
    return f"{base}（{msg}）" if msg and resp.status_code not in (401,) else base


async def _post(ctx: ResearchContext, url: str, body: dict[str, Any]) -> tuple[int, Any, str]:
    """POST JSON，429 / 408 / 5xx 时退避后重试 1 次。返回 (状态码, JSON, 中文错误)；网络错误状态码为 0。"""
    headers = {"Authorization": f"Bearer {api_key(ctx)}", "Content-Type": "application/json"}
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(transport=ctx.transport, timeout=httpx.Timeout(API_TIMEOUT, connect=10.0),
                                         follow_redirects=False) as client:
                resp = await client.post(url, json=body, headers=headers)
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            # 还没拿到响应（官方说明超时和失败请求不计费），可以重试
            status, data = 0, None
            err = "连接 DeepSeek 超时" if isinstance(exc, httpx.TimeoutException) else "连不上 DeepSeek"
        except httpx.HTTPError as exc:
            # 已经收到响应但读取 / 解码失败：服务端可能已计费，不重试
            return 0, None, f"读取 DeepSeek 响应失败（{type(exc).__name__}）"
        else:
            if resp.status_code == 200:
                try:
                    return 200, resp.json(), ""
                except ValueError:
                    return 200, None, "DeepSeek 返回的不是 JSON"
            status, data, err = resp.status_code, None, _error_message(resp)
            if status in (429, 408) or status >= 500:
                if attempt == 0:
                    delay = RETRY_DELAY
                    ra = resp.headers.get("retry-after", "").strip()
                    if RETRY_DELAY > 0 and ra.isdigit():
                        delay = min(max(float(ra), RETRY_DELAY), 10.0)
                    ctx.logger.info("DeepSeek 返回 %s，%.1f 秒后重试一次", status, delay)
                    if delay > 0:
                        await asyncio.sleep(delay)
                    continue
            return status, data, err
        if attempt == 0:
            if RETRY_DELAY > 0:
                await asyncio.sleep(RETRY_DELAY)
            continue
        return status, data, err
    return 0, None, "DeepSeek 请求失败"


def _cache(ctx: ResearchContext, name: str, ttl: float) -> JsonCache:
    return JsonCache(Path(ctx.data_dir) / "cache" / "research" / name, ttl)


# ---------------------------------------------------------------- web_search

def _hit(r: dict[str, Any]) -> SearchHit | None:
    url = str(r.get("url") or "").strip()
    if not url.lower().startswith(("http://", "https://")):
        return None
    content = str(r.get("content") or "").strip() or None
    return SearchHit(
        title=str(r.get("title") or "").strip() or url,
        url=url,
        summary=str(r.get("summary") or r.get("snippet") or "").strip(),
        content=content[:CACHE_CHARS] if content else None,
        site=(str(r.get("site_name") or "").strip() or None),
        published_at=(str(r.get("date") or "").strip() or None),
    )


async def web_search(ctx: ResearchContext, query: str, *, count: int = 5) -> list[SearchHit]:
    """DeepSeek 联网搜索。不可用、超出预算或失败时返回空列表并记日志，不抛异常。"""
    q, scrubbed = clean_query(query)
    if scrubbed:
        ctx.logger.warning("检索词里有手机号或邮箱，已删除后再搜索")
    if not q:
        return []
    reason = deepseek_unavailable(ctx)
    if reason:
        ctx.logger.info("跳过联网搜索：%s", reason)
        return []
    n = max(1, min(int(count or 5), 50))
    cache = _cache(ctx, "search", SEARCH_TTL)
    ckey = f"search|{n}|{q}"
    cached = cache.get(ckey)
    if isinstance(cached, list):
        return [SearchHit(**h) for h in cached if isinstance(h, dict)]
    if ctx.used_searches >= ctx.max_searches:
        ctx.logger.info("联网搜索已达本次上限（%d 次），跳过", ctx.max_searches)
        return []
    ctx.used_searches += 1
    status, data, err = await _post(ctx, SEARCH_URL, {"query": q, "count": n, "need_content": True})
    if status != 200 or not isinstance(data, dict):
        ctx.logger.warning("联网搜索失败：%s", err or "返回格式不正确")
        return []
    results = data.get("results")
    if not isinstance(results, list):
        ctx.logger.warning("联网搜索返回格式不正确（缺少 results）")
        return []
    hits = [h for h in (_hit(r) for r in results if isinstance(r, dict)) if h]
    if results:
        ctx.cost_usd += PRICE_PER_CALL_USD
    cache.set(ckey, [h.model_dump() for h in hits])
    ctx.logger.info("联网搜索完成：%d 条结果", len(hits))
    return hits[:n]


# ---------------------------------------------------------------- fetch_page

def _clip(md: str, max_chars: int) -> str:
    md = (md or "").strip()
    if len(md) <= max_chars:
        return md
    return md[:max_chars].rstrip() + f"\n\n（正文过长，已截断，原文约 {len(md)} 字）"


async def _direct_fetch(ctx: ResearchContext, url: str) -> PageContent:
    try:
        resp = await safe_get(url, transport=ctx.transport, resolver=ctx.resolver, timeout=PAGE_TIMEOUT,
                              max_bytes=PAGE_MAX_BYTES)
    except UnsafeURLError as exc:
        return PageContent(url=url, title=None, markdown="", ok=False, error=str(exc))
    except FetchError as exc:
        return PageContent(url=url, title=None, markdown="", ok=False, error=exc.message)
    if resp.status >= 400:
        return PageContent(url=url, title=None, markdown="", ok=False, error=f"网页返回 HTTP {resp.status}")
    ctype = resp.content_type
    if ctype in ("text/plain", "text/markdown", "application/json") or ctype.endswith("+json"):
        text = resp.text()
        return PageContent(url=resp.url, title=None, markdown=text[:CACHE_CHARS], ok=bool(text.strip()),
                           error=None if text.strip() else "网页没有正文")
    if ctype and "html" not in ctype and "xml" not in ctype:
        return PageContent(url=url, title=None, markdown="", ok=False, error=f"不支持的内容类型：{ctype}")
    root = "js_content" if "mp.weixin.qq.com" in resp.url else None
    doc = html_to_markdown(resp.text(), root_id=root)
    title = doc.meta.get("og:title") or doc.meta.get("wx:msg_title") or doc.title
    md = doc.markdown
    if resp.truncated:
        md += "\n\n（网页超过 2 MB，只读取了前面部分）"
    if not md.strip():
        return PageContent(url=resp.url, title=title, markdown="", ok=False, error="网页没有可提取的正文")
    return PageContent(url=resp.url, title=title, markdown=md[:CACHE_CHARS], ok=True)


async def fetch_page(ctx: ResearchContext, url: str, *, max_chars: int = 12000) -> PageContent:
    """读取网页正文（Markdown）。优先 DeepSeek Fetch；不可用或失败时直接 GET。不抛异常。"""
    url = str(url or "").strip()
    max_chars = max(200, int(max_chars or 12000))
    try:
        await check_url(url, resolver=ctx.resolver)
        resolvable = True
    except HostResolveError:
        resolvable = False
    except UnsafeURLError as exc:
        ctx.logger.warning("拒绝抓取网页：%s", exc)
        return PageContent(url=url, title=None, markdown="", ok=False, error=str(exc))
    rs = research_settings(ctx)
    if rs.get("enabled") is False:
        return PageContent(url=url, title=None, markdown="", ok=False, error="联网研究已关闭")
    cache = _cache(ctx, "fetch", FETCH_TTL)
    cached = cache.get(f"fetch|{url}")
    if isinstance(cached, dict) and cached.get("ok"):
        page = PageContent(**cached)
        return page.model_copy(update={"markdown": _clip(page.markdown, max_chars)})
    if ctx.used_fetches >= ctx.max_fetches:
        ctx.logger.info("网页抓取已达本次上限（%d 次），跳过", ctx.max_fetches)
        return PageContent(url=url, title=None, markdown="", ok=False, error=f"已达本次抓取上限（{ctx.max_fetches} 次）")
    ctx.used_fetches += 1
    page: PageContent | None = None
    reason = deepseek_unavailable(ctx)
    if reason is None:
        status, data, err = await _post(ctx, FETCH_URL, {"url": url})
        content = str((data or {}).get("content") or "").strip() if isinstance(data, dict) else ""
        if status == 200 and content:
            ctx.cost_usd += PRICE_PER_CALL_USD
            page = PageContent(url=url, title=str(data.get("title") or "").strip() or None,
                               markdown=content[:CACHE_CHARS], ok=True)
        else:
            ctx.logger.info("DeepSeek Fetch 未取到内容（%s），改为直接读取网页", err or "正文为空")
    else:
        ctx.logger.info("不使用 DeepSeek Fetch：%s；改为直接读取网页", reason)
    if page is None:
        if not resolvable:
            return PageContent(url=url, title=None, markdown="", ok=False, error="域名解析失败")
        page = await _direct_fetch(ctx, url)
    if page.ok:
        cache.set(f"fetch|{url}", page.model_dump())
        return page.model_copy(update={"markdown": _clip(page.markdown, max_chars)})
    ctx.logger.info("网页抓取失败：%s", page.error)
    return page
