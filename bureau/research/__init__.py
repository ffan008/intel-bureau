"""联网研究（负责人 B2）：联网搜索、网页正文、链接分类与增强。签名见 docs/V2_KNOWLEDGE.md §5。

- ``web_search(ctx, query, count=5)``：DeepSeek Search API；没有 key、``research.provider == "none"``、
  ``research.enabled == false``、未同意云端（``privacy.cloud_llm_consent``）或超出 ``max_searches`` 时
  返回空列表并记日志。
- ``fetch_page(ctx, url, max_chars=12000)``：DeepSeek Fetch API，不可用时直接 GET 网页并粗略转 Markdown；
  两条路都先做 SSRF 检查。受 ``max_fetches`` 限制（每次调用计 1 次，不论走哪条路）。
- ``enrich_link(ctx, url, context_text="")``：GitHub / X / 公众号 / 网盘 / 视频 / 文档 / 其它链接的元数据，
  缓存 24 小时；网盘只识别平台和提取码，不发请求。
- ``classify_link(url)``：纯规则分类。

所有函数都不抛异常（参数类型错误除外）；``ctx.used_searches / used_fetches / cost_usd`` 由本模块累加。
"""

from bureau.research.links import classify_link, enrich_link, extract_code, link_provider, normalize_url
from bureau.research.models import LinkMeta, PageContent, ResearchContext, SearchHit
from bureau.research.search import fetch_page, web_search

__all__ = [
    "ResearchContext", "SearchHit", "PageContent", "LinkMeta",
    "web_search", "fetch_page", "enrich_link", "classify_link",
    "extract_code", "link_provider", "normalize_url",
]
