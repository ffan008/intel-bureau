"""把数据库行转换成 docs/API.md 定义的 DTO（字段名严格按契约）。"""

from __future__ import annotations

from typing import Any

from bureau.core.constants import STAGE_AGENT, STAGES

TOTALS_DEFAULT: dict[str, Any] = {
    "messages_raw": 0, "messages_clean": 0, "chunks": 0, "candidates": 0, "items": 0,
    "tokens_in": 0, "tokens_out": 0, "cost_cny": 0.0, "llm_provider": "",
}


def _opt(d: dict[str, Any], **kw: Any) -> dict[str, Any]:
    for k, v in kw.items():
        if v is not None and v != "":
            d[k] = v
    return d


def empty_stats() -> dict[str, Any]:
    return {
        "messages_raw": 0, "messages_clean": 0, "snr": 0.0, "speakers": 0,
        "by_platform": [],
        "hourly": [{"hour": h, "wechat": 0, "qq": 0, "feishu": 0, "demo": 0} for h in range(24)],
        "heat_7x24": [[d, h, 0] for d in range(7) for h in range(24)],
        "msg_types": [], "top_groups": [], "top_speakers": [], "keywords": [], "rising": [],
    }


def group_dto(g: dict[str, Any], activity: dict[str, int] | None = None) -> dict[str, Any]:
    act = activity or {}
    d = {
        "key": g["key"], "platform": g["platform"], "native_id": g["native_id"], "name": g.get("name") or g["native_id"],
        "whitelisted": bool(g.get("whitelisted")), "weight": float(g.get("weight") or 1.0), "tags": list(g.get("tags") or []),
        "messages_24h": int(act.get("m24", 0)), "messages_7d": int(act.get("m7d", 0)),
        "is_demo": bool(g.get("is_demo")),
    }
    return _opt(d, alias=g.get("alias"), member_count=g.get("member_count"),
                last_message_at=g.get("last_message_at"), last_collect_at=g.get("last_collect_at"))


def stage_dto(row: dict[str, Any]) -> dict[str, Any]:
    d = {"name": row["name"], "agent": STAGE_AGENT[row["name"]], "status": row.get("status") or "pending",
         "metrics": dict(row.get("metrics") or {})}
    return _opt(d, started_at=row.get("started_at"), finished_at=row.get("finished_at"),
                duration_ms=row.get("duration_ms"), message=row.get("message"))


def run_dto(run: dict[str, Any]) -> dict[str, Any]:
    by_name = {s["name"]: s for s in run.get("stages") or []}
    stages = [stage_dto(by_name.get(n) or {"name": n, "status": "pending", "metrics": {}}) for n in STAGES]
    totals = {**TOTALS_DEFAULT, **(run.get("totals") or {})}
    d = {
        "id": run["id"], "trigger": run["trigger"], "status": run["status"], "dry_run": bool(run.get("dry_run")),
        "window_start": run["window_start"], "window_end": run["window_end"], "stages": stages, "totals": totals,
        "is_demo": bool(run.get("is_demo")),
    }
    return _opt(d, schedule_id=run.get("schedule_id"), started_at=run.get("started_at"),
                finished_at=run.get("finished_at"), report_id=run.get("report_id"), error=run.get("error"))


def delivery_brief(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"channel_id": r["channel_id"], "channel_name": r.get("channel_name") or r["channel_id"],
             "kind": r["kind"], "ok": bool(r["ok"])} for r in rows]


