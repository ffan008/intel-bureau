"""bureau.research：DeepSeek Search / Fetch 请求格式、预算、降级、SSRF、链接增强与缓存。全部走 MockTransport + 假 DNS。"""

from __future__ import annotations

import json
import logging

import httpx
import pytest

from bureau.integrations import netsafe
from bureau.research import (LinkMeta, ResearchContext, classify_link, enrich_link, extract_code, fetch_page,
                             web_search)
from bureau.research import search as search_mod

from .helpers import MockHTTP, ok_json, run

PUBLIC_IP = "93.184.216.34"
DNS = {"intranet.example.com": ["10.1.2.3"], "rebind.example.com": ["93.184.216.34", "127.0.0.1"],
       "nx.example.com": []}

SEARCH_OK = {"results": [
    {"rerank_score": 2.4, "title": "HyperFrames", "url": "https://github.com/heygen-com/hyperframes",
     "snippet": "短摘要", "summary": "长摘要" * 10, "content": "正文内容", "site_name": "GitHub",
     "site_icon": "https://github.com/favicon.ico", "date": "2026-06-01T00:00:00+00:00", "authority": 3},
    {"rerank_score": 1.1, "title": "坏结果", "url": "javascript:alert(1)", "snippet": "", "summary": "",
     "content": "", "site_name": None, "site_icon": None, "date": None, "authority": -1},
]}


async def fake_resolver(host: str, port: int) -> list[str]:
    if host in DNS:
        if not DNS[host]:
            raise OSError("NXDOMAIN")
        return DNS[host]
    return [PUBLIC_IP]


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch):
    monkeypatch.setattr(search_mod, "RETRY_DELAY", 0.0)


def make_ctx(tmp_path, handler, *, key="sk-test-key-123456", consent=True, provider="deepseek",
             max_searches=5, max_fetches=5, extra_research=None, secrets=None):
    http = MockHTTP(handler)
    research = {"enabled": True, "provider": provider} | (extra_research or {})
    sec = secrets if secrets is not None else ({"llm": {"openai_compat": {"api_key": key}}} if key else {})
    ctx = ResearchContext(settings={"research": research, "privacy": {"cloud_llm_consent": consent}},
                          secrets=sec, data_dir=tmp_path, max_searches=max_searches, max_fetches=max_fetches,
                          logger=logging.getLogger("test.research"), transport=http.transport,
                          resolver=fake_resolver)
    return ctx, http


def never(request):
    raise AssertionError(f"不应发出请求：{request.url}")


# ---------------------------------------------------------------- web_search

def test_search_request_format_and_parsing(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(SEARCH_OK))
    hits = run(web_search(ctx, "HyperFrames HeyGen GitHub", count=3))
    req = http.requests[0]
    assert req.method == "POST" and str(req.url) == "https://api.deepseek.com/v1/tools/search"
    assert req.headers["authorization"] == "Bearer sk-test-key-123456"
    assert http.body() == {"query": "HyperFrames HeyGen GitHub", "count": 3, "need_content": True}
    assert len(hits) == 1                                   # 非 http(s) 链接被丢弃
    h = hits[0]
    assert (h.title, h.url, h.site, h.published_at) == ("HyperFrames", "https://github.com/heygen-com/hyperframes",
                                                        "GitHub", "2026-06-01T00:00:00+00:00")
    assert h.summary.startswith("长摘要") and h.content == "正文内容"
    assert ctx.used_searches == 1 and ctx.cost_usd == pytest.approx(0.00075)


def test_search_prefers_research_key_then_llm_key(tmp_path):
    secrets = {"research": {"deepseek_api_key": "sk-research-only"}, "llm": {"openai_compat": {"api_key": "sk-llm"}}}
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(SEARCH_OK), secrets=secrets)
    run(web_search(ctx, "q"))
    assert http.requests[0].headers["authorization"] == "Bearer sk-research-only"


@pytest.mark.parametrize("kw", [dict(key=""), dict(provider="none"), dict(consent=False),
                                dict(extra_research={"enabled": False})])
def test_search_degrades_without_key_provider_or_consent(tmp_path, kw, caplog):
    ctx, http = make_ctx(tmp_path, never, **kw)
    with caplog.at_level(logging.INFO, logger="test.research"):
        assert run(web_search(ctx, "anything")) == []
    assert http.requests == [] and ctx.used_searches == 0 and "跳过联网搜索" in caplog.text


