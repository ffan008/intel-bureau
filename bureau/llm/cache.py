"""LLM 结果缓存：data/cache/llm/<sha256>.json。"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def cache_key(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(json.dumps(p, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
        h.update(b"\x1f")
    return h.hexdigest()


class LLMCache:
    def __init__(self, directory: Path, enabled: bool = True) -> None:
        self.dir = directory
        self.enabled = enabled
        if enabled:
            self.dir.mkdir(parents=True, exist_ok=True)

    def get(self, key: str) -> dict[str, Any] | None:
        if not self.enabled:
            return None
        p = self.dir / f"{key}.json"
        if not p.exists():
            return None
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def put(self, key: str, obj: dict[str, Any]) -> None:
        if not self.enabled:
            return
        p = self.dir / f"{key}.json"
        tmp = p.with_suffix(f".{os.getpid()}.tmp")
        try:
            tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, p)
        except OSError:
            pass
