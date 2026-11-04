"""采集器注册表（懒加载）。由 Lead 维护。"""

from __future__ import annotations

import importlib
import logging

from bureau.collectors.base import Collector, CollectorContext

log = logging.getLogger(__name__)

# 键 -> "模块路径:类名"。键的前缀就是平台。
COLLECTOR_REGISTRY: dict[str, str] = {
    "wechat.wda": "bureau.collectors.wechat_wda:WdaCollector",
    "wechat.weflow": "bureau.collectors.wechat_weflow:WeFlowCollector",
    "wechat.file_import": "bureau.collectors.file_import:FileImportCollector",
    "qq.onebot": "bureau.collectors.qq_onebot:OneBotCollector",
    "qq.file_import": "bureau.collectors.file_import:FileImportCollector",
    "feishu.lark_cli": "bureau.collectors.feishu_lark:LarkCliCollector",
    "feishu.file_import": "bureau.collectors.file_import:FileImportCollector",
    "demo.synthetic": "bureau.collectors.demo:DemoCollector",
}


class CollectorUnavailable(RuntimeError):
    pass


def load_collector_class(key: str) -> type[Collector]:
    try:
        target = COLLECTOR_REGISTRY[key]
    except KeyError as exc:
        raise CollectorUnavailable(f"未知的采集器：{key}") from exc
    module_name, _, class_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise CollectorUnavailable(f"采集器 {key} 尚未实现（缺少模块 {module_name}）") from exc
        raise
    cls = getattr(module, class_name, None)
    if cls is None:
        raise CollectorUnavailable(f"采集器 {key} 的类 {class_name} 不存在")
    return cls


def available_collectors(platform: str | None = None) -> dict[str, type[Collector]]:
    """返回已实现的采集器；缺失的模块会被跳过并记日志。"""
    found: dict[str, type[Collector]] = {}
    for key in COLLECTOR_REGISTRY:
        if platform and not key.startswith(f"{platform}."):
            continue
        try:
            found[key] = load_collector_class(key)
        except CollectorUnavailable as exc:
            log.debug("%s", exc)
    return found


def create_collector(key: str, ctx: CollectorContext) -> Collector:
    return load_collector_class(key)(ctx)


__all__ = [
    "COLLECTOR_REGISTRY",
    "Collector",
    "CollectorContext",
    "CollectorUnavailable",
    "available_collectors",
    "create_collector",
    "load_collector_class",
]
