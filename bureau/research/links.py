"""链接分类（纯规则）、提取码识别与链接增强（GitHub / X / 公众号 / 网盘 / 视频 / 文档 / 其它）。

外部接口（均带 SSRF 防护、15 秒超时、24 小时缓存）：
- GitHub：``GET https://api.github.com/repos/{owner}/{repo}``（可选 ``Authorization: Bearer <github_token>``），
  取 stargazers_count、language、forks_count、description、updated_at、pushed_at、topics。
  未带 token 时每小时 60 次。
- X / Twitter：``GET https://api.fxtwitter.com/{user}/status/{id}`` → ``{code, message, tweet: {text,
  author: {name, screen_name}, likes, retweets, replies, views, created_at, created_timestamp}}``。
- YouTube：``GET https://www.youtube.com/oembed?url=...&format=json`` → ``{title, author_name}``。
- 公众号 / 其它网页：直接 GET 页面，读 og 标签、<title> 和正文。
- 网盘：**不发任何请求**，只识别平台和提取码。
"""

from __future__ import annotations

import contextvars
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from bureau.integrations.htmltext import html_to_markdown
from bureau.integrations.netsafe import FetchError, UnsafeURLError, safe_get
from bureau.research.cache import JsonCache
from bureau.research.models import LinkMeta, ResearchContext
from bureau.research.search import research_settings

ENRICH_TTL = 24 * 3600
TIMEOUT = 15.0
PAGE_MAX_BYTES = 2 * 1024 * 1024
WECHAT_MAX_BYTES = 4 * 1024 * 1024
GITHUB_API = "https://api.github.com/repos/{owner}/{repo}"
FXTWITTER_API = "https://api.fxtwitter.com/{user}/status/{id}"
YOUTUBE_OEMBED = "https://www.youtube.com/oembed?url={url}&format=json"

# ---------------------------------------------------------------- 平台表

NETDISK_HOSTS: dict[str, str] = {
    "pan.quark.cn": "夸克网盘", "drive.uc.cn": "UC 网盘", "fast.uc.cn": "UC 网盘",
    "pan.baidu.com": "百度网盘", "yun.baidu.com": "百度网盘",
    "www.alipan.com": "阿里云盘", "alipan.com": "阿里云盘", "www.aliyundrive.com": "阿里云盘",
    "aliyundrive.com": "阿里云盘",
    "cloud.189.cn": "天翼云盘", "h5.cloud.189.cn": "天翼云盘",
    "www.123pan.com": "123 云盘", "123pan.com": "123 云盘", "www.123pan.cn": "123 云盘", "123pan.cn": "123 云盘",
    "www.123684.com": "123 云盘", "www.123865.com": "123 云盘", "www.123912.com": "123 云盘",
    "www.123592.com": "123 云盘",
    "pan.xunlei.com": "迅雷云盘",
    "115.com": "115 网盘", "115cdn.com": "115 网盘", "anxia.com": "115 网盘",
    "caiyun.139.com": "移动云盘", "yun.139.com": "移动云盘",
    "pan.wo.cn": "联通云盘", "share.weiyun.com": "腾讯微云", "www.weiyun.com": "腾讯微云",
    "yunpan.360.cn": "360 安全云盘", "www.feijipan.com": "小飞机网盘", "www.ilanzou.com": "蓝奏云优享",
    "cowtransfer.com": "奶牛快传", "www.wenshushu.cn": "文叔叔", "mega.nz": "MEGA", "drive.google.com": "Google Drive",
    "1drv.ms": "OneDrive", "onedrive.live.com": "OneDrive", "www.dropbox.com": "Dropbox",
}
_NETDISK_SUFFIX: list[tuple[str, str]] = [
    (".115.com", "115 网盘"), (".115cdn.com", "115 网盘"), (".cowtransfer.com", "奶牛快传"),
    (".lanzoue.com", "蓝奏云"), (".woozooo.com", "蓝奏云"),
]
_LANZOU = re.compile(r"(?:^|\.)lanzou[a-z]?\.com$|(?:^|\.)lanzn\.com$")