def test_search_budget_and_cache(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(SEARCH_OK), max_searches=2)
    assert run(web_search(ctx, "q1")) and run(web_search(ctx, "q2"))
    assert run(web_search(ctx, "q3")) == []                  # 超出 max_searches
    assert len(http.requests) == 2 and ctx.used_searches == 2
    assert run(web_search(ctx, "q1"))                         # 命中缓存：不发请求、不占预算
    assert len(http.requests) == 2 and ctx.used_searches == 2


def test_search_429_retries_once_then_gives_up(tmp_path):
    calls = []

    def handler(r):
        calls.append(1)
        return ok_json({"error": {"message": "rate limited"}}, status=429) if len(calls) < 2 else ok_json(SEARCH_OK)

    ctx, _ = make_ctx(tmp_path, handler)
    assert len(run(web_search(ctx, "q"))) == 1 and len(calls) == 2
    ctx2, http2 = make_ctx(tmp_path / "b", lambda r: ok_json({"error": {"message": "x"}}, status=429))
    assert run(web_search(ctx2, "q")) == [] and len(http2.requests) == 2      # 只重试 1 次
    assert ctx2.cost_usd == 0


def test_search_errors_do_not_raise_or_bill(tmp_path, caplog):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json({"error": {"message": "bad key sk-abcdefghijk"}}, status=401))
    with caplog.at_level(logging.WARNING, logger="test.research"):
        assert run(web_search(ctx, "q")) == []
    assert len(http.requests) == 1 and ctx.cost_usd == 0 and "API Key 无效" in caplog.text
    assert "sk-abcdefghijk" not in caplog.text and "sk-test-key" not in caplog.text
    ctx2, _ = make_ctx(tmp_path / "e", lambda r: ok_json({"results": []}))
    assert run(web_search(ctx2, "q")) == [] and ctx2.cost_usd == 0            # 空结果不计费


def test_search_scrubs_phone_and_email_and_clips(tmp_path, caplog):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(SEARCH_OK))
    with caplog.at_level(logging.WARNING, logger="test.research"):
        run(web_search(ctx, "联系 13812345678 或 a.b@example.com 的 ComfyUI 工作流 " + "长" * 300))
    q = http.body()["query"]
    assert "13812345678" not in q and "example.com" not in q and "ComfyUI" in q and len(q) <= 128
    assert "手机号或邮箱" in caplog.text


# ---------------------------------------------------------------- fetch_page

def test_fetch_page_deepseek_format_budget_and_cache(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json({"title": "页面", "content": "# 页面\n\n" + "字" * 500}),
                         max_fetches=1)
    page = run(fetch_page(ctx, "https://example.com/a", max_chars=300))
    assert str(http.requests[0].url) == "https://api.deepseek.com/v1/tools/fetch"
    assert http.body() == {"url": "https://example.com/a"}
    assert page.ok and page.title == "页面" and "已截断" in page.markdown and len(page.markdown) < 360
    assert ctx.used_fetches == 1 and ctx.cost_usd == pytest.approx(0.00075)
    assert run(fetch_page(ctx, "https://example.com/a")).ok and len(http.requests) == 1   # 缓存
    over = run(fetch_page(ctx, "https://example.com/b"))
    assert not over.ok and "上限" in over.error and len(http.requests) == 1


def test_fetch_page_falls_back_to_direct_get(tmp_path):
    html = ("<html><head><title>直连标题</title><style>.x{}</style></head><body><nav>菜单</nav>"
            "<h2>小节</h2><p>第一段<a href='https://a.example.org/x'>链接</a></p><script>alert(1)</script>"
            "<ul><li>甲</li><li>乙</li></ul></body></html>")

    def handler(r):
        if r.url.host == "api.deepseek.com":
            return ok_json({"error": {"message": "no content"}}, status=404)
        return httpx.Response(200, html=html)

    ctx, http = make_ctx(tmp_path, handler)
    page = run(fetch_page(ctx, "https://example.com/p"))
    assert page.ok and page.title == "直连标题" and ctx.used_fetches == 1 and ctx.cost_usd == 0
    assert "## 小节" in page.markdown and "[链接](https://a.example.org/x)" in page.markdown
    assert "- 甲" in page.markdown and "alert" not in page.markdown and "菜单" not in page.markdown
    assert [r.url.host for r in http.requests] == ["api.deepseek.com", "example.com"]