def report_summary_dto(report: dict[str, Any], deliveries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    heads = [{"title": h.get("title", ""), "category": h.get("category", ""), "score": float(h.get("score", 0))}
             for h in report.get("headlines") or []]
    return {
        "id": report["id"], "run_id": report["run_id"], "title": report["title"],
        "date_label": report["date_label"], "window_label": report["window_label"],
        "created_at": report["created_at"], "items_total": int(report.get("items_total") or 0),
        "headlines": heads, "deliveries": delivery_brief(deliveries or []),
        "is_demo": bool(report.get("is_demo")), "dry_run": bool(report.get("dry_run")),
    }


def report_dto(report: dict[str, Any], items: list[dict[str, Any]],
               deliveries: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    d = report_summary_dto(report, deliveries)
    stats = {**empty_stats(), **(report.get("stats") or {})}
    d.update({
        "judgments": list(report.get("judgments") or []),
        "full_md": report.get("full_md", ""), "summary_md": report.get("summary_md", ""),
        "items": items, "stats": stats,
    })
    d.update(report_v2_fields(report))
    return d


V2_LIST_FIELDS = ("articles", "resources", "media", "groups")


def report_v2_fields(report: dict[str, Any]) -> dict[str, Any]:
    """v2 字段（docs/V2_KNOWLEDGE.md §7）。v1 的旧报告没有这些数据：数组给空数组，对象给空对象。"""
    v2 = report.get("v2_data") or {}
    if not isinstance(v2, dict):
        v2 = {}
    out: dict[str, Any] = {"sections": dict(v2.get("sections") or {})}
    for k in V2_LIST_FIELDS:
        out[k] = list(v2.get(k) or [])
    out["section_counts"] = dict(v2.get("section_counts") or {})
    out["doc_links"] = dict(v2.get("doc_links") or {})
    return out


def kb_summary_dto(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"], "title": row["title"], "category": row.get("category") or "", "tags": list(row.get("tags") or []),
        "hook": row.get("hook") or "", "risk_flags": list(row.get("risk_flags") or []),
        "updated_at": row["updated_at"], "created_at": row["created_at"],
        "versions": int(row.get("n_versions") or 0), "sources": len(row.get("sources") or []),
    }


def kb_article_dto(row: dict[str, Any], versions: list[dict[str, Any]], related: list[dict[str, str]]) -> dict[str, Any]:
    d = kb_summary_dto(row)
    d.update({
        "body_md": row.get("body_md") or "",
        "versions": [{"at": v["created_at"], "report_id": v.get("report_id") or "", "note": v.get("note") or "",
                      "id": v["id"]} for v in versions],
        "sources": [{"group_name": s.get("group_name") or "", "sender": s.get("sender") or "",
                     "sent_at": s.get("sent_at") or ""} for s in row.get("sources") or []],
        "related": related,
        "first_day": row.get("first_day"), "last_day": row.get("last_day"),
    })
    return d


def schedule_dto(s: dict[str, Any], *, next_run_at: str | None = None,
                 last_run: dict[str, Any] | None = None) -> dict[str, Any]:
    d = {
        "id": s["id"], "name": s["name"], "enabled": bool(s["enabled"]), "cron": s["cron"], "timezone": s["timezone"],
        "window_mode": s["window_mode"], "window_hours": int(s["window_hours"]),
        "platforms": list(s.get("platforms") or []), "group_keys": list(s.get("group_keys") or []),
        "channel_ids": list(s.get("channel_ids") or []), "top_n": int(s["top_n"]), "dry_run": bool(s["dry_run"]),
    }
    if last_run:
        d["last_run"] = _opt({"id": last_run["id"], "status": last_run["status"]}, finished_at=last_run.get("finished_at"))
    return _opt(d, next_run_at=next_run_at)


def channel_dto(c: dict[str, Any], masked_config: dict[str, Any], *, available: bool = True,
                label: str | None = None) -> dict[str, Any]:
    d: dict[str, Any] = {"id": c["id"], "kind": c["kind"], "name": c["name"], "enabled": bool(c["enabled"]),
                         "config": masked_config, "available": available}
    if label:
        d["kind_label"] = label
    if c.get("last_at"):
        d["last_result"] = {"ok": bool(c.get("last_ok")), "detail": c.get("last_detail") or "", "at": c["last_at"]}
    return d
