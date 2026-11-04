"""media 的数据类型（签名按 docs/V2_KNOWLEDGE.md §5）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class MediaResult(BaseModel):
    ok: bool
    kind: Literal["image", "file", "video"]
    path: str | None = None
    filename: str | None = None
    mime: str | None = None
    size: int | None = None
    width: int | None = None
    height: int | None = None
    sha256: str | None = None
    error: str | None = None
