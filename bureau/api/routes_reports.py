"""报告、情报条目、推送通道。"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response

from bureau.api.deps import get_ctx, json_body, page
from bureau.api.errors import ApiError
from bureau.channels import CHANNEL_REGISTRY
from bureau.core import channel_service as cs
from bureau.core.app import AppContext
from bureau.core.dto import report_dto, report_summary_dto
from bureau.core.reportfiles import assets_dir_for, basic_markdown_html, payload_from_report
from bureau.pipeline.deliver import deliver_ordered, regen_summary

router = APIRouter(prefix="/api")


def _report_or_404(ctx: AppContext, rid: str) -> dict[str, Any]:
    r = ctx.store.get_report(rid)
    if r is None:
        raise ApiError(404, "report_not_found", f"报告不存在：{rid}")
    return r


@router.get("/reports")
def list_reports(limit: int | None = None, offset: int | None = None, q: str | None = None,
                 ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    lim, off = page(limit, offset)
    rows, total = ctx.store.list_reports(lim, off, q=q or None)
    return {"items": [report_summary_dto(r, ctx.store.deliveries_for(r["id"])) for r in rows], "total": total}


@router.get("/reports/{rid}")
def get_report(rid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    r = _report_or_404(ctx, rid)
    return report_dto(r, ctx.store.report_items(rid), ctx.store.deliveries_for(rid))


@router.get("/reports/{rid}/export")
def export_report(rid: str, request: Request, format: str = "md", inline: int = 0,
                  ctx: AppContext = Depends(get_ctx)) -> Response:
    r = _report_or_404(ctx, rid)
    media = {"md": "text/markdown; charset=utf-8", "html": "text/html; charset=utf-8",
             "json": "application/json; charset=utf-8"}
    if format not in media:
        raise ApiError(400, "invalid_format", "format 只能是 md / html / json")
    path = (r.get("files") or {}).get(format)
    content: str | None = None
    if path and Path(path).is_file():
        content = Path(path).read_text(encoding="utf-8")
    elif format == "md":
        content = r["full_md"]
    elif format == "html":
        content = basic_markdown_html(r["full_md"], r["title"])
    else:
        content = json.dumps(report_dto(r, ctx.store.report_items(rid)), ensure_ascii=False, indent=2)
    disp = "inline" if inline else "attachment"
    headers = {"Content-Disposition": f"{disp}; filename=\"{rid}.{format}\"; filename*=UTF-8''{rid}.{format}"}
    if format == "html":   # 报告 HTML 自带内联样式，不含脚本；图片只能来自本服务的 assets 接口
        headers["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'; img-src 'self' data:"
        token = request.query_params.get("token")
        if inline and token:                    # 浏览器里预览：相对路径的图片改走 assets 接口（同一个令牌）
            content = _ASSET_SRC.sub(lambda m: f'src="/api/reports/{rid}/assets/{m.group(2)}?token={quote(token)}"',
                                     content or "")
    return Response(content=content, media_type=media[format], headers=headers)


_ASSET_SRC = re.compile(r'src="([\w.-]+)_assets/([\w.-]+)"')
_ASSET_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]{0,80}$")
ASSET_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp",
               ".bmp": "image/bmp", ".pdf": "application/pdf", ".txt": "text/plain; charset=utf-8",
               ".md": "text/markdown; charset=utf-8", ".csv": "text/csv; charset=utf-8",
               ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
               ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
               ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation"}


@router.get("/reports/{rid}/assets/{name}")
def report_asset(rid: str, name: str, ctx: AppContext = Depends(get_ctx)) -> Response:
    """报告图片 / 文档。只能读这份报告的 <report_id>_assets/ 目录里、报告登记过的文件（防路径穿越）。"""
    r = _report_or_404(ctx, rid)
    if not _ASSET_NAME.match(name) or ".." in name:
        raise ApiError(400, "invalid_asset", "文件名不合法")
    ext = Path(name).suffix.lower()
    if ext not in ASSET_TYPES:
        raise ApiError(404, "asset_not_found", "文件不存在")
    html = (r.get("files") or {}).get("html")
    if not html:
        raise ApiError(404, "asset_not_found", "这份报告没有附件")
    reports_root = ctx.paths.reports.resolve()
    folder = assets_dir_for(html, rid).resolve()
    target = (folder / name).resolve()
    known = {m.get("url", "").rsplit("/", 1)[-1] for m in (r.get("v2_data") or {}).get("media") or []}
    if reports_root not in folder.parents or target.parent != folder or name not in known or not target.is_file():
        raise ApiError(404, "asset_not_found", "文件不存在")
    disp = "inline" if ASSET_TYPES[ext].startswith("image/") else "attachment"
    return FileResponse(target, media_type=ASSET_TYPES[ext], headers={
        "Content-Disposition": f"{disp}; filename=\"{name}\"", "Cache-Control": "private, max-age=86400",
        "Content-Security-Policy": "default-src 'none'; sandbox"})


@router.post("/reports/{rid}/deliver")
async def redeliver(rid: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    r = _report_or_404(ctx, rid)
    body = await json_body(request)
    ids = body.get("channel_ids")
    if not isinstance(ids, list) or not ids:
        raise ApiError(400, "invalid_request", "需要 {channel_ids: string[]}")
    by_id = {c["id"]: c for c in ctx.store.list_channels()}
    missing = [i for i in ids if i not in by_id]
    if missing:
        raise ApiError(400, "unknown_channel", f"通道不存在：{'、'.join(map(str, missing))}")
    payload = payload_from_report(r, ctx.store.report_items(rid), ctx.dashboard_url())
    meta = (r.get("v2_data") or {}).get("summary_meta")
    results = await deliver_ordered(ctx, [by_id[i] for i in ids], payload, run_id=r["run_id"],
                                    regen=lambda p: regen_summary(p, meta))
    if payload.doc_links and r.get("v2_data"):            # 文档链接和新的推送版写回报告
        ctx.store.update_report_v2(rid, {"doc_links": dict(payload.doc_links)})
        ctx.store.update_report_summary(rid, payload.summary_md, payload.summary_text)
    return {"results": [{"channel_id": x["channel_id"], "ok": x["ok"], "detail": x["detail"],
                         **({"url": x["url"]} if x.get("url") else {})} for x in results]}


@router.get("/items/{item_id}")
def get_item(item_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    it = ctx.store.get_item(item_id)
    if it is None:
        raise ApiError(404, "item_not_found", f"情报不存在：{item_id}")
    ctx_msgs: dict[str, Any] = {"before": [], "after": []}
    ev = (it.get("evidence") or [None])[0]
    if ev and str(ev.get("message_id", "")).isdigit():
        mid = int(ev["message_id"])
        ctx_msgs = ctx.store.message_context(mid, 5)
        focus = ctx.store.message_by_id(mid)
        if focus:
            ctx_msgs["focus"] = {k: focus[k] for k in ("id", "group_key", "platform", "native_id", "sender_name",
                                                       "sent_at", "kind", "text", "reply_to")}
    for side in ("before", "after"):
        for m in ctx_msgs.get(side, []):
            m["message_id"] = str(m["id"])
    return {**it, "context": ctx_msgs}


# ---------------- 推送通道 ----------------
@router.get("/channel-kinds")
def channel_kinds() -> list[dict[str, Any]]:
    return cs.list_kinds()


@router.get("/channels")
def list_channels(ctx: AppContext = Depends(get_ctx)) -> list[dict[str, Any]]:
    return [cs.to_dto(ctx, c) for c in ctx.store.list_channels()]


def _channel_or_404(ctx: AppContext, cid: str) -> dict[str, Any]:
    c = ctx.store.get_channel(cid)
    if c is None:
        raise ApiError(404, "channel_not_found", f"通道不存在：{cid}")
    return c


@router.post("/channels")
async def create_channel(request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    body = await json_body(request)
    kind = str(body.get("kind") or "")
    if kind not in CHANNEL_REGISTRY:
        raise ApiError(400, "unknown_kind", f"未知的通道类型：{kind}")
    if not cs.kind_info(kind)["available"]:
        raise ApiError(501, "channel_unavailable", f"通道类型 {kind} 尚未实现")
    cfg = body.get("config") or {}
    if not isinstance(cfg, dict):
        raise ApiError(400, "invalid_config", "config 必须是对象")
    ch = cs.create_channel_record(ctx, kind, str(body.get("name") or "").strip(), bool(body.get("enabled", True)), cfg)
    return cs.to_dto(ctx, ch)


@router.put("/channels/{cid}")
async def update_channel(cid: str, request: Request, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ch = _channel_or_404(ctx, cid)
    body = await json_body(request)
    if "config" in body and not isinstance(body["config"], dict):
        raise ApiError(400, "invalid_config", "config 必须是对象")
    return cs.to_dto(ctx, cs.update_channel_record(ctx, ch, body))


@router.delete("/channels/{cid}")
def delete_channel(cid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    _channel_or_404(ctx, cid)
    cs.delete_channel_record(ctx, cid)
    for s in ctx.store.list_schedules():
        if cid in s["channel_ids"]:
            ctx.store.update_schedule(s["id"], {"channel_ids": [x for x in s["channel_ids"] if x != cid]})
    return {"ok": True}


@router.post("/channels/{cid}/test")
async def test_channel(cid: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    ch = _channel_or_404(ctx, cid)
    res = await cs.send_via(ctx, ch, None, test=True)
    ctx.store.set_channel_result(cid, res.ok, res.detail)
    return {"ok": res.ok, "detail": res.detail}
