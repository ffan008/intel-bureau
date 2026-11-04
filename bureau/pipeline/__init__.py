"""情报流水线：12 个阶段（collect → … → archive）。"""

from __future__ import annotations

from typing import Awaitable, Callable

from bureau.pipeline import (archive, clean, collect, compose, deliver, extract, merge, render, score, segment, stats,
                             verify)

STAGE_FUNCS: dict[str, Callable[..., Awaitable]] = {
    "collect": collect.run, "clean": clean.run, "stats": stats.run, "segment": segment.run,
    "extract": extract.run, "merge": merge.run, "score": score.run, "verify": verify.run,
    "compose": compose.run, "render": render.run, "deliver": deliver.run, "archive": archive.run,
}

__all__ = ["STAGE_FUNCS"]
