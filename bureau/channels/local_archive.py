"""本地归档通道：把报告写入 data/reports/<date>/<report_id>.{md,html,json}。始终可用，作兜底。"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bureau.channels.base import Channel
from bureau.contracts import ConfigField, DeliveryResult, ReportPayload
from bureau.core.reportfiles import basic_markdown_html


class LocalArchiveChannel(Channel):
    kind = "local_archive"
    label = "本地归档"
    platform_label = "本地"

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return []

    def _target_dir(self, report: ReportPayload) -> Path:
        if report.html_path:
            p = Path(report.html_path)
            if p.parent.exists():
                return p.parent
        day = datetime.now(ZoneInfo(self.ctx.tz)).strftime("%Y-%m-%d")
        return self.ctx.data_dir / "reports" / day

    def _write(self, report: ReportPayload) -> tuple[Path, list[str]]:
        d = self._target_dir(report)
        d.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        md = d / f"{report.report_id}.md"
        md.write_text(report.full_md, encoding="utf-8")
        written.append(md.name)
        html_file = d / f"{report.report_id}.html"
        src = Path(report.html_path) if report.html_path else None
        if src is not None and src.exists():
            if src.resolve() != html_file.resolve():
                html_file.write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
        else:
            html_file.write_text(basic_markdown_html(report.full_md, report.title), encoding="utf-8")
        written.append(html_file.name)
        js = d / f"{report.report_id}.json"
        if not js.exists() or report.is_test:
            js.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2), encoding="utf-8")
        written.append(js.name)
        return d, written

    async def send(self, report: ReportPayload) -> DeliveryResult:
        try:
            d, written = await asyncio.to_thread(self._write, report)
        except OSError as exc:
            return self.result(False, f"写入本地归档失败：{exc}")
        return self.result(True, f"已归档到 {d}（{'、'.join(written)}）", external_id=str(d / f"{report.report_id}.md"))
