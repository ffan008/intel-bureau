"""懒加载 B2 的 bureau.research / bureau.media（docs/V2_KNOWLEDGE.md §5）。

两个模块可能还没写完或依赖缺失：导入失败时返回 (None, 原因)，调用方跳过对应的子步骤并打日志，流水线照常跑完。
导入结果按进程缓存；测试可以 monkeypatch sys.modules 后调用 reset() 注入假模块。
"""

from __future__ import annotations

import importlib
import logging
from types import ModuleType
from typing import Any

log = logging.getLogger("bureau.pipeline.b2")

RESEARCH_ATTRS = ("ResearchContext", "web_search", "fetch_page", "enrich_link")
MEDIA_ATTRS = ("fetch_media", "ocr_image", "extract_document")
_CACHE: dict[str, tuple[ModuleType | None, str]] = {}


def reset() -> None:
    _CACHE.clear()


def _load(name: str, attrs: tuple[str, ...]) -> tuple[ModuleType | None, str]:
    if name in _CACHE:
        return _CACHE[name]
    try:
        mod = importlib.import_module(name)
    except ImportError as exc:
        res: tuple[ModuleType | None, str] = (None, f"模块 {name} 不可用（{exc}）")
    except Exception as exc:                                         # noqa: BLE001  模块自身出错也不能拖垮流水线
        log.warning("加载 %s 出错：%s", name, exc)
        res = (None, f"模块 {name} 加载出错（{exc}）")
    else:
        if mod is None:
            res = (None, f"模块 {name} 不可用")
        else:
            missing = [a for a in attrs if not hasattr(mod, a)]
            res = (mod, "") if not missing else (None, f"模块 {name} 缺少 {'、'.join(missing)}")
    _CACHE[name] = res
    return res


def research_api() -> tuple[ModuleType | None, str]:
    return _load("bureau.research", RESEARCH_ATTRS)


def media_api() -> tuple[ModuleType | None, str]:
    return _load("bureau.media", MEDIA_ATTRS)


def scoped_secrets(secrets: dict[str, Any], *sections: str) -> dict[str, Any]:
    """只把需要的密钥段交给 B2（最小权限）：例如 research 段，以及复用的 llm.openai_compat。"""
    out: dict[str, Any] = {}
    for s in sections:
        head, _, rest = s.partition(".")
        val = secrets.get(head)
        if rest:
            val = (val or {}).get(rest) if isinstance(val, dict) else None
            if val is not None:
                out.setdefault(head, {})[rest] = val
        elif val is not None:
            out[head] = val
    return out
