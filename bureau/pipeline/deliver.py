"""阶段 11 deliver（v2，docs/V2_KNOWLEDGE.md §3.5）：
1. 先投文档类通道（feishu_doc 等），拿到 DeliveryResult.url 填进 ReportPayload.doc_links；
2. 用 doc_links 重新生成 summary_md / summary_text（推送里的「今日风向标直达」改成文档链接）；
3. 再并发投其它通道。单个通道失败不影响其它通道；结果写入 deliveries 并发事件。
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable

from bureau.core.channel_service import send_via
from bureau.pipeline.models import RunContext, StageResult
from bureau.pipeline.summary import build_summary

DOC_KINDS = frozenset({"feishu_doc"})


def is_doc_channel(ch: dict[str, Any]) -> bool:
    if ch["kind"] in DOC_KINDS:
        return True
    try:
        from bureau.channels import load_channel_class

        return bool(getattr(load_channel_class(ch["kind"]), "is_document", False))
    except Exception:                                                # noqa: BLE001
        return False


def resolve_channels(rc: RunContext) -> tuple[list[dict[str, Any]], list[str]]:
    """返回 (要投递的通道, 跳过说明)。
    channel_ids=None：全部启用的通道；演示运行默认只投本地归档（避免把演示数据推给真实的人）。"""
    store = rc.app.store
    allc = store.list_channels()
    skipped: list[str] = []
    if rc.channel_ids is None or not rc.channel_ids:
        chosen = [c for c in allc if c["enabled"]]
        if rc.demo or rc.channel_ids is not None:       # 演示运行 / 任务没选通道：只用本地归档兜底
            chosen = [c for c in chosen if c["kind"] == "local_archive"]
    else:
        by_id = {c["id"]: c for c in allc}
        chosen = []
        for cid in rc.channel_ids:
            c = by_id.get(cid)
            if c is None:
                skipped.append(f"{cid}（不存在）")
            elif not c["enabled"]:
                skipped.append(f"{c['name']}（已停用）")
            else:
                chosen.append(c)
    return chosen, skipped


def _url_of(res: Any) -> str | None:
    url = getattr(res, "url", None) or None
    if not url and str(getattr(res, "external_id", "") or "").startswith(("http://", "https://")):
        url = res.external_id
    return url if res.ok and url else None


async def deliver_to(app: Any, channels: list[dict[str, Any]], payload: Any, *, run_id: str | None,
                     log: Any = None) -> list[dict[str, Any]]:
    async def one(ch: dict[str, Any]) -> dict[str, Any]:
        res = await send_via(app, ch, payload)
        app.store.add_delivery(report_id=payload.report_id, run_id=run_id, channel_id=ch["id"], channel_name=ch["name"],
                               kind=ch["kind"], ok=res.ok, detail=res.detail, external_id=res.external_id, parts=res.parts)
        app.store.set_channel_result(ch["id"], res.ok, res.detail)
        evt = {"run_id": run_id, "report_id": payload.report_id, "channel_id": ch["id"], "channel_name": ch["name"],
               "kind": ch["kind"], "ok": res.ok, "detail": res.detail}
        url = _url_of(res)
        if url:
            evt["url"] = url
        app.bus.publish("delivery.result", evt)
        if log is not None:
            (log.info if res.ok else log.warn)("COURIER", f"{'✓' if res.ok else '✗'} {ch['name']}：{res.detail}", "deliver")
        return evt

    return list(await asyncio.gather(*(one(c) for c in channels)))


def regen_summary(payload: Any, meta: dict[str, Any] | None) -> None:
    """拿到文档链接后重新生成推送版。没有 summary_meta（v1 的旧报告）时不动。"""
    if not meta:
        return
    payload.summary_md, payload.summary_text = build_summary(meta, payload.doc_links)


async def deliver_ordered(app: Any, channels: list[dict[str, Any]], payload: Any, *, run_id: str | None,
                          log: Any = None, regen: Callable[[Any], None] | None = None) -> list[dict[str, Any]]:
    docs = [c for c in channels if is_doc_channel(c)]
    rest = [c for c in channels if c not in docs]
    results: list[dict[str, Any]] = []
    if docs:
        results += await deliver_to(app, docs, payload, run_id=run_id, log=log)
        links = dict(payload.doc_links or {})
        for evt in results:
            if evt.get("url"):
                key = evt["kind"] if evt["kind"] not in links else f"{evt['kind']}:{evt['channel_id']}"
                links[key] = evt["url"]
        payload.doc_links = links
        if regen is not None:
            regen(payload)
        if links and log is not None:
            log.info("COURIER", f"文档已发布，推送里的直达链接改为：{next(iter(links.values()))}", "deliver")
    if rest:
        results += await deliver_to(app, rest, payload, run_id=run_id, log=log)
    return results


async def run(rc: RunContext) -> StageResult:
    if rc.dry_run:
        rc.log.info("COURIER", "仅预览（dry_run）：不投递任何通道，报告已写入本地", "deliver")
        return StageResult(metrics={"channels": 0, "ok": 0, "failed": 0, "dry_run": 1}, message="仅预览，未投递")
    channels, skipped = resolve_channels(rc)
    for s in skipped:
        rc.log.warn("COURIER", f"跳过通道 {s}", "deliver")
    if not channels:
        rc.log.warn("COURIER", "没有可用的推送通道", "deliver")
        return StageResult(metrics={"channels": 0, "ok": 0, "failed": 0}, message="没有可用通道")
    meta = (rc.report.get("v2_data") or {}).get("summary_meta")
    rc.deliveries = await deliver_ordered(rc.app, channels, rc.payload, run_id=rc.run_id, log=rc.log,
                                          regen=lambda p: regen_summary(p, meta))
    if rc.payload.doc_links:                                # archive 阶段把链接和新的推送版写进报告
        rc.report["summary_md"], rc.report["summary_text"] = rc.payload.summary_md, rc.payload.summary_text
        rc.report.setdefault("v2_data", {})["doc_links"] = dict(rc.payload.doc_links)
    ok = sum(1 for d in rc.deliveries if d["ok"])
    docs = sum(1 for c in channels if is_doc_channel(c))
    return StageResult(metrics={"channels": len(channels), "ok": ok, "failed": len(channels) - ok, "doc_channels": docs,
                                "doc_links": len(rc.payload.doc_links or {})},
                       message=f"{ok}/{len(channels)} 成功")