def test_fetch_page_without_key_goes_direct(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: httpx.Response(200, text="纯文本", headers={"content-type": "text/plain"}),
                         key="")
    page = run(fetch_page(ctx, "https://example.com/t.txt"))
    assert page.ok and page.markdown == "纯文本" and [r.url.host for r in http.requests] == ["example.com"]


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/admin", "http://localhost:8765/api", "http://10.0.0.8/", "http://192.168.1.1/",
    "http://172.16.0.1/", "http://169.254.169.254/latest/meta-data/", "http://[::1]/", "http://0.0.0.0/",
    "http://[::ffff:127.0.0.1]/", "http://100.64.0.1/", "http://2130706433/", "http://0x7f.1/",
    "http://intranet.example.com/", "http://rebind.example.com/", "file:///C:/Windows/win.ini",
    "ftp://example.com/x", "http://user:pw@example.com/", "http://printer.local/", "http://intranet/",
])
def test_fetch_page_blocks_ssrf(tmp_path, url):
    ctx, http = make_ctx(tmp_path, never)
    page = run(fetch_page(ctx, url))
    assert not page.ok and page.error and http.requests == [] and ctx.used_fetches == 0


def test_fetch_page_blocks_redirect_to_internal(tmp_path):
    def handler(r):
        if r.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.5/secret"})
        raise AssertionError(f"跟随了指向内网的重定向：{r.url}")

    ctx, http = make_ctx(tmp_path, handler, key="")
    page = run(fetch_page(ctx, "https://example.com/r"))
    assert not page.ok and "内网" in page.error and [str(r.url) for r in http.requests] == ["https://example.com/r"]


def test_safe_get_strips_auth_on_cross_host_redirect_and_limits_size(tmp_path):
    seen = []

    def handler(r):
        seen.append((r.url.host, r.headers.get("authorization")))
        if r.url.host == "api.github.com":
            return httpx.Response(301, headers={"location": "https://other.example.org/x"})
        return httpx.Response(200, content=b"x" * 5000)

    http = MockHTTP(handler)
    resp = run(netsafe.safe_get("https://api.github.com/repos/a/b", transport=http.transport, resolver=fake_resolver,
                                headers={"Authorization": "Bearer t"}, max_bytes=1000))
    assert seen == [("api.github.com", "Bearer t"), ("other.example.org", None)]
    assert resp.truncated and len(resp.content) == 1000
    with pytest.raises(netsafe.FetchError):
        run(netsafe.safe_get("https://other.example.org/x", transport=http.transport, resolver=fake_resolver,
                             max_bytes=1000, oversize="error"))


def test_ip_blocklist():
    for ip in ("127.0.0.1", "10.0.0.1", "172.31.255.255", "192.168.0.1", "169.254.1.1", "100.64.0.1", "0.0.0.0",
               "::1", "fe80::1", "fc00::1", "::ffff:10.0.0.1", "2002:7f00:1::", "64:ff9b::7f00:1", "224.0.0.1",
               "240.0.0.1", "not-an-ip"):
        assert netsafe.ip_blocked(ip), ip
    for ip in ("93.184.216.34", "1.1.1.1", "2606:4700::1111"):
        assert not netsafe.ip_blocked(ip), ip


# ---------------------------------------------------------------- 分类与提取码

