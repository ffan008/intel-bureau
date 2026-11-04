"""演示采集器：返回合成的三平台群与消息（离线、确定性）。"""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

from bureau.collectors.base import Collector
from bureau.contracts import ConfigField, FetchResult, GroupInfo, Health, HealthStatus, Platform
from bureau.core.timeutil import now, parse_iso


class DemoCollector(Collector):
    key: ClassVar[str] = "demo.synthetic"
    label: ClassVar[str] = "演示数据（合成）"
    platforms: ClassVar[tuple[Platform, ...]] = (Platform.WECHAT, Platform.QQ, Platform.FEISHU, Platform.DEMO)

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return [ConfigField(key="scale", label="数据量倍数", type="number", default=1.0,
                            help="1.0 约 1 万条消息；调小可加快演示")]

    @property
    def anchor(self) -> datetime:
        a = parse_iso(str(self.ctx.settings.get("anchor") or ""), self.ctx.tz)
        return a or now(self.ctx.tz).replace(minute=0, second=0, microsecond=0)

    @property
    def scale(self) -> float:
        try:
            return float(self.ctx.settings.get("scale") or 1.0)
        except (TypeError, ValueError):
            return 1.0

    @property
    def media_dir(self) -> str:
        """演示素材目录（v2：图片和文档附件的 extra.fetch.path 指向这里）。"""
        return str(self.ctx.settings.get("media_dir") or (self.ctx.data_dir / "demo_media"))

    def _data(self):
        from bureau.demo.generator import generate

        return generate(self.anchor, self.scale, self.media_dir)

    async def health(self) -> HealthStatus:
        return HealthStatus(ok=True, state=Health.OK, detail="演示数据可用：9 个群 × 7 天合成消息",
                            data={"anchor": self.anchor.isoformat()})

    async def list_groups(self) -> list[GroupInfo]:
        return list(self._data().groups)

    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        msgs = [m for m in self._data().messages
                if m.group_native_id == group.native_id and since <= m.sent_at < until]
        msgs.sort(key=lambda m: m.sent_at)
        complete = len(msgs) <= limit
        return FetchResult(messages=msgs[:limit], complete=complete,
                           next_cursor=msgs[min(len(msgs), limit) - 1].native_id if msgs else cursor)
