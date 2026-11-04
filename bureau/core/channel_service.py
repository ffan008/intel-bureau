"""推送通道服务：通道类型、配置拆分（非密钥进数据库，密钥进 secrets.yaml）、构造与投递。"""

from __future__ import annotations

import asyncio
import logging
import secrets as _secrets
from typing import Any

from bureau.channels import CHANNEL_REGISTRY, ChannelUnavailable, load_channel_class
from bureau.channels.base import Channel, ChannelContext
from bureau.contracts import DeliveryResult, ReportPayload
from bureau.core.constants import CHANNEL_FALLBACK_LABELS
from bureau.core.dto import channel_dto
from bureau.core.security import is_unchanged_secret, mask_secret

log = logging.getLogger("bureau.channels")
_SECRET_HINTS = ("token", "secret", "key", "password", "passwd", "webhook", "sendkey", "spt")


def kind_info(kind: str) -> dict[str, Any]:
    label, plabel = CHANNEL_FALLBACK_LABELS.get(kind, (kind, "其他"))
    try:
        cls = load_channel_class(kind)
        return {"kind": kind, "label": getattr(cls, "label", label), "platform_label": getattr(cls, "platform_label", plabel),
                "config_schema": [f.model_dump(exclude_none=True) for f in cls.config_schema()], "available": True}
    except ChannelUnavailable as exc:
        return {"kind": kind, "label": f"{label}（未实现）", "platform_label": plabel, "config_schema": [],
                "available": False, "detail": str(exc)}
    except Exception as exc:                                          # noqa: BLE001
        log.warning("加载通道 %s 出错：%s", kind, exc)
        return {"kind": kind, "label": f"{label}（加载失败）", "platform_label": plabel, "config_schema": [],
                "available": False, "detail": f"通道 {kind} 加载失败：{exc}"}


def list_kinds() -> list[dict[str, Any]]:
    return [kind_info(k) for k in CHANNEL_REGISTRY]


def _types(kind: str) -> dict[str, str]:
    try:
        return {f.key: f.type for f in load_channel_class(kind).config_schema()}
    except Exception:                                                 # noqa: BLE001
        return {}


def split_config(kind: str, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    types = _types(kind)
    settings, secrets = {}, {}
    for k, v in (config or {}).items():
        t = types.get(k) or ("secret" if any(h in k.lower() for h in _SECRET_HINTS) else "text")
        if t == "secret":
            secrets[k] = v
        else:
            settings[k] = v
    return settings, secrets


def masked_config(app: Any, ch: dict[str, Any]) -> dict[str, Any]:
    cfg = dict(ch.get("config") or {})
    for k, v in (app.config.secret(f"channels.{ch['id']}", {}) or {}).items():
        cfg[k] = mask_secret(v)
    return cfg


def to_dto(app: Any, ch: dict[str, Any]) -> dict[str, Any]:
    info = kind_info(ch["kind"])
    return channel_dto(ch, masked_config(app, ch), available=info["available"], label=info["label"])


def build_channel(app: Any, ch: dict[str, Any]) -> Channel:
    cls = load_channel_class(ch["kind"])
    ctx = ChannelContext(channel_id=ch["id"], name=ch["name"], settings=dict(ch.get("config") or {}),
                         secrets=dict(app.config.secret(f"channels.{ch['id']}", {}) or {}),
                         data_dir=app.paths.data, tz=app.tz, logger=logging.getLogger(f"bureau.channel.{ch['kind']}"))
    return cls(ctx)


async def send_via(app: Any, ch: dict[str, Any], payload: ReportPayload, *, test: bool = False,
                   timeout: float = 120.0) -> DeliveryResult:
    """投递到单个通道，不抛异常。"""
    try:
        channel = build_channel(app, ch)
    except ChannelUnavailable as exc:
        return DeliveryResult(ok=False, channel_id=ch["id"], kind=ch["kind"], detail=f"通道未实现：{exc}")
    except Exception as exc:                                          # noqa: BLE001
        return DeliveryResult(ok=False, channel_id=ch["id"], kind=ch["kind"], detail=f"通道加载失败：{exc}")
    try:
        errors = channel.validate()
        if errors:
            return channel.result(False, "配置不完整：" + "；".join(errors))
        coro = channel.test() if test else channel.send(payload)
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        return channel.result(False, f"投递超时（{timeout:.0f} 秒）", retryable=True)
    except Exception as exc:                                          # noqa: BLE001
        log.warning("通道 %s 投递异常：%s", ch["id"], exc)
        return channel.result(False, f"投递出错：{exc}")
    finally:
        try:
            await channel.aclose()
        except Exception:                                             # noqa: BLE001
            pass


def create_channel_record(app: Any, kind: str, name: str, enabled: bool, config: dict[str, Any]) -> dict[str, Any]:
    if kind not in CHANNEL_REGISTRY:
        raise ValueError(f"未知的通道类型：{kind}")
    cid = f"ch_{_secrets.token_hex(4)}"
    settings, secrets = split_config(kind, config)
    ch = app.store.create_channel(cid, kind, name or kind_info(kind)["label"], enabled, settings)
    secrets = {k: v for k, v in secrets.items() if not is_unchanged_secret(v)}
    if secrets:
        app.config.update_secrets({"channels": {cid: secrets}})
    return ch


def update_channel_record(app: Any, ch: dict[str, Any], body: dict[str, Any]) -> dict[str, Any]:
    cfg = None
    if isinstance(body.get("config"), dict):
        settings, secrets = split_config(ch["kind"], body["config"])
        cfg = {**(ch.get("config") or {}), **settings}
        secrets = {k: v for k, v in secrets.items() if not is_unchanged_secret(v)}
        if secrets:
            app.config.update_secrets({"channels": {ch["id"]: secrets}})
    out = app.store.update_channel(ch["id"], name=body.get("name"), enabled=body.get("enabled"), config=cfg)
    return out or ch


def delete_channel_record(app: Any, cid: str) -> bool:
    ok = app.store.delete_channel(cid)
    app.config.delete_secret(f"channels.{cid}")
    return ok