@pytest.mark.parametrize("url,kind", [
    ("https://github.com/NapNeko/NapCatQQ", "github"), ("github.com/a/b", "github"),
    ("https://raw.githubusercontent.com/a/b/main/README.md", "github"), ("https://gist.github.com/u/1", "github"),
    ("https://x.com/jack/status/20", "x"), ("https://twitter.com/a/status/1?s=20", "x"), ("https://x.com/home", "x"),
    ("https://mp.weixin.qq.com/s/AbCdEf", "wechat_article"), ("https://mp.weixin.qq.com/s?__biz=x&mid=1", "wechat_article"),
    ("https://pan.quark.cn/s/abc123", "netdisk"), ("https://pan.baidu.com/s/1xYz?pwd=ab12", "netdisk"),
    ("https://www.alipan.com/s/xyz", "netdisk"), ("https://www.aliyundrive.com/s/xyz", "netdisk"),
    ("https://cloud.189.cn/t/abc", "netdisk"), ("https://www.123pan.com/s/abc", "netdisk"),
    ("https://www.123684.com/s/abc", "netdisk"), ("https://wwi.lanzoue.com/iAbc", "netdisk"),
    ("https://xx.lanzoux.com/i1", "netdisk"), ("https://pan.xunlei.com/s/VN1", "netdisk"),
    ("https://115.com/s/sw1?password=a1b2", "netdisk"), ("https://115cdn.com/s/sw1", "netdisk"),
    ("https://drive.uc.cn/s/abc", "netdisk"),
    ("https://www.bilibili.com/video/BV1xx", "video"), ("https://b23.tv/abc", "video"),
    ("https://v.douyin.com/abc/", "video"), ("https://www.youtube.com/watch?v=1", "video"),
    ("https://youtu.be/abc", "video"), ("https://channels.weixin.qq.com/web/x", "video"),
    ("https://weixin.qq.com/sph/Abc", "video"),
    ("https://abc.feishu.cn/docx/Xyz", "doc"), ("https://abc.feishu.cn/wiki/Xyz", "doc"),
    ("https://abc.larksuite.com/docx/Xyz", "doc"), ("https://docs.qq.com/doc/DAbc", "doc"),
    ("https://www.yuque.com/u/b/c", "doc"), ("https://abc.feishu.cn/", "web"),
    ("https://example.com/post", "web"), ("http://news.ycombinator.com/", "web"),
    ("magnet:?xt=urn:btih:abc", "other"), ("ed2k://|file|a|1|h|/", "other"), ("", "other"), ("not a url", "other"),
])
def test_classify_link(url, kind):
    assert classify_link(url) == kind


@pytest.mark.parametrize("url,ctx_text,code", [
    ("https://pan.baidu.com/s/1abc?pwd=x9k2", "", "x9k2"),
    ("https://115.com/s/sw1?password=a1b2", "", "a1b2"),
    ("https://cloud.189.cn/t/abc", "https://cloud.189.cn/t/abc（访问码：ma7q）", "ma7q"),
    ("https://pan.quark.cn/s/abc", "链接：https://pan.quark.cn/s/abc 提取码：Ab12 复制这段内容打开", "Ab12"),
    ("https://pan.quark.cn/s/abc", "https://pan.quark.cn/s/abc\n码:hK3d", "hK3d"),
    ("https://pan.quark.cn/s/abc", "https://pan.quark.cn/s/abc 密码 【QwEr】", "QwEr"),
    ("https://pan.quark.cn/s/abc", "https://pan.quark.cn/s/abc pwd=zz99", "zz99"),
    ("https://pan.quark.cn/s/abc", "https://pan.quark.cn/s/abc 邀请码：ZZZZ", None),
    ("https://pan.quark.cn/s/abc", "用 Claude Code 2024 做的", None),
    ("https://pan.quark.cn/s/abc", "", None),
    ("https://pan.quark.cn/s/b", "A：https://pan.quark.cn/s/a 提取码：1111\nB：https://pan.quark.cn/s/b 提取码：2222", "2222"),
])
def test_extract_code(url, ctx_text, code):
    assert extract_code(url, ctx_text) == code


# ---------------------------------------------------------------- enrich_link

GITHUB_REPO = {"full_name": "NapNeko/NapCatQQ", "description": "Modern protocol-side framework based on NTQQ",
               "stargazers_count": 11968, "forks_count": 863, "language": "TypeScript",
               "updated_at": "2026-10-29T18:39:40Z", "pushed_at": "2026-10-29T16:17:49Z",
               "topics": ["napcat", "onebot"], "archived": False, "license": {"spdx_id": "NOASSERTION"}}


