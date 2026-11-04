"""对外 HTTP 请求的 SSRF 防护：只允许 http/https，目标必须是公网地址，重定向逐跳复查，限时限量。

research（网页抓取、链接增强）和 media（按 URL 下载图片 / 文件）共用。

规则：
- 只允许 http / https，URL 里不得带用户名密码。
- 主机名：拒绝 localhost、*.local / *.internal 等内网后缀、单段主机名、非标准写法的数字 IP（如 0x7f.1）。
- IP（字面量或 DNS 解析结果）：只要有一个不是全局单播地址（回环、私网、链路本地、CGNAT、保留、组播、
  未指定等）就拒绝；IPv4 映射 / 6to4 / NAT64 形式的 IPv6 先还原成 IPv4 再判断。
- 重定向不交给 httpx 自动跟随：每一跳都重新校验，跨主机时去掉 Authorization。
- 整条请求链共用一个总超时；正文边读边计数，超过上限截断或报错（解压后的大小）。

已知限制：校验时和真正连接时各做一次 DNS 解析，理论上存在 DNS rebinding 窗口；走系统代理时
实际连接由代理发起。这两种情况都需要攻击者控制域名解析，且只影响"公网域名指向内网"这一类。
"""

from __future__ import annotations

import asyncio
import ipaddress
import re
import socket
from dataclasses import dataclass
from typing import Awaitable, Callable, Literal
from urllib.parse import urljoin, urlsplit

import httpx

Resolver = Callable[[str, int], Awaitable[list[str]]]

DEFAULT_TIMEOUT = 15.0
DEFAULT_MAX_BYTES = 2 * 1024 * 1024
MAX_REDIRECTS = 5
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/130.0 Safari/537.36")
_BLOCKED_SUFFIXES = (".localhost", ".local", ".localdomain", ".internal", ".intranet", ".lan", ".home",
                     ".corp", ".home.arpa", ".in-addr.arpa", ".ip6.arpa")
_NUMERIC_LABEL = re.compile(r"0x[0-9a-f]*|\d+")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_REDIRECT_CODES = {301, 302, 303, 307, 308}


class UnsafeURLError(ValueError):
    """URL 不允许访问（非 http/https、指向本机或内网等）。str(exc) 是中文说明。"""


class HostResolveError(UnsafeURLError):
    """域名解析失败（不一定是不安全，只是无法确认）。"""


class FetchError(Exception):
    """请求失败（网络、超时、超过大小上限、重定向过多）。message 是中文。"""

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = False) -> None:
        super().__init__(message)
        self.message = message
        self.status = status
        self.retryable = retryable


async def system_resolver(host: str, port: int) -> list[str]:
    loop = asyncio.get_running_loop()
    infos = await loop.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return list(dict.fromkeys(str(i[4][0]) for i in infos))


def ip_blocked(value: str) -> bool:
    """True 表示该 IP 不是可以访问的公网地址。无法解析的字符串也视为不允许。"""
    try:
        ip = ipaddress.ip_address(str(value).split("%", 1)[0].strip("[]"))
    except ValueError:
        return True
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped
        elif ip.sixtofour is not None:
            ip = ip.sixtofour
        elif ip in _NAT64:
            ip = ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return (not ip.is_global or ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast
            or ip.is_reserved or ip.is_unspecified)


def _literal_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(host.strip("[]").split("%", 1)[0])
    except ValueError:
        return None


def check_url_static(url: str) -> tuple[str, str, int]:
    """不做 DNS 的静态检查，返回 (url, host, port)；不允许时抛 UnsafeURLError。"""
    if not isinstance(url, str) or not url.strip():
        raise UnsafeURLError("链接为空")
    url = url.strip()
    if len(url) > 8192:
        raise UnsafeURLError("链接过长")
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        raise UnsafeURLError("链接格式不正确") from None
    scheme = (parts.scheme or "").lower()
    if scheme not in ("http", "https"):
        raise UnsafeURLError("只允许访问 http / https 链接")
    if parts.username or parts.password or "@" in (parts.netloc or ""):
        raise UnsafeURLError("链接里不允许带用户名或密码")
    host = (parts.hostname or "").rstrip(".").lower()
    if not host:
        raise UnsafeURLError("链接缺少主机名")
    lit = _literal_ip(host)
    if lit is None:
        if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES) or "." not in host:
            raise UnsafeURLError("不允许访问本机或内网主机名")
        if all(_NUMERIC_LABEL.fullmatch(lbl) for lbl in host.split(".") if lbl):
            raise UnsafeURLError("不允许非标准写法的 IP 地址")
    elif ip_blocked(str(lit)):
        raise UnsafeURLError("不允许访问本机、内网或保留地址")
    return url, host, port or (443 if scheme == "https" else 80)


