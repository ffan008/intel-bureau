"""multipart/form-data 解析（标准库实现，避免为一个导入接口新增依赖）。"""

from __future__ import annotations

from email import policy
from email.parser import BytesParser
from typing import Any


def parse_multipart(content_type: str, body: bytes) -> tuple[dict[str, str], dict[str, tuple[str | None, bytes]]]:
    """返回 (普通字段, 文件字段 {name: (filename, bytes)})。"""
    raw = b"Content-Type: " + content_type.encode("latin-1") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    msg: Any = BytesParser(policy=policy.HTTP).parsebytes(raw)
    fields: dict[str, str] = {}
    files: dict[str, tuple[str | None, bytes]] = {}
    if not msg.is_multipart():
        return fields, files
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        if filename is not None:
            files[str(name)] = (_fix_name(filename), payload)
        else:
            charset = part.get_content_charset() or "utf-8"
            fields[str(name)] = payload.decode(charset, errors="replace")
    return fields, files


def _fix_name(name: str) -> str:
    """浏览器直接发 UTF-8 文件名时，email 解析器会按 latin-1/代理字符解码，这里还原。"""
    try:
        return name.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            return name.encode("utf-8", "surrogateescape").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return name