def test_enrich_github_request_fields_and_cache(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(GITHUB_REPO), secrets={"research": {"github_token": "ghp_x"}})
    m = run(enrich_link(ctx, "https://github.com/NapNeko/NapCatQQ/tree/main/src"))
    req = http.requests[0]
    assert str(req.url) == "https://api.github.com/repos/NapNeko/NapCatQQ"
    assert req.headers["authorization"] == "Bearer ghp_x" and "github" in req.headers["accept"]
    assert m.ok and m.kind == "github" and m.title == "NapNeko/NapCatQQ"
    assert m.meta["stars"] == 11968 and m.meta["language"] == "TypeScript" and m.meta["forks"] == 863
    assert m.meta["updated_at"] and m.meta["topics"] == ["napcat", "onebot"] and m.description.startswith("Modern")
    again = run(enrich_link(ctx, "https://github.com/NapNeko/NapCatQQ/tree/main/src"))
    assert again == m and len(http.requests) == 1                        # 24 小时缓存


def test_enrich_github_not_found_and_rate_limit(tmp_path):
    ctx, _ = make_ctx(tmp_path, lambda r: ok_json({"message": "Not Found"}, status=404))
    m = run(enrich_link(ctx, "https://github.com/ghost/none"))
    assert not m.ok and "找不到" in m.error and m.title == "ghost/none"
    ctx2, _ = make_ctx(tmp_path / "r", lambda r: ok_json({"message": "API rate limit"}, status=403))
    m2 = run(enrich_link(ctx2, "https://github.com/a/b"))
    assert not m2.ok and "github_token" in m2.error


def test_enrich_github_disabled_makes_no_request(tmp_path):
    ctx, http = make_ctx(tmp_path, never, extra_research={"github_enrich": False})
    m = run(enrich_link(ctx, "https://github.com/a/b"))
    assert m.ok and m.title == "a/b" and http.requests == []


FX_TWEET = {"code": 200, "message": "OK", "tweet": {
    "url": "https://x.com/jack/status/20", "id": "20", "text": "just setting up my twttr",
    "author": {"name": "jack", "screen_name": "jack"}, "likes": 300000, "retweets": 120000, "replies": 20000,
    "views": None, "created_at": "Tue Mar 21 20:50:14 +0000 2006", "created_timestamp": 1142974214, "lang": "en"}}


def test_enrich_x_via_fxtwitter(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: ok_json(FX_TWEET))
    m = run(enrich_link(ctx, "https://twitter.com/jack/status/20?s=21"))
    assert str(http.requests[0].url) == "https://api.fxtwitter.com/jack/status/20"
    assert m.ok and m.kind == "x" and m.title.startswith("@jack：just setting")
    assert (m.meta["author"], m.meta["likes"], m.meta["retweets"]) == ("jack", 300000, 120000)
    assert m.meta["text"] == "just setting up my twttr" and m.meta["created_at"].startswith("Tue Mar 21")


def test_enrich_x_accepts_new_fxembed_shape(tmp_path):
    new = {"code": 200, "message": "OK", "status": {"id": "20", "text": "hi", "author": {"name": "jack",
                                                                                     "screen_name": "jack"},
                                                     "likes": 5, "reposts": 7, "replies": 1, "created_at": "x"}}
    ctx, _ = make_ctx(tmp_path, lambda r: ok_json(new))
    m = run(enrich_link(ctx, "https://x.com/jack/status/20"))
    assert m.ok and m.meta["retweets"] == 7 and m.meta["likes"] == 5


def test_enrich_x_unreachable_returns_kind_and_link_and_trips_breaker(tmp_path):
    def handler(r):
        raise httpx.ConnectTimeout("timeout", request=r)

    ctx, http = make_ctx(tmp_path, handler)
    m = run(enrich_link(ctx, "https://x.com/jack/status/20"))
    assert not m.ok and m.kind == "x" and m.url == "https://x.com/jack/status/20" and m.meta["id"] == "20"
    m2 = run(enrich_link(ctx, "https://x.com/someone/status/21"))
    assert not m2.ok and "跳过" in m2.error and len(http.requests) == 1     # 同一主机本次运行不再尝试


WECHAT_HTML = """<html><head><meta property="og:title" content="手绘贴图的 7 个技巧" />
<meta property="og:description" content="一篇讲贴图的文章" /><meta name="author" content="青岚" />
<script>var nickname = htmlDecode("创作研究所"); var msg_title = '手绘贴图的 7 个技巧';</script></head>
<body><div class="rich_media"><h1>手绘贴图的 7 个技巧</h1><div id="js_content"><p>第一段正文，共十二个汉字。</p>
<p>Second paragraph has five words.</p><section><p>嵌套的段落</p></section></div>
<div id="js_pc_qr_code">扫码关注</div></div></body></html>"""


