"""报告文件读写：data/reports/<date>/<report_id>.{md,html,json}。流水线和本地归档通道共用。"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path
from typing import Any


def write_report_files(reports_dir: Path, day: str, report_id: str, *, md: str, html_text: str,
                       json_obj: Any) -> dict[str, str]:
    d = reports_dir / day
    d.mkdir(parents=True, exist_ok=True)
    files = {"md": d / f"{report_id}.md", "html": d / f"{report_id}.html", "json": d / f"{report_id}.json"}
    files["md"].write_text(md, encoding="utf-8")
    files["html"].write_text(html_text, encoding="utf-8")
    files["json"].write_text(json.dumps(json_obj, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {k: str(v) for k, v in files.items()}


def payload_from_report(report: dict[str, Any], items: list[dict[str, Any]], dashboard_url: str) -> Any:
    """从数据库里的报告重建 ReportPayload（重新投递用）。"""
    from bureau.contracts import PLATFORM_LABELS, HeadlineBrief, Platform, ReportPayload

    heads = [HeadlineBrief(title=i["title"], hook=i["hook"], category=i["category"], score=i["score"], trend=i["trend"],
                           sources=[f"{PLATFORM_LABELS[Platform(s['platform'])]}·{s['group_name']}" for s in i["sources"][:3]],
                           risk_flags=i["risk_flags"], links=[x["url"] for x in i["links"]])
             for i in items if i.get("is_headline")]
    st = report.get("stats") or {}
    v2 = report.get("v2_data") or {}
    html_path = (report.get("files") or {}).get("html")
    return ReportPayload(report_id=report["id"], run_id=report["run_id"], title=report["title"],
                         date_label=report["date_label"], window_label=report["window_label"],
                         summary_md=report.get("summary_md", ""), summary_text=report.get("summary_text", ""),
                         full_md=report.get("full_md", ""), html_path=html_path,
                         dashboard_url=f"{dashboard_url}/reports?id={report['id']}", headlines=heads,
                         stats={k: st.get(k) for k in ("messages_raw", "messages_clean", "snr", "speakers", "by_platform")},
                         articles=[_article_brief(a) for a in v2.get("articles") or []],
                         resources=[_resource_brief(r) for r in v2.get("resources") or []],
                         sections=dict(v2.get("sections") or {}),
                         assets_dir=str(assets_dir_for(html_path, report["id"])) if html_path and v2 else None,
                         doc_links=dict(v2.get("doc_links") or {}))


def assets_dir_for(html_path: str | Path, report_id: str) -> Path:
    """报告图片目录：data/reports/<date>/<report_id>_assets/（与 HTML 同目录，HTML 用相对路径引用）。"""
    return Path(html_path).parent / f"{report_id}_assets"


def _article_brief(a: dict[str, Any]) -> Any:
    from bureau.contracts import ArticleBrief

    return ArticleBrief(id=a["id"], seq=int(a["seq"]), title=a["title"], hook=a.get("hook", ""),
                        category=a.get("category", ""), body_md=a.get("body_md", ""),
                        risk_flags=list(a.get("risk_flags") or []), risk_note=a.get("risk_note"),
                        sources=list(a.get("source_lines") or []), image_paths=list(a.get("images") or []),
                        kb_id=a.get("kb_id"))


def _resource_brief(r: dict[str, Any]) -> Any:
    from bureau.contracts import ResourceBrief

    return ResourceBrief(kind=r.get("kind") or "other", title=r.get("title") or r["url"], url=r["url"], code=r.get("code"),
                         meta=dict(r.get("meta") or {}), note=r.get("note"), shared_by=r.get("shared_by"),
                         group_name=r.get("group_name"), sent_at=r.get("sent_at") or None)


_INLINE_LINK = re.compile(r"\[([^\]]+)\]\((https?://[^)\s]+)\)")
_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _inline(text: str) -> str:
    t = html.escape(text)
    t = _BOLD.sub(r"<strong>\1</strong>", t)
    return _INLINE_LINK.sub(lambda m: f'<a href="{m.group(2)}" rel="noopener noreferrer">{m.group(1)}</a>', t)


def basic_markdown_html(md: str, title: str) -> str:
    """极简 Markdown → 自包含 HTML（本地归档通道兜底用；正式报告由流水线排版）。"""
    out: list[str] = []
    in_list = False
    for line in md.splitlines():
        s = line.rstrip()
        if in_list and not s.lstrip().startswith(("- ", "* ")):
            out.append("</ul>")
            in_list = False
        if not s:
            continue
        m = re.match(r"^(#{1,4})\s+(.*)$", s)
        if m:
            n = len(m.group(1))
            out.append(f"<h{n}>{_inline(m.group(2))}</h{n}>")
        elif s.startswith(">"):
            out.append(f"<blockquote>{_inline(s.lstrip('> '))}</blockquote>")
        elif s.lstrip().startswith(("- ", "* ")):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(s.lstrip()[2:])}</li>")
        elif s.startswith("|"):
            out.append(f"<pre>{html.escape(s)}</pre>")
        else:
            out.append(f"<p>{_inline(s)}</p>")
    if in_list:
        out.append("</ul>")
    body = "\n".join(out)
    return (f"<!doctype html><html lang=\"zh-CN\"><head><meta charset=\"utf-8\"><title>{html.escape(title)}</title>"
            "<style>body{background:#060b1a;color:#eaf6ff;font-family:'Microsoft YaHei UI','PingFang SC',sans-serif;"
            "max-width:860px;margin:32px auto;padding:0 20px;line-height:1.75}a{color:#22e4ff}"
            "blockquote{border-left:3px solid #22e4ff;margin:8px 0;padding:4px 12px;color:#a9c4dd}"
            "pre{white-space:pre-wrap;color:#a9c4dd}</style></head>"
            f"<body>{body}</body></html>")
