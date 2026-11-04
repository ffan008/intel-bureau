"""情报源：平台、群白名单、导入、OneBot 实时上报。B 的函数都兜住导入失败（返回 501 + 中文说明）。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from bureau.api.deps import as_bool, get_ctx, json_body, page
from bureau.api.errors import ApiError
from bureau.api.multipart import parse_multipart
from bureau.collectors import CollectorUnavailable
from bureau.contracts import Platform
from bureau.core.app import AppContext
from bureau.core.constants import LIVE_PLATFORMS
from bureau.core.dto import group_dto
from bureau.core.platforms import check_health, create_collector, platform_dto, save_platform_config
from bureau.core.security import is_loopback

router = APIRouter(prefix="/api")
MAX_IMPORT_BYTES = 50 * 1024 * 1024


def _platform(p: str) -> str:
    if p not in LIVE_PLATFORMS:
        raise ApiError(404, "unknown_platform", f"不支持的平台：{p}", "可选 wechat / qq / feishu")
    return p


@router.get("/platforms")
def platforms(ctx: AppContext = Depends(get_ctx)) -> list[dict[str, Any]]:
    return [platform_dto(ctx, p) for p in LIVE_PLATFORMS]


@router.put("/platforms/{platform}")
async def put_platform(platform: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    _platform(platform)
    body = await json_body(request)
    try:
        save_platform_config(ctx, platform, body)
    except ValueError as exc:
        raise ApiError(400, "invalid_config", str(exc)) from None
    if ctx.config.get(f"sources.{platform}.enabled", False):
        await check_health(ctx, platform)
    dto = platform_dto(ctx, platform)
    ctx.bus.publish("platform.health", dto)
    return dto


@router.post("/platforms/{platform}/test")
async def test_platform(platform: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    _platform(platform)
    await check_health(ctx, platform)
    dto = platform_dto(ctx, platform)
    ctx.bus.publish("platform.health", dto)
    return dto


async def refresh_groups(ctx: AppContext, platform: str) -> dict[str, int]:
    try:
        collector = create_collector(ctx, platform)
    except CollectorUnavailable as exc:
        raise ApiError(501, "collector_unavailable", f"采集器未实现：{exc}", "可以先用「导入聊天记录文件」") from None
    try:
        groups = await asyncio.wait_for(collector.list_groups(), 60)
    except asyncio.TimeoutError:
        raise ApiError(504, "timeout", "拉取群列表超时（60 秒）", "确认对应的本地服务已启动") from None
    except Exception as exc:                                         # noqa: BLE001
        raise ApiError(502, "collector_error", f"拉取群列表失败：{exc}") from None
    finally:
        await collector.aclose()
    added = updated = 0
    for g in groups:
        if g.platform.value != platform:
            continue
        _, created = ctx.store.upsert_group(g)
        added += int(created)
        updated += int(not created)
    total = len(ctx.store.list_groups(platform=platform, is_demo=False)[0])
    return {"added": added, "updated": updated, "total": total}


@router.post("/platforms/{platform}/refresh-groups")
async def post_refresh(platform: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, int]:
    return await refresh_groups(ctx, _platform(platform))


def _group_out(ctx: AppContext, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    live = [g["key"] for g in rows if not g["is_demo"]]
    demo = [g["key"] for g in rows if g["is_demo"]]
    act = ctx.store.group_activity(live, ctx.now())
    act.update(ctx.store.group_activity(demo, ctx.demo_anchor() or ctx.now()))
    return [group_dto(g, act.get(g["key"])) for g in rows]


@router.get("/groups")
def list_groups(platform: str | None = None, whitelisted: str | None = None, q: str | None = None,
                limit: int | None = None, offset: int | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    lim, off = page(limit, offset, default=200, cap=1000)
    rows, total = ctx.store.list_groups(platform=platform or None, whitelisted=as_bool(whitelisted), q=q or None,
                                        limit=lim, offset=off)
    return {"items": _group_out(ctx, rows), "total": total}


@router.patch("/groups/{key:path}")
async def patch_group(key: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    body = await json_body(request)
    if ctx.store.get_group(key) is None:
        raise ApiError(404, "group_not_found", f"群不存在：{key}")
    if "tags" in body and not isinstance(body["tags"], list):
        raise ApiError(400, "invalid_tags", "tags 必须是字符串数组")
    try:
        g = ctx.store.update_group(key, **{k: body.get(k) for k in ("whitelisted", "weight", "alias", "tags")})
    except (TypeError, ValueError):
        raise ApiError(400, "invalid_group", "字段格式不正确") from None
    ctx.overview_cache.clear()
    ctx.bus.publish("overview.dirty", {})
    return _group_out(ctx, [g])[0]  # type: ignore[list-item]


@router.post("/groups/bulk")
async def bulk_groups(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, int]:
    body = await json_body(request)
    keys = body.get("keys")
    if not isinstance(keys, list) or not isinstance(body.get("whitelisted"), bool):
        raise ApiError(400, "invalid_request", "需要 {keys: string[], whitelisted: boolean}")
    n = ctx.store.bulk_whitelist([str(k) for k in keys], body["whitelisted"])
    ctx.overview_cache.clear()
    ctx.bus.publish("overview.dirty", {})
    return {"updated": n}


@router.post("/import")
async def import_chat(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    body = await request.body()
    if len(body) > MAX_IMPORT_BYTES:
        raise ApiError(413, "too_large", "文件超过 50 MB")
    ctype = request.headers.get("content-type", "")
    filename: str | None = None
    if ctype.startswith("multipart/form-data"):
        fields, files = parse_multipart(ctype, body)
        if "file" in files:
            filename, content = files["file"]
        else:
            content = (fields.get("text") or "").encode("utf-8")
    elif ctype.startswith("application/x-www-form-urlencoded"):
        from urllib.parse import parse_qs

        fields = {k: v[0] for k, v in parse_qs(body.decode("utf-8", errors="replace")).items()}
        content = (fields.get("text") or "").encode("utf-8")
    else:
        try:
            fields = json.loads(body or b"{}")
        except ValueError:
            raise ApiError(400, "invalid_request", "请用 multipart/form-data 上传文件，或提交 JSON {platform, group_name, text}") from None
        content = str(fields.get("text") or "").encode("utf-8")
    platform = str(fields.get("platform") or "")
    if platform not in LIVE_PLATFORMS:
        raise ApiError(400, "invalid_platform", "platform 必须是 wechat / qq / feishu")
    if not content.strip():
        raise ApiError(400, "empty", "没有收到文件或文本")
    try:
        from bureau.collectors.file_import import parse_export
    except ImportError:
        raise ApiError(501, "not_implemented", "聊天记录导入模块尚未安装（bureau.collectors.file_import）",
                       "等待导入模块交付后再试") from None
    try:
        parsed = await asyncio.to_thread(parse_export, content, filename=filename, platform=Platform(platform),
                                         group_name=(fields.get("group_name") or None), tz=ctx.tz)
    except ValueError as exc:
        raise ApiError(400, "parse_failed", f"无法识别的聊天记录格式：{exc}") from None
    g, _ = ctx.store.upsert_group(parsed.group, whitelisted=True)
    imported, skipped = await asyncio.to_thread(ctx.store.insert_messages, parsed.messages, source="import")
    ctx.overview_cache.clear()
    ctx.bus.publish("ingest.message", {"platform": platform, "group_name": g["name"], "count": imported})
    ctx.bus.publish("overview.dirty", {})
    return {"group": _group_out(ctx, [g])[0], "imported": imported, "skipped": skipped, "format": parsed.format,
            "warnings": list(parsed.warnings)}


def _onebot_creds(ctx: AppContext) -> tuple[str | None, str | None]:
    secrets = ctx.config.secret("sources.qq.onebot", {}) or {}
    try:
        from bureau.integrations.onebot import onebot_credentials

        return onebot_credentials(secrets)
    except ImportError:
        return (secrets.get("report_secret") or secrets.get("secret") or None,
                secrets.get("token") or secrets.get("access_token") or None)


@router.post("/ingest/onebot")
async def ingest_onebot(request: Request, ctx: AppContext = Depends(get_ctx)) -> Response:
    client = request.client.host if request.client else None
    if not is_loopback(client):
        raise ApiError(403, "loopback_only", "实时上报只接受本机地址")
    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        raise ApiError(413, "too_large", "上报内容过大")
    try:
        from bureau.integrations.onebot import parse_onebot_event, verify_onebot_request
    except ImportError:
        raise ApiError(501, "not_implemented", "OneBot 上报解析模块尚未安装（bureau.integrations.onebot）") from None
    secret, token = _onebot_creds(ctx)
    if not verify_onebot_request(request.headers, body, secret=secret, token=token):
        raise ApiError(401, "bad_signature", "OneBot 上报签名校验失败", "检查 NapCat HTTP 客户端的 token 与情报局里的设置是否一致")
    try:
        event = json.loads(body or b"{}")
    except ValueError:
        raise ApiError(400, "invalid_json", "上报内容不是 JSON") from None
    msg = parse_onebot_event(event) if isinstance(event, dict) else None
    if msg is None:
        return Response(status_code=204)
    g = ctx.store.get_group(msg.group_key)
    if g is None or not g["whitelisted"]:       # 非白名单群：不落库，只记下群名方便用户加白名单
        if g is None and msg.group_name:
            from bureau.contracts import GroupInfo

            ctx.store.upsert_group(GroupInfo(platform=msg.platform, native_id=msg.group_native_id, name=msg.group_name))
        return Response(status_code=204)
    inserted, _ = ctx.store.insert_messages([msg], source="realtime")
    if inserted:
        data: dict[str, Any] = {"platform": msg.platform.value, "group_name": g.get("alias") or g["name"], "count": inserted}
        if ctx.config.get("privacy.live_preview", False):
            data.update(sender=msg.sender_name, preview=(msg.text or "")[:30])
        ctx.bus.publish("ingest.message", data)
    return Response(status_code=204)