async def check_url(url: str, *, resolver: Resolver | None = None, dns_timeout: float = 8.0) -> str:
    """完整检查（含 DNS 解析结果），返回去掉首尾空白的 URL；不允许时抛 UnsafeURLError。"""
    url, host, port = check_url_static(url)
    if _literal_ip(host) is not None:
        return url
    try:
        ips = await asyncio.wait_for((resolver or system_resolver)(host, port), dns_timeout)
    except (OSError, asyncio.TimeoutError, UnicodeError, ValueError):
        raise HostResolveError("域名解析失败") from None
    if not ips:
        raise HostResolveError("域名解析失败")
    if any(ip_blocked(ip) for ip in ips):
        raise UnsafeURLError("该域名解析到本机、内网或保留地址，已拒绝访问")
    return url


@dataclass
class SafeResponse:
    url: str                    # 跟随重定向后的最终地址
    status: int
    headers: httpx.Headers
    content: bytes
    truncated: bool = False

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").split(";", 1)[0].strip().lower()

    def text(self) -> str:
        return decode_text(self.content, self.headers.get("content-type"))


_CHARSET_ALIASES = {"gb2312": "gb18030", "gbk": "gb18030", "x-gbk": "gb18030", "utf8": "utf-8"}


def decode_text(content: bytes, content_type: str | None = None) -> str:
    """按 Content-Type / <meta charset> 解码，失败时依次尝试 utf-8、gb18030。"""
    charset = None
    m = re.search(r"charset=[\"']?([\w.-]+)", content_type or "", re.I)
    if m:
        charset = m.group(1)
    if not charset:
        head = content[:4096].decode("ascii", "ignore")
        m = re.search(r"<meta[^>]+charset=[\"']?([\w.-]+)", head, re.I)
        if m:
            charset = m.group(1)
    tried = []
    for enc in (charset, "utf-8", "gb18030"):
        if not enc:
            continue
        enc = _CHARSET_ALIASES.get(enc.lower(), enc.lower())
        if enc in tried:
            continue
        tried.append(enc)
        try:
            return content.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode("utf-8", "replace")


async def safe_get(url: str, *, transport: httpx.AsyncBaseTransport | None = None,
                   resolver: Resolver | None = None, timeout: float = DEFAULT_TIMEOUT,
                   max_bytes: int = DEFAULT_MAX_BYTES, headers: dict[str, str] | None = None,
                   max_redirects: int = MAX_REDIRECTS,
                   oversize: Literal["truncate", "error"] = "truncate") -> SafeResponse:
    """带 SSRF 防护的 GET。不安全时抛 UnsafeURLError，网络/超时/超限抛 FetchError。"""
    try:
        async with asyncio.timeout(timeout):
            return await _get_chain(url, transport=transport, resolver=resolver, timeout=timeout,
                                    max_bytes=max_bytes, headers=headers or {}, max_redirects=max_redirects,
                                    oversize=oversize)
    except TimeoutError:
        raise FetchError(f"请求超时（{timeout:g} 秒）", retryable=True) from None


async def _get_chain(url: str, *, transport, resolver, timeout: float, max_bytes: int, headers: dict[str, str],
                     max_redirects: int, oversize: str) -> SafeResponse:
    hdrs = {"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6"}
    hdrs.update(headers)
    current = url
    first_host = (urlsplit(url.strip()).hostname or "").lower()
    async with httpx.AsyncClient(transport=transport, timeout=httpx.Timeout(timeout, connect=min(timeout, 8.0)),
                                 follow_redirects=False) as client:
        for _hop in range(max_redirects + 1):
            current = await check_url(current, resolver=resolver)
            req_headers = dict(hdrs)
            if (urlsplit(current).hostname or "").lower() != first_host:
                req_headers = {k: v for k, v in req_headers.items() if k.lower() != "authorization"}
            try:
                async with client.stream("GET", current, headers=req_headers) as resp:
                    location = resp.headers.get("location")
                    if resp.status_code in _REDIRECT_CODES and location:
                        current = urljoin(current, location.strip())
                        continue
                    declared = resp.headers.get("content-length")
                    if oversize == "error" and declared and declared.isdigit() and int(declared) > max_bytes:
                        raise FetchError(f"文件超过大小上限（{max_bytes // 1024} KB）", status=resp.status_code)
                    buf = bytearray()
                    truncated = False
                    async for chunk in resp.aiter_bytes():
                        buf += chunk
                        if len(buf) > max_bytes:
                            if oversize == "error":
                                raise FetchError(f"文件超过大小上限（{max_bytes // 1024} KB）",
                                                 status=resp.status_code)
                            del buf[max_bytes:]
                            truncated = True
                            break
                    return SafeResponse(url=current, status=resp.status_code, headers=resp.headers,
                                        content=bytes(buf), truncated=truncated)
            except httpx.TimeoutException:
                raise FetchError("连接或读取超时", retryable=True) from None
            except httpx.HTTPError as exc:
                raise FetchError(f"网络错误（{type(exc).__name__}）", retryable=True) from None
    raise FetchError(f"重定向次数超过 {max_redirects} 次")