def test_enrich_wechat_article(tmp_path):
    ctx, http = make_ctx(tmp_path, lambda r: httpx.Response(200, html=WECHAT_HTML))
    m = run(enrich_link(ctx, "https://mp.weixin.qq.com/s/AbCdEf"))
    assert m.ok and m.kind == "wechat_article" and m.title == "手绘贴图的 7 个技巧"
    assert m.description == "一篇讲贴图的文章" and m.meta["author"] == "青岚" and m.meta["account"] == "创作研究所"
    assert 15 <= m.meta["words"] <= 30                                     # 只统计 js_content 内的字数
    blocked = "<html><head><title>验证</title></head><body>环境异常，完成验证后即可继续访问</body></html>"
    ctx2, _ = make_ctx(tmp_path / "b", lambda r: httpx.Response(200, html=blocked))
    m2 = run(enrich_link(ctx2, "https://mp.weixin.qq.com/s/x"))
    assert not m2.ok and "环境异常" in m2.error


def test_enrich_netdisk_never_requests(tmp_path):
    ctx, http = make_ctx(tmp_path, never)
    m = run(enrich_link(ctx, "https://pan.quark.cn/s/abc，", context_text="https://pan.quark.cn/s/abc 提取码：Ab12"))
    assert m == LinkMeta(url="https://pan.quark.cn/s/abc", kind="netdisk", meta={"provider": "夸克网盘"}, code="Ab12")
    m2 = run(enrich_link(ctx, "https://pan.baidu.com/s/1abc?pwd=x9k2"))
    assert m2.code == "x9k2" and m2.meta["provider"] == "百度网盘" and http.requests == []


def test_enrich_video_doc_and_web_titles(tmp_path):
    def handler(r):
        if r.url.host == "www.youtube.com" and r.url.path == "/oembed":
            return ok_json({"title": "演示视频", "author_name": "频道"})
        if r.url.host == "www.bilibili.com":
            return httpx.Response(200, html="<title>手绘教程_哔哩哔哩_bilibili</title>")
        if r.url.host == "abc.feishu.cn":
            return httpx.Response(200, html="<title>登录</title>")
        return httpx.Response(200, html="<html><head><title> 普通网页 </title>"
                                         "<meta name='description' content='描述'></head></html>")

    ctx, _ = make_ctx(tmp_path, handler)
    yt = run(enrich_link(ctx, "https://youtu.be/abc"))
    assert yt.kind == "video" and yt.title == "演示视频" and yt.meta == {"provider": "YouTube", "author": "频道"}
    bl = run(enrich_link(ctx, "https://www.bilibili.com/video/BV1"))
    assert bl.title == "手绘教程" and bl.meta["provider"] == "B 站"
    fs = run(enrich_link(ctx, "https://abc.feishu.cn/docx/X"))
    assert fs.kind == "doc" and fs.title is None and fs.meta["provider"] == "飞书文档"
    web = run(enrich_link(ctx, "https://example.com/a"))
    assert web.kind == "web" and web.title == "普通网页" and web.description == "描述"
    other = run(enrich_link(ctx, "magnet:?xt=urn:btih:abc"))
    assert other.kind == "other" and other.ok


def test_enrich_ssrf_blocked(tmp_path):
    ctx, http = make_ctx(tmp_path, never)
    for url in ("http://127.0.0.1:8765/api/overview", "http://intranet.example.com/x", "http://169.254.169.254/"):
        m = run(enrich_link(ctx, url))
        assert not m.ok and m.error and m.kind == "web"
    assert http.requests == []


def test_research_context_signature():
    import dataclasses
    names = [f.name for f in dataclasses.fields(ResearchContext)]
    assert names[:9] == ["settings", "secrets", "data_dir", "max_searches", "max_fetches", "used_searches",
                         "used_fetches", "cost_usd", "logger"]
    ctx = ResearchContext(settings={}, secrets={}, data_dir=".", max_searches=1, max_fetches=1)
    assert ctx.used_searches == 0 and ctx.cost_usd == 0.0 and ctx.logger.name == "bureau.research"
    assert json.loads(LinkMeta(url="u", kind="web").model_dump_json())["meta"] == {}
