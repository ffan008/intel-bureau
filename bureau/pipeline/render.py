"""阶段 10 render（v2，docs/V2_KNOWLEDGE.md §3.1、§4）：
- 图片复制到 data/reports/<date>/<report_id>_assets/，HTML 和 Markdown 用相对路径引用；
- full_md（按 12 个板块分节）、sections、articles（§3.2 模板的 body_md）、resources、media、分群摘要；
- 自包含 HTML（左侧板块标签页，纯 CSS 切换）；
- 推送版 summary_md / summary_text（§3.5）。
文件写入 data/reports/<date>/<report_id>.{md,html,json}。
"""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

from bureau.contracts import ArticleBrief, HeadlineBrief, PLATFORM_LABELS, Platform, ReportPayload, ResourceBrief
from bureau.core.reportfiles import assets_dir_for, write_report_files
from bureau.core.timeutil import iso
from bureau.pipeline.models import RunContext, StageResult
from bureau.pipeline.render_page import render_page
from bureau.pipeline.report_model import build_context, item_dto
from bureau.pipeline.risk import has_risk, policy_of
from bureau.pipeline.score import report_day
from bureau.pipeline.sections import build_sections, full_markdown, section_markdown
from bureau.pipeline.summary import build_summary, summary_meta

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
DOC_EXT = {".pdf", ".docx", ".xlsx", ".pptx", ".txt", ".md", ".csv"}


def _allowed_roots(rc: RunContext) -> list[Path]:
    """只从这些目录复制图片（取回的媒体缓存、演示素材），不跟随任意路径。"""
    return [rc.app.paths.media_cache.resolve(), rc.app.paths.demo_media.resolve()]


def copy_assets(rc: RunContext, assets: Path) -> int:
    """把取回的图片复制到报告的 assets 目录，给媒体条目补上 asset（相对路径）与 url（工作台接口）。"""
    roots = _allowed_roots(rc)
    n = 0
    for m in rc.media:
        if not m.get("ok") or not m.get("path"):
            continue
        src = Path(m["path"]).resolve()
        allowed = IMG_EXT if m["kind"] == "image" else DOC_EXT
        if src.suffix.lower() not in allowed or not src.is_file() or not any(r in src.parents for r in roots):
            continue
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{m['ref']}{src.suffix.lower()}")
        assets.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, assets / name)
        m["asset_name"] = name
        m["url"] = f"/api/reports/{rc.report['id']}/assets/{name}"
        if m["kind"] == "image":                          # 文档只供下载，不在正文里引用
            m["asset"] = f"{assets.name}/{name}"
        n += 1
    return n


def build_payload(rc: RunContext, ctx: dict[str, Any], v2: dict[str, Any], assets: Path | None) -> ReportPayload:
    r = rc.report
    heads = [HeadlineBrief(title=it.title, hook=it.hook, category=it.category, score=it.score, trend=it.trend,  # type: ignore[arg-type]
                           sources=[f"{PLATFORM_LABELS[Platform(s['platform'])]}·{s['group_name']}" for s in it.sources[:3]],
                           risk_flags=it.risk_flags, links=[x["url"] for x in it.links])
             for it in ctx["heads"]]
    arts = [ArticleBrief(id=a["id"], seq=a["seq"], title=a["title"], hook=a["hook"], category=a["category"],
                         body_md=a["body_md"], risk_flags=a["risk_flags"], risk_note=a.get("risk_note"),
                         sources=a["source_lines"], image_paths=a["images"], kb_id=a.get("kb_id"))
            for a in v2["articles"]]
    res = [ResourceBrief(**{k: x[k] for k in ("kind", "title", "url", "code", "meta", "note", "shared_by", "group_name",
                                              "sent_at") if k in x}) for x in v2["resources"]]
    return ReportPayload(report_id=r["id"], run_id=rc.run_id, title=r["title"], date_label=r["date_label"],
                         window_label=r["window_label"], summary_md=r["summary_md"], summary_text=r["summary_text"],
                         full_md=r["full_md"], html_path=(r.get("files") or {}).get("html"),
                         dashboard_url=ctx["dashboard_url"], headlines=heads,
                         stats={k: rc.stats.get(k) for k in ("messages_raw", "messages_clean", "snr", "speakers", "by_platform")},
                         articles=arts, resources=res, sections=dict(v2["sections"]),
                         assets_dir=str(assets) if assets is not None and assets.is_dir() else None, doc_links={})


