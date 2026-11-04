"""安全工具：Host 校验、令牌校验、密钥掩码、回环地址判断、日志脱敏。"""

from __future__ import annotations

import hmac
import ipaddress
import re
from typing import Any, Iterable

MASK = "••••"


def allowed_hosts(port: int, extra: Iterable[str] = ()) -> set[str]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    hosts.update(h.strip().lower() for h in extra if h and h.strip())
    return hosts


def host_allowed(host_header: str | None, port: int, extra: Iterable[str] = ()) -> bool:
    """只接受 127.0.0.1:<port> 和 localhost:<port>，防 DNS 重绑定。"""
    if not host_header:
        return False
    return host_header.strip().lower() in allowed_hosts(port, extra)


def token_ok(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def mask_secret(value: Any) -> str:
    """密钥掩码：``"••••末4位"``；短于 8 位只显示 ``"••••"``；空值返回空串。"""
    if value is None:
        return ""
    s = str(value)
    if not s:
        return ""
    if is_masked(s):
        return s
    return MASK + s[-4:] if len(s) >= 8 else MASK


def is_masked(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(MASK)


def is_unchanged_secret(value: Any) -> bool:
    """PUT 时空串或掩码表示"不修改"。"""
    return value is None or (isinstance(value, str) and (not value.strip() or is_masked(value)))


def mask_tree(obj: Any) -> Any:
    """把嵌套结构里所有叶子值都替换成掩码（用于展示 secrets）。"""
    if isinstance(obj, dict):
        return {k: mask_tree(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_tree(v) for v in obj]
    if obj is None or obj == "":
        return ""
    if isinstance(obj, bool):
        return obj
    return mask_secret(obj)


def is_loopback(host: str | None) -> bool:
    if not host:
        return False
    if host in ("localhost", "testclient"):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


_TOKEN_QS = re.compile(r"(token=)[^&\s]+", re.I)


def redact_text(text: str, secrets: Iterable[str]) -> str:
    """把已知密钥值和 URL 里的 token 参数替换成掩码。"""
    out = text
    for s in secrets:
        if s and len(s) >= 6 and s in out:
            out = out.replace(s, MASK)
    return _TOKEN_QS.sub(r"\1" + MASK, out)
