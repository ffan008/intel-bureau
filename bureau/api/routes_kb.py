"""知识库（docs/V2_KNOWLEDGE.md §3.3、§7）：搜索、分类 / 标签筛选、阅读、历史版本。

scope：默认跟随工作台模式（演示模式看演示知识库，实时模式看真实知识库），也可以用 ?scope=live|demo 指定。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from bureau.api.deps import get_ctx, page
from bureau.api.errors import ApiError
from bureau.core.app import AppContext
from bureau.core.dto import kb_article_dto, kb_summary_dto

router = APIRouter(prefix="/api")


def _scope(ctx: AppContext, scope: str | None) -> str:
    if scope in ("live", "demo"):
        return scope
    if scope:
        raise ApiError(400, "invalid_scope", "scope 只能是 live / demo")
    return ctx.mode()


@router.get("/kb")
def list_kb(q: str | None = None, category: str | None = None, tag: str | None = None, limit: int | None = None,
            offset: int | None = None, scope: str | None = None, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    lim, off = page(limit, offset)
    sc = _scope(ctx, scope)
    rows, total = ctx.store.kb_list(sc, q=(q or "").strip()[:100] or None, category=category or None, tag=tag or None,
                                    limit=lim, offset=off)
    cats, tags = ctx.store.kb_facets(sc)
    return {"items": [kb_summary_dto(r) for r in rows], "total": total, "categories": cats, "tags": tags, "scope": sc}


@router.get("/kb/{kb_id}")
def get_kb(kb_id: str, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    row = ctx.store.kb_get(kb_id)
    if row is None:
        raise ApiError(404, "kb_not_found", f"知识库条目不存在：{kb_id}")
    return kb_article_dto(row, ctx.store.kb_versions(kb_id), ctx.store.kb_related(kb_id))


@router.get("/kb/{kb_id}/versions/{version_id}")
def get_kb_version(kb_id: str, version_id: int, ctx: AppContext = Depends(get_ctx)) -> dict[str, Any]:
    """某个历史版本的正文（KbArticleDTO.versions 只给时间和说明，正文按需取）。"""
    row = ctx.db.query_one("SELECT id, kb_id, report_id, day, note, title, body_md, created_at FROM kb_versions "
                           "WHERE kb_id=? AND id=?", (kb_id, int(version_id)))
    if row is None:
        raise ApiError(404, "kb_version_not_found", "历史版本不存在")
    return {"id": row["id"], "kb_id": row["kb_id"], "at": row["created_at"], "report_id": row["report_id"],
            "day": row["day"], "note": row["note"], "title": row["title"], "body_md": row["body_md"]}