async def run(rc: RunContext) -> StageResult:
    ctx = build_context(rc)
    report_id = ctx["report_id"]
    rc.report["id"] = report_id
    day = report_day(rc)
    assets = assets_dir_for(rc.app.paths.reports / day / f"{report_id}.html", report_id)
    copied = await asyncio.to_thread(copy_assets, rc, assets)
    model = build_sections(rc, ctx["items"], report_id)
    sections = section_markdown(model)
    full_md = full_markdown(ctx["title"], ctx["header"], rc.demo, model)
    html_text = render_page(ctx, model)
    policy = policy_of(rc)
    items = [item_dto(it, report_id, policy) for it in ctx["items"]]
    risky = sum(1 for it in ctx["items"] if has_risk(it.risk_flags))
    groups = [g.get("alias") or g["name"] for g in rc.groups if any(s["group_key"] == g["key"] for it in ctx["items"]
                                                                  for s in it.sources)] or [g["name"] for g in rc.stats.get("top_groups", [])]
    meta = summary_meta(groups=groups, date_label=ctx["date_label"], titles=[a["title"] for a in model["articles"]],
                        resources=model["resources"], risky=risky, dashboard_url=ctx["dashboard_url"],
                        dashboard_base=rc.app.dashboard_url(), demo=rc.demo)
    summary_md, summary_text = build_summary(meta)
    v2 = {"version": 2, "sections": sections, "section_counts": model["counts"], "articles": model["articles"],
          "resources": model["resources"], "media": model["media"], "groups": rc.digests,
          "summary": rc.v2.get("summary", ""), "summary_meta": meta, "doc_links": {},
          "risk_policy": policy, "privacy_dropped": int(rc.v2.get("privacy_dropped") or 0),
          "assets": copied}
    rc.report.update({
        "id": report_id, "run_id": rc.run_id, "title": ctx["title"], "date_label": ctx["date_label"],
        "window_label": ctx["window_label"], "window_start": iso(rc.start, rc.tz), "window_end": iso(rc.end, rc.tz),
        "is_demo": rc.demo, "dry_run": rc.dry_run, "created_at": rc.app.store.now_iso(),
        "headlines": [{"title": it.title, "category": it.category, "score": it.score} for it in ctx["heads"]],
        "judgments": [{"text": j["text"], "basis": j.get("basis", ""), "item_ids": j.get("item_ids", [])}
                      for j in rc.judgments],
        "stats": rc.stats, "full_md": full_md, "summary_md": summary_md, "summary_text": summary_text,
        "items": items, "v2_data": v2,
    })
    json_obj = {k: v for k, v in rc.report.items() if k != "files"}
    json_obj["header"] = ctx["header"]
    files = await asyncio.to_thread(write_report_files, rc.app.paths.reports, day, report_id,
                                    md=full_md, html_text=html_text, json_obj=json_obj)
    rc.report["files"] = files
    rc.payload = build_payload(rc, ctx, v2, assets if copied else None)
    c = model["counts"]
    rc.log.info("WRITER", f"报告已排版：12 个板块，专题 {c['articles']} 篇、资源 {c['resources']} 条、提示词 {c['prompts']} 段、"
                          f"风险 {c['risks']} 条、图片与文档 {c['media']} 个（复制图片 {copied} 张）；推送版 {len(summary_md)} 字",
                "render")
    return StageResult(metrics={"items": len(items), "headlines": len(ctx["heads"]), "features": c["articles"],
                                "resources": c["resources"], "prompts": c["prompts"], "risks": c["risks"],
                                "media": c["media"], "assets": copied, "full_md_chars": len(full_md),
                                "summary_chars": len(summary_md), "html_kb": round(len(html_text.encode("utf-8")) / 1024, 1)},
                       message=f"{len(full_md):,} 字 · 专题 {c['articles']}")
