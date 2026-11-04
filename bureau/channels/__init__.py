"""推送通道注册表（懒加载）。由 Lead 维护。"""

from __future__ import annotations

import importlib
import logging

from bureau.channels.base import Channel, ChannelContext, split_text

log = logging.getLogger(__name__)

CHANNEL_REGISTRY: dict[str, str] = {
    "feishu_webhook": "bureau.channels.feishu_webhook:FeishuWebhookChannel",
    "feishu_app": "bureau.channels.feishu_app:FeishuAppChannel",
    "feishu_doc": "bureau.channels.feishu_doc:FeishuDocChannel",
    "wecom_webhook": "bureau.channels.wecom_webhook:WecomWebhookChannel",
    "serverchan": "bureau.channels.serverchan:ServerChanChannel",
    "pushplus": "bureau.channels.pushplus:PushPlusChannel",
    "wxpusher": "bureau.channels.wxpusher:WxPusherChannel",
    "qq_onebot": "bureau.channels.qq_onebot:QQOneBotChannel",
    "email_smtp": "bureau.channels.email_smtp:EmailSmtpChannel",
    "local_archive": "bureau.channels.local_archive:LocalArchiveChannel",
}


class ChannelUnavailable(RuntimeError):
    pass


def load_channel_class(kind: str) -> type[Channel]:
    try:
        target = CHANNEL_REGISTRY[kind]
    except KeyError as exc:
        raise ChannelUnavailable(f"未知的推送通道类型：{kind}") from exc
    module_name, _, class_name = target.partition(":")
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        if exc.name == module_name:
            raise ChannelUnavailable(f"通道 {kind} 尚未实现（缺少模块 {module_name}）") from exc
        raise
    cls = getattr(module, class_name, None)
    if cls is None:
        raise ChannelUnavailable(f"通道 {kind} 的类 {class_name} 不存在")
    return cls


def available_channels() -> dict[str, type[Channel]]:
    found: dict[str, type[Channel]] = {}
    for kind in CHANNEL_REGISTRY:
        try:
            found[kind] = load_channel_class(kind)
        except ChannelUnavailable as exc:
            log.debug("%s", exc)
    return found


def create_channel(kind: str, ctx: ChannelContext) -> Channel:
    return load_channel_class(kind)(ctx)


__all__ = [
    "CHANNEL_REGISTRY",
    "Channel",
    "ChannelContext",
    "ChannelUnavailable",
    "available_channels",
    "create_channel",
    "load_channel_class",
    "split_text",
]