VIDEO_HOSTS: dict[str, str] = {
    "bilibili.com": "B 站", "b23.tv": "B 站", "bili2233.cn": "B 站",
    "douyin.com": "抖音", "iesdouyin.com": "抖音",
    "youtube.com": "YouTube", "youtu.be": "YouTube",
    "channels.weixin.qq.com": "视频号", "ixigua.com": "西瓜视频", "kuaishou.com": "快手",
    "v.qq.com": "腾讯视频", "vimeo.com": "Vimeo", "tiktok.com": "TikTok",
}
DOC_HOSTS: dict[str, str] = {
    "feishu.cn": "飞书文档", "larksuite.com": "飞书文档", "larkoffice.com": "飞书文档", "feishu.net": "飞书文档",
    "docs.qq.com": "腾讯文档", "doc.weixin.qq.com": "腾讯文档", "yuque.com": "语雀", "notion.so": "Notion",
    "notion.site": "Notion", "shimo.im": "石墨文档", "kdocs.cn": "金山文档", "docs.google.com": "Google 文档",
    "wolai.com": "我来",
}
_FEISHU_DOC_PATH = re.compile(r"^/(?:docx|docs|doc|wiki|sheets|sheet|base|mindnotes|slides|file|drive|minutes)/", re.I)
X_HOSTS = {"x.com", "twitter.com", "mobile.twitter.com", "mobile.x.com", "fxtwitter.com", "vxtwitter.com",
           "fixupx.com", "fixvx.com", "nitter.net"}
_GITHUB_RESERVED = {"orgs", "settings", "login", "logout", "join", "marketplace", "features", "explore", "topics",
                    "sponsors", "trending", "about", "pricing", "notifications", "new", "search", "collections",
                    "events", "enterprise", "issues", "pulls", "apps", "site", "security", "customer-stories",
                    "codespaces", "copilot", "readme", "team", "users", "organizations", "account"}
_NAME = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})$")
_REPO = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_TRAIL = "，。；;、）)】]》>\"'”’！!？?…,."


# ---------------------------------------------------------------- 分类（纯规则）

