"""平台服务：适配器信息（懒加载，缺失时显示"未实现"）、健康检查、PlatformDTO、平台配置保存。"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bureau.collectors import COLLECTOR_REGISTRY, CollectorUnavailable, load_collector_class
from bureau.collectors.base import CollectorContext
from bureau.contracts import PLATFORM_LABELS, Health, HealthStatus, Platform
from bureau.core.constants import ADAPTER_FALLBACK_LABELS, LIVE_PLATFORMS
from bureau.core.security import is_unchanged_secret, mask_secret

log = logging.getLogger("bureau.platforms")
_SECRET_HINTS = ("token", "secret", "key", "password", "passwd", "sendkey")


def adapter_keys(platform: str) -> list[str]:
    return [k for k in COLLECTOR_REGISTRY if k.startswith(f"{platform}.")]


def adapter_suffix(adapter_key: str) -> str:
    return adapter_key.split(".", 1)[1]


def adapter_info(key: str) -> dict[str, Any]:
    """{key, label, config_schema, available, detail}。模块缺失不抛异常。"""
    try:
        cls = load_collector_class(key)
        schema = [f.model_dump(exclude_none=True) for f in cls.config_schema()]
        return {"key": key, "label": getattr(cls, "label", key), "config_schema": schema, "available": True,
                "realtime": bool(getattr(cls, "supports_realtime", False))}
    except CollectorUnavailable as exc:
        return {"key": key, "label": f"{ADAPTER_FALLBACK_LABELS.get(key, key)}（未实现）", "config_schema": [],
                "available": False, "detail": str(exc)}
    except Exception as exc:                                          # noqa: BLE001  B 的模块导入出错
        log.warning("加载采集器 %s 出错：%s", key, exc)
        return {"key": key, "label": f"{ADAPTER_FALLBACK_LABELS.get(key, key)}（加载失败）", "config_schema": [],
                "available": False, "detail": f"采集器 {key} 加载失败：{exc}"}


def _schema_types(key: str) -> dict[str, str]:
    try:
        return {f.key: f.type for f in load_collector_class(key).config_schema()}
    except Exception:                                                 # noqa: BLE001
        return {}


def collector_context(app: Any, platform: str, adapter_key: str) -> CollectorContext:
    suffix = adapter_suffix(adapter_key)
    return CollectorContext(
        platform=Platform(platform),
        settings=dict(app.config.get(f"sources.{platform}.{suffix}", {}) or {}),
        secrets=dict(app.config.secret(f"sources.{platform}.{suffix}", {}) or {}),
        data_dir=app.paths.data, tz=app.tz, logger=logging.getLogger(f"bureau.collector.{platform}"),
    )


def create_collector(app: Any, platform: str, adapter_key: str | None = None) -> Any:
    key = adapter_key or app.config.get(f"sources.{platform}.adapter") or adapter_keys(platform)[0]
    cls = load_collector_class(key)
    return cls(collector_context(app, platform, key))


async def check_health(app: Any, platform: str, *, timeout: float = 6.0) -> dict[str, Any]:
    """返回并缓存 {state, detail, hint, checked_at}。"""
    enabled = bool(app.config.get(f"sources.{platform}.enabled", False))
    adapter = app.config.get(f"sources.{platform}.adapter") or adapter_keys(platform)[0]
    label = PLATFORM_LABELS[Platform(platform)]
    if not enabled:
        st = HealthStatus(ok=False, state=Health.DISABLED, detail=f"{label}采集未启用",
                          hint="在「情报源」页面打开启用开关并选择适配器")
    else:
        try:
            collector = create_collector(app, platform, adapter)
        except CollectorUnavailable as exc:
            st = HealthStatus(ok=False, state=Health.UNCONFIGURED, detail=f"适配器未实现：{exc}",
                              hint="该适配器尚未安装；可以先用「导入聊天记录文件」把导出文件放进来")
        except Exception as exc:                                      # noqa: BLE001
            st = HealthStatus(ok=False, state=Health.DOWN, detail=f"适配器加载失败：{exc}", hint="查看 data/logs/bureau.log")
        else:
            try:
                st = await asyncio.wait_for(collector.health(), timeout)
            except asyncio.TimeoutError:
                st = HealthStatus(ok=False, state=Health.DOWN, detail=f"健康检查超时（{timeout:.0f} 秒）",
                                  hint="确认对应的本地服务已启动")
            except Exception as exc:                                  # noqa: BLE001
                st = HealthStatus(ok=False, state=Health.DOWN, detail=f"健康检查出错：{exc}")
            finally:
                try:
                    await collector.aclose()
                except Exception:                                     # noqa: BLE001
                    pass
    entry = {"state": st.state.value, "detail": st.detail, "hint": st.hint, "checked_at": app.store.now_iso(),
             "adapter": adapter, "data": st.data}
    app.health_cache[platform] = entry
    return entry


def platform_dto(app: Any, platform: str, *, demo_view: bool = False, scope_demo: bool | None = None,
                 activity: dict[str, dict[str, int]] | None = None, end: Any = None) -> dict[str, Any]:
    """scope_demo=None 统计全部群；True/False 只统计演示 / 真实群。demo_view=True 时按演示模式展示健康状态。"""
    enabled = bool(app.config.get(f"sources.{platform}.enabled", False))
    adapter = app.config.get(f"sources.{platform}.adapter") or adapter_keys(platform)[0]
    adapters = [adapter_info(k) for k in adapter_keys(platform)]
    health = app.health_cache.get(platform)
    if health is None:
        state = "disabled" if not enabled else "unconfigured"
        cur = next((a for a in adapters if a["key"] == adapter), None)
        detail = f"{PLATFORM_LABELS[Platform(platform)]}采集未启用" if not enabled else (
            "尚未检查" if cur and cur["available"] else f"适配器 {adapter} 未实现")
        health = {"state": state, "detail": detail, "hint": None, "checked_at": None}
    groups, _ = app.store.list_groups(platform=platform, is_demo=True if demo_view else scope_demo)
    keys = [g["key"] for g in groups]
    wl = [g for g in groups if g["whitelisted"]]
    act = activity if activity is not None else app.store.group_activity(keys, end or app.now())
    last_collect = max((g["last_collect_at"] for g in groups if g.get("last_collect_at")), default=None)
    d: dict[str, Any] = {
        "platform": platform, "label": PLATFORM_LABELS[Platform(platform)], "enabled": enabled, "adapter": adapter,
        "adapters": adapters, "health": health["state"], "detail": health["detail"],
        "groups_total": len(groups), "groups_whitelisted": len(wl),
        "messages_24h": sum(act.get(k, {}).get("m24", 0) for k in keys),
        "config": masked_platform_config(app, platform, adapter),
    }
    if demo_view and groups:
        d.update({"health": "ok", "detail": "演示模式：合成数据（未连接真实平台）"})
    if health.get("hint") and not (demo_view and groups):
        d["hint"] = health["hint"]
    if health.get("checked_at"):
        d["checked_at"] = health["checked_at"]
    if last_collect:
        d["last_collect_at"] = last_collect
    return d


def masked_platform_config(app: Any, platform: str, adapter: str) -> dict[str, Any]:
    suffix = adapter_suffix(adapter)
    cfg = dict(app.config.get(f"sources.{platform}.{suffix}", {}) or {})
    for k, v in (app.config.secret(f"sources.{platform}.{suffix}", {}) or {}).items():
        cfg[k] = mask_secret(v)
    return cfg


def save_platform_config(app: Any, platform: str, body: dict[str, Any]) -> None:
    if platform not in LIVE_PLATFORMS:
        raise ValueError(f"不支持的平台：{platform}")
    patch: dict[str, Any] = {}
    if body.get("enabled") is not None:
        patch["enabled"] = bool(body["enabled"])
    adapter = body.get("adapter") or app.config.get(f"sources.{platform}.adapter")
    if body.get("adapter"):
        if body["adapter"] not in adapter_keys(platform):
            raise ValueError(f"平台 {platform} 没有适配器 {body['adapter']}")
        patch["adapter"] = body["adapter"]
    cfg = body.get("config")
    if isinstance(cfg, dict) and cfg:
        types = _schema_types(adapter)
        settings_part: dict[str, Any] = {}
        secrets_part: dict[str, Any] = {}
        for k, v in cfg.items():
            t = types.get(k) or ("secret" if any(h in k.lower() for h in _SECRET_HINTS) else "text")
            if t == "secret":
                if not is_unchanged_secret(v):
                    secrets_part[k] = str(v).strip()
            else:
                settings_part[k] = _coerce(v, t)
        suffix = adapter_suffix(adapter)
        if settings_part:
            patch[suffix] = settings_part
        if secrets_part:
            app.config.update_secrets({"sources": {platform: {suffix: secrets_part}}})
    if patch:
        app.config.update_settings({"sources": {platform: patch}})
    app.health_cache.pop(platform, None)


def _coerce(v: Any, t: str) -> Any:
    if t == "number":
        try:
            return float(v) if "." in str(v) else int(v)
        except (TypeError, ValueError):
            raise ValueError(f"数字格式不正确：{v}") from None
    if t == "bool":
        return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")
    if t == "url" and v and not str(v).startswith(("http://", "https://")):
        raise ValueError(f"地址必须以 http:// 或 https:// 开头：{v}")
    return v.strip() if isinstance(v, str) else v


async def health_loop(app: Any, interval: float) -> None:
    """后台定期检查已启用的平台，状态变化时发 platform.health 事件。"""
    while True:
        for p in LIVE_PLATFORMS:
            if not app.config.get(f"sources.{p}.enabled", False):
                continue
            before = (app.health_cache.get(p) or {}).get("state")
            try:
                await check_health(app, p)
            except Exception as exc:                                  # noqa: BLE001
                log.warning("平台 %s 健康检查异常：%s", p, exc)
                continue
            if app.health_cache.get(p, {}).get("state") != before:
                app.bus.publish("platform.health", platform_dto(app, p))
        await asyncio.sleep(max(30.0, interval))
