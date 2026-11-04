"""链接分类：优先用 B2 的 bureau.research.classify_link（纯规则，同步）；模块还没装好时用这里的本地规则兜底。"""

from __future__ import annotations

import re
from urllib.parse import urlparse

from bureau.core.constants import LINK_KINDS
from bureau.pipeline.b2 import research_api

_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("github", ("github.com", "gist.github.com")),
    ("x", ("x.com", "twitter.com", "mobile.twitter.com")),
    ("wechat_article", ("mp.weixin.qq.com",)),
    ("netdisk", ("pan.baidu.com", "yun.baidu.com", "aliyundrive.com", "alipan.com", "pan.quark.cn", "cloud.189.cn",
                 "lanzou", "123pan.com", "123684.com", "pan.xunlei.com", "weiyun.com", "share.weiyun.com")),
    ("video", ("bilibili.com", "b23.tv", "youtube.com", "youtu.be", "douyin.com", "v.douyin.com", "ixigua.com",
               "channels.weixin.qq.com", "kuaishou.com", "vimeo.com")),
    ("doc", ("docs.qq.com", "feishu.cn/docx", "feishu.cn/wiki", "larksuite.com", "notion.so", "notion.site",
             "yuque.com", "shimo.im", "docs.google.com", "kdocs.cn")),
]
_DOC_EXT = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|md|txt|csv)(?:$|[?#])", re.I)


def classify_local(url: str) -> str:
    try:
        p = urlparse(url.strip())
    except ValueError:
        return "other"
    if p.scheme not in ("http", "https") or not p.netloc:
        return "other"
    host = p.netloc.lower().split("@")[-1].split(":")[0]
    target = host + p.path.lower()
    for kind, needles in _RULES:
        for n in needles:
            if "/" in n:
                if n in target:
                    return kind
            elif host == n or host.endswith("." + n) or (n == "lanzou" and "lanzou" in host):
                return kind
    if _DOC_EXT.search(p.path):
        return "doc"
    return "web"


_NETDISK = {"pan.baidu.com": "百度网盘", "yun.baidu.com": "百度网盘", "pan.quark.cn": "夸克网盘", "aliyundrive.com": "阿里云盘",
            "alipan.com": "阿里云盘", "cloud.189.cn": "天翼云盘", "123pan.com": "123 云盘", "123684.com": "123 云盘",
            "pan.xunlei.com": "迅雷云盘", "weiyun.com": "微云", "share.weiyun.com": "微云"}


def default_title(url: str, kind: str) -> str:
    """链接没有标题时的显示名（只从地址推出来，不编造）：GitHub 显示 owner/repo，网盘显示平台名。"""
    try:
        p = urlparse(url)
    except ValueError:
        return url
    host = p.netloc.lower().split(":")[0]
    parts = [x for x in p.path.split("/") if x]
    if kind == "github" and len(parts) >= 2:
        return f"{parts[0]}/{parts[1]}"
    if kind == "x" and parts:
        return f"X · @{parts[0]}"
    if kind == "netdisk":
        return next((v for k, v in _NETDISK.items() if host == k or host.endswith("." + k)),
                    "蓝奏云" if "lanzou" in host else "网盘") + " 分享"
    if kind == "wechat_article":
        return "公众号文章"
    return host.removeprefix("www.") + ("/" + parts[0] if parts and kind in ("doc", "video") else "")


def netdisk_provider(url: str) -> str | None:
    host = urlparse(url).netloc.lower().split(":")[0]
    return next((v for k, v in _NETDISK.items() if host == k or host.endswith("." + k)),
                "蓝奏云" if "lanzou" in host else None)


def classify(url: str) -> str:
    mod, _why = research_api()
    if mod is not None and hasattr(mod, "classify_link"):
        try:
            k = str(mod.classify_link(url))
            if k in LINK_KINDS:
                return k
        except Exception:                                            # noqa: BLE001  B2 的规则出错时用本地规则
            pass
    return classify_local(url)
