"""research 的小型 JSON 文件缓存：一个键一个文件，带过期时间，原子写入。"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any


class JsonCache:
    def __init__(self, root: Path, ttl_seconds: float) -> None:
        self.root = Path(root)
        self.ttl = float(ttl_seconds)

    def _path(self, key: str) -> Path:
        return self.root / (hashlib.sha256(key.encode("utf-8")).hexdigest()[:32] + ".json")

    def get(self, key: str) -> Any | None:
        try:
            doc = json.loads(self._path(key).read_text("utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(doc, dict) or doc.get("key") != key:
            return None
        ttl = float(doc.get("ttl") or self.ttl)
        if time.time() - float(doc.get("ts") or 0) > ttl:
            return None
        return doc.get("data")

    def set(self, key: str, data: Any, *, ttl_seconds: float | None = None) -> None:
        """写入失败只放弃缓存，不影响调用方。"""
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.root, prefix=".c-", suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"key": key, "ts": time.time(), "ttl": ttl_seconds or self.ttl, "data": data},
                          fh, ensure_ascii=False)
            os.replace(tmp, self._path(key))
        except (OSError, TypeError, ValueError):
            try:
                os.unlink(tmp)  # type: ignore[possibly-undefined]
            except (OSError, NameError, UnboundLocalError):
                pass