def normalize_url(url: str) -> str:
    """去掉首尾空白和中文标点；没有 scheme 的域名补成 https://。不保证合法。"""
    u = str(url or "").strip().strip("<>").rstrip(_TRAIL)
    if not u:
        return ""
    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", u) and re.match(r"^(?:[\w-]+\.)+[a-zA-Z]{2,}(?:[:/?#]|$)", u):
        u = "https://" + u
    return u


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().rstrip(".")
    except ValueError:
        return ""


def _match_host(host: str, table: dict[str, str]) -> str | None:
    for domain, name in table.items():
        if host == domain or host.endswith("." + domain):
            return name
    return None


def netdisk_provider(url: str) -> str | None:
    host = _host(normalize_url(url))
    if not host:
        return None
    if host in NETDISK_HOSTS:
        return NETDISK_HOSTS[host]
    if _LANZOU.search(host):
        return "蓝奏云"
    for suffix, name in _NETDISK_SUFFIX:
        if host.endswith(suffix):
            return name
    if host.endswith(".baidu.com") and urlsplit(normalize_url(url)).path.startswith(("/s/", "/share/")):
        return "百度网盘"
    return None


def github_repo(url: str) -> tuple[str, str] | None:
    """github.com/<owner>/<repo>[/...] → (owner, repo)；不是仓库页面时返回 None。"""
    u = normalize_url(url)
    host = _host(u)
    parts = [p for p in urlsplit(u).path.split("/") if p] if host else []
    if host == "raw.githubusercontent.com" and len(parts) >= 2:
        owner, repo = parts[0], parts[1]
    elif host in ("github.com", "www.github.com") and len(parts) >= 2:
        owner, repo = parts[0], parts[1]
    else:
        return None
    repo = re.sub(r"\.git$", "", repo)
    if owner.lower() in _GITHUB_RESERVED or not _NAME.match(owner) or not _REPO.match(repo) or repo in (".", ".."):
        return None
    return owner, repo


def x_status(url: str) -> tuple[str, str] | None:
    """x.com/<user>/status/<id> → (user, id)。"""
    u = normalize_url(url)
    if _host(u) not in X_HOSTS:
        return None
    m = re.match(r"^/(?:([A-Za-z0-9_]{1,30})|i/web|i)/status(?:es)?/(\d{1,25})(?:[/?#]|$)", urlsplit(u).path)
    if not m:
        return None
    return (m.group(1) or "i"), m.group(2)


def classify_link(url: str) -> str:
    """链接类别：github / x / wechat_article / netdisk / video / doc / web / other。纯规则，不联网。"""
    u = normalize_url(url)
    try:
        parts = urlsplit(u)
    except ValueError:
        return "other"
    if parts.scheme.lower() not in ("http", "https"):
        return "other"
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        return "other"
    path = parts.path or "/"
    if host in ("github.com", "www.github.com", "raw.githubusercontent.com", "gist.github.com"):
        return "github"
    if host in X_HOSTS:
        return "x"
    if host == "mp.weixin.qq.com" and (path.startswith("/s") or path.startswith("/mp/appmsg")):
        return "wechat_article"
    if netdisk_provider(u):
        return "netdisk"
    if host == "weixin.qq.com" and path.startswith("/sph/"):
        return "video"
    if _match_host(host, VIDEO_HOSTS):
        return "video"
    doc = _match_host(host, DOC_HOSTS)
    if doc:
        if doc == "飞书文档" and not _FEISHU_DOC_PATH.match(path):
            return "web"
        return "doc"
    return "web"


def link_provider(url: str) -> str | None:
    """平台中文名（网盘 / 视频 / 文档），其它返回 None。"""
    u = normalize_url(url)
    host = _host(u)
    if host == "weixin.qq.com" and urlsplit(u).path.startswith("/sph/"):
        return "视频号"
    return netdisk_provider(u) or _match_host(host, VIDEO_HOSTS) or _match_host(host, DOC_HOSTS)


# ---------------------------------------------------------------- 提取码

_CODE_PARAMS = ("pwd", "password", "passcode", "code", "extract_code", "access_code", "sharepwd", "pass")
_CODE_TEXT = re.compile(
    r"(?:(?:提取码|访问码|提取密码|分享码|密码|(?<![邀请验证代编号条暗口识维解源乱机注册激活兑换优惠])码)\s*[:：=＝]?"
    r"|(?<![A-Za-z])(?:pwd|passcode|password)\s*[:：=＝])"
    r"\s*[\"“'‘【\[(（]?\s*([A-Za-z0-9]{4,8})(?![A-Za-z0-9])",
    re.I)


def extract_code(url: str, context_text: str = "") -> str | None:
    """网盘提取码：先看 url 的 pwd= 等参数，再看上下文里的「提取码/码/密码：xxxx」。原样返回，不改大小写。"""
    u = normalize_url(url)
    try:
        parts = urlsplit(u)
    except ValueError:
        parts = None
    if parts is not None:
        for src in (parts.query, parts.fragment):
            qs = parse_qs(src or "", keep_blank_values=False)
            for name in _CODE_PARAMS:
                for val in qs.get(name, []):
                    if re.fullmatch(r"[A-Za-z0-9]{3,12}", val.strip()):
                        return val.strip()
    text = str(context_text or "")
    if not text:
        return None
    for needle in dict.fromkeys(x for x in (str(url or "").strip(), u) if x):
        idx = text.find(needle)
        if idx >= 0:
            m = _CODE_TEXT.search(text[idx + len(needle): idx + len(needle) + 160])
            if m:
                return m.group(1)
            break
    found = list(dict.fromkeys(m.group(1) for m in _CODE_TEXT.finditer(text)))
    return found[0] if len(found) == 1 else None


# ---------------------------------------------------------------- 增强

def _cache(ctx: ResearchContext) -> JsonCache:
    return JsonCache(Path(ctx.data_dir) / "cache" / "enrich", ENRICH_TTL)


def _secret(ctx: ResearchContext, key: str) -> str:
    return str(((ctx.secrets or {}).get("research") or {}).get(key) or "").strip()


_NET_CALLS: contextvars.ContextVar[list[int] | None] = contextvars.ContextVar("enrich_net_calls", default=None)


async def _get(ctx: ResearchContext, url: str, *, headers: dict[str, str] | None = None,
               max_bytes: int = PAGE_MAX_BYTES):
    host = _host(url)
    if host in ctx.down_hosts:
        raise FetchError(f"{host} 本次运行中连接失败过，已跳过")
    counter = _NET_CALLS.get()
    if counter is not None:
        counter[0] += 1
    try:
        return await safe_get(url, transport=ctx.transport, resolver=ctx.resolver, timeout=TIMEOUT,
                              max_bytes=max_bytes, headers=headers)
    except FetchError as exc:
        if exc.retryable:          # 超时 / 网络错误：同一主机在本次运行里不再尝试，避免每个链接都等 15 秒
            ctx.down_hosts.add(host)
            ctx.logger.info("链接增强：%s 连接失败（%s），本次运行不再访问该站点", host, exc.message)
        raise


def _json(resp) -> Any:
    try:
        return json.loads(resp.content.decode("utf-8", "replace"))
    except ValueError:
        return None


async def _github(ctx: ResearchContext, url: str) -> LinkMeta:
    repo = github_repo(url)
    if not repo:
        return LinkMeta(url=url, kind="github", title=urlsplit(url).path.strip("/") or "GitHub")
    owner, name = repo
    base = LinkMeta(url=url, kind="github", title=f"{owner}/{name}", meta={"owner": owner, "repo": name})
    if research_settings(ctx).get("github_enrich") is False:
        return base
    headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    token = _secret(ctx, "github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    resp = await _get(ctx, GITHUB_API.format(owner=quote(owner, safe=""), repo=quote(name, safe="")), headers=headers)
    if resp.status == 404:
        return base.model_copy(update={"ok": False, "error": "GitHub 上找不到这个仓库（可能已删除或为私有仓库）"})
    if resp.status in (403, 429):
        hint = "" if token else "，可在 secrets.yaml 的 research.github_token 填写令牌提高额度"
        return base.model_copy(update={"ok": False, "error": f"GitHub 接口限流（HTTP {resp.status}）{hint}"})
    data = _json(resp)
    if resp.status != 200 or not isinstance(data, dict):
        return base.model_copy(update={"ok": False, "error": f"GitHub 接口返回 HTTP {resp.status}"})
    meta = {
        "owner": owner, "repo": name, "full_name": data.get("full_name") or f"{owner}/{name}",
        "stars": data.get("stargazers_count"), "forks": data.get("forks_count"), "language": data.get("language"),
        "updated_at": data.get("updated_at"), "pushed_at": data.get("pushed_at"),
        "topics": list(data.get("topics") or [])[:12], "archived": bool(data.get("archived")),
        "license": ((data.get("license") or {}).get("spdx_id") if isinstance(data.get("license"), dict) else None),
        "homepage": data.get("homepage") or None,
    }
    return LinkMeta(url=url, kind="github", title=str(data.get("full_name") or f"{owner}/{name}"),
                    description=(str(data.get("description") or "").strip() or None),
                    meta={k: v for k, v in meta.items() if v is not None and v != "" and v != []})


async def _x(ctx: ResearchContext, url: str) -> LinkMeta:
    st = x_status(url)
    if not st:
        return LinkMeta(url=url, kind="x", title=None)
    user, tid = st
    base = LinkMeta(url=url, kind="x", title=f"@{user}" if user != "i" else None, meta={"id": tid})
    if research_settings(ctx).get("x_enrich") is False:
        return base
    resp = await _get(ctx, FXTWITTER_API.format(user=quote(user, safe=""), id=tid),
                      headers={"Accept": "application/json"})
    data = _json(resp)
    # 旧版接口返回 {code, message, tweet: {..., retweets}}；FxEmbed 新版 schema 是 {code, status: {..., reposts}}
    tweet = (data.get("tweet") or data.get("status")) if isinstance(data, dict) else None
    if resp.status != 200 or not isinstance(tweet, dict):
        msg = str((data or {}).get("message") or "") if isinstance(data, dict) else ""
        return base.model_copy(update={"ok": False, "error": f"读取推文失败（HTTP {resp.status}{'，' + msg[:40] if msg else ''}）"})
    author = tweet.get("author") if isinstance(tweet.get("author"), dict) else {}
    handle = str(author.get("screen_name") or user)
    text = str(tweet.get("text") or "").strip()
    if not text and isinstance(tweet.get("raw_text"), dict):
        text = str(tweet["raw_text"].get("text") or "").strip()
    meta = {"id": tid, "author": author.get("name"), "screen_name": handle, "text": text,
            "likes": tweet.get("likes"),
            "retweets": tweet.get("retweets") if tweet.get("retweets") is not None else tweet.get("reposts"),
            "replies": tweet.get("replies"),
            "views": tweet.get("views"), "created_at": tweet.get("created_at"),
            "created_timestamp": tweet.get("created_timestamp"), "lang": tweet.get("lang")}
    snippet = re.sub(r"\s+", " ", text)[:60]
    return LinkMeta(url=url, kind="x", title=f"@{handle}：{snippet}" if snippet else f"@{handle}",
                    description=text or None, meta={k: v for k, v in meta.items() if v not in (None, "")})


def _word_count(md: str) -> int:
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md or "")
    cjk = len(re.findall(r"[㐀-鿿豈-﫿]", text))
    latin = len(re.findall(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*", text))
    return cjk + latin


_WX_BLOCK = ("环境异常", "完成验证后即可继续访问", "该内容已被发布者删除", "此内容因违规无法查看", "该公众号已迁移")


async def _wechat(ctx: ResearchContext, url: str) -> LinkMeta:
    resp = await _get(ctx, url, max_bytes=WECHAT_MAX_BYTES)
    if resp.status >= 400:
        return LinkMeta(url=url, kind="wechat_article", ok=False, error=f"公众号页面返回 HTTP {resp.status}")
    page = resp.text()
    doc = html_to_markdown(page, root_id="js_content")
    has_body = 'id="js_content"' in page or "id='js_content'" in page
    title = (doc.meta.get("og:title") or doc.meta.get("twitter:title") or doc.meta.get("wx:msg_title")
             or doc.title or "").strip() or None
    if not has_body:
        reason = next((w for w in _WX_BLOCK if w in page), None)
        return LinkMeta(url=url, kind="wechat_article", title=title, ok=False,
                        error=f"公众号页面无法读取正文（{reason or '可能需要验证或文章已删除'}）")
    author = (doc.meta.get("og:article:author") or doc.meta.get("author") or doc.meta.get("wx:author") or "").strip()
    account = (doc.meta.get("wx:nickname") or doc.meta.get("og:site_name") or "").strip()
    desc = (doc.meta.get("og:description") or doc.meta.get("description") or doc.meta.get("wx:msg_desc") or "").strip()
    meta = {"author": author or account or None, "account": account or None, "words": _word_count(doc.markdown)}
    if resp.truncated:
        meta["words_note"] = "页面过大，字数只统计了前 4 MB"
    return LinkMeta(url=url, kind="wechat_article", title=title, description=desc or None,
                    meta={k: v for k, v in meta.items() if v not in (None, "")})


_TITLE_SUFFIX = re.compile(r"(?:_哔哩哔哩_bilibili| - YouTube| - 抖音|_抖音| - 飞书云文档| - 飞书文档| · 语雀|"
                           r" - 腾讯文档|_腾讯文档)\s*$")
_LOGIN_TITLES = {"登录", "飞书", "Feishu", "Lark", "腾讯文档", "语雀", "抖音", "Sign in", "Log in"}


async def _page_meta(ctx: ResearchContext, url: str, kind: str) -> LinkMeta:
    provider = link_provider(url)
    base_meta = {"provider": provider} if provider else {}
    if kind == "video" and _match_host(_host(url), {"youtube.com": "y", "youtu.be": "y"}):
        resp = await _get(ctx, YOUTUBE_OEMBED.format(url=quote(url, safe="")), headers={"Accept": "application/json"})
        data = _json(resp)
        if resp.status == 200 and isinstance(data, dict) and data.get("title"):
            return LinkMeta(url=url, kind="video", title=str(data["title"]),
                            meta=base_meta | {k: v for k, v in (("author", data.get("author_name")),) if v})
    resp = await _get(ctx, url)
    if resp.status >= 400:
        return LinkMeta(url=url, kind=kind, meta=base_meta, ok=False, error=f"网页返回 HTTP {resp.status}")
    ctype = resp.content_type
    if ctype and "html" not in ctype and "xml" not in ctype:
        return LinkMeta(url=url, kind=kind, meta=base_meta | {"content_type": ctype})
    doc = html_to_markdown(resp.text())
    title = (doc.meta.get("og:title") or doc.meta.get("twitter:title") or doc.title or "").strip()
    title = _TITLE_SUFFIX.sub("", title).strip()
    if title in _LOGIN_TITLES:
        title = ""
    desc = (doc.meta.get("og:description") or doc.meta.get("description") or "").strip()
    return LinkMeta(url=url, kind=kind, title=title or None, description=desc[:300] or None,
                    meta=base_meta | ({"final_url": resp.url} if resp.url != url else {}))


def _offline_meta(url: str, kind: str) -> LinkMeta:
    """不联网能从链接本身得到的信息（联网失败时返回它）。"""
    if kind == "github" and (repo := github_repo(url)):
        return LinkMeta(url=url, kind="github", title=f"{repo[0]}/{repo[1]}", meta={"owner": repo[0], "repo": repo[1]})
    if kind == "x" and (st := x_status(url)):
        return LinkMeta(url=url, kind="x", title=f"@{st[0]}" if st[0] != "i" else None,
                        meta={"id": st[1]} | ({"screen_name": st[0]} if st[0] != "i" else {}))
    provider = link_provider(url)
    return LinkMeta(url=url, kind=kind, meta={"provider": provider} if provider else {})  # type: ignore[arg-type]


async def enrich_link(ctx: ResearchContext, url: str, *, context_text: str = "") -> LinkMeta:
    """识别链接类别并补充元数据。不抛异常：失败时 ok=False，error 为中文。"""
    u = normalize_url(url)
    kind = classify_link(u)
    if kind == "netdisk":
        return LinkMeta(url=u, kind="netdisk", meta={"provider": netdisk_provider(u)},
                        code=extract_code(u, context_text) or extract_code(url, context_text))
    if kind == "other" or not u:
        return LinkMeta(url=u or str(url or ""), kind="other")
    cache = _cache(ctx)
    ckey = f"enrich|{u}"
    cached = cache.get(ckey)
    if isinstance(cached, dict):
        try:
            return LinkMeta(**cached)
        except (TypeError, ValueError):
            pass
    counter = [0]
    token = _NET_CALLS.set(counter)
    try:
        if kind == "github":
            meta = await _github(ctx, u)
        elif kind == "x":
            meta = await _x(ctx, u)
        elif kind == "wechat_article":
            meta = await _wechat(ctx, u)
        else:
            meta = await _page_meta(ctx, u, kind)
    except UnsafeURLError as exc:
        ctx.logger.info("链接增强已拒绝：%s", exc)
        return _offline_meta(u, kind).model_copy(update={"ok": False, "error": str(exc)})
    except FetchError as exc:
        return _offline_meta(u, kind).model_copy(update={"ok": False, "error": exc.message})
    except Exception as exc:  # noqa: BLE001 — 约定不抛异常
        ctx.logger.warning("链接增强出错（%s）：%s", kind, type(exc).__name__)
        return LinkMeta(url=u, kind=kind, ok=False, error=f"链接增强出错（{type(exc).__name__}）")  # type: ignore[arg-type]
    finally:
        _NET_CALLS.reset(token)
    # 只缓存真正联网拿到的结果（关闭增强或无法解析链接时不缓存，以免之后打开开关也拿不到数据）
    if counter[0] and (meta.ok or (kind == "github" and meta.error and "找不到" in meta.error)):
        cache.set(ckey, meta.model_dump())
    return meta
