"""导入聊天记录文件（wechat.file_import / qq.file_import / feishu.file_import 共用）。

把导出文件放进 ``data/inbox/<platform>/``（.json / .jsonl / .zip / .csv / .tsv / .txt / .md），
定时任务会按时间窗口取出对应群的消息。处理进度按 文件哈希 × 群 记在
``data/inbox/<platform>/.processed.json``：某个群在这份文件里的最后一条消息早于本次窗口终点，
就标记为已处理，之后不再重复读取。想重新导入时删除该文件（或其中对应条目）即可。

``parse_export`` 的实现在 ``bureau.integrations.export_parsers``，这里按 ARCHITECTURE §5 的约定导出。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from bureau.collectors.base import Collector, CollectorContext
from bureau.contracts import ConfigField, FetchResult, GroupInfo, Health, HealthStatus, ParsedImport, Platform
from bureau.integrations.export_parsers import ImportFormatError, parse_export, parse_export_all

__all__ = ["FileImportCollector", "ImportFormatError", "parse_export", "parse_export_all"]

SUFFIXES = {".json", ".jsonl", ".zip", ".csv", ".tsv", ".txt", ".md", ".log"}
MAX_FILE_BYTES = 300 * 1024 * 1024
PROCESSED_NAME = ".processed.json"

_CACHE: OrderedDict[tuple[str, str, str], list[ParsedImport]] = OrderedDict()
_CACHE_LOCK = threading.Lock()
_CACHE_SIZE = 16
_STATE_LOCK = threading.Lock()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _parse_cached(path: Path, digest: str, platform: Platform, tz: str) -> list[ParsedImport]:
    key = (digest, platform.value, tz)
    with _CACHE_LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    results = parse_export_all(path.read_bytes(), filename=path.name, platform=platform, group_name=None, tz=tz)
    with _CACHE_LOCK:
        _CACHE[key] = results
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return results


class FileImportCollector(Collector):
    """三个平台共用；平台取 ``ctx.platform``，注册表键随之变为 ``<platform>.file_import``。"""

    key = "wechat.file_import"
    label = "导入聊天记录文件"
    platforms = (Platform.WECHAT, Platform.QQ, Platform.FEISHU)
    supports_realtime = False

    def __init__(self, ctx: CollectorContext) -> None:
        super().__init__(ctx)
        self.platform = Platform(ctx.platform)
        self.key = f"{self.platform.value}.file_import"      # 实例级覆盖，便于日志区分平台
        self.inbox = Path(ctx.data_dir) / "inbox" / self.platform.value
        self.state_path = self.inbox / PROCESSED_NAME

    @classmethod
    def config_schema(cls) -> list[ConfigField]:
        return []

    # ---------------------------------------------------------------- 文件与进度
    def _files(self) -> list[Path]:
        if not self.inbox.is_dir():
            return []
        out = []
        for p in sorted(self.inbox.iterdir()):
            if p.is_file() and not p.name.startswith((".", "~$")) and p.suffix.lower() in SUFFIXES:
                if p.stat().st_size <= MAX_FILE_BYTES:
                    out.append(p)
                else:
                    self.ctx.logger.warning("导入文件过大，已跳过：%s", p.name)
        return out

    def _load_state(self) -> dict[str, Any]:
        try:
            data = json.loads(self.state_path.read_text("utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_state(self, state: dict[str, Any]) -> None:
        self.inbox.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.inbox, prefix=".processed-", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(state, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, self.state_path)

    def _scan(self) -> list[tuple[Path, str, list[ParsedImport] | None, str | None]]:
        """读取并解析 inbox 里的全部文件：[(路径, 哈希, 解析结果或 None, 错误)]。"""
        out = []
        for p in self._files():
            digest = _sha256(p)
            try:
                out.append((p, digest, _parse_cached(p, digest, self.platform, self.ctx.tz), None))
            except ImportFormatError as exc:
                out.append((p, digest, None, str(exc)))
            except (OSError, ValueError) as exc:
                out.append((p, digest, None, f"读取失败：{type(exc).__name__}"))
        return out


    # ---------------------------------------------------------------- 接口
    async def health(self) -> HealthStatus:
        def check() -> tuple[int, int]:
            # 只看文件名和大小，不计算哈希，保证几秒内返回
            self.inbox.mkdir(parents=True, exist_ok=True)
            files = self._files()
            known = {(v.get("name"), v.get("size")): v for v in self._load_state().values() if isinstance(v, dict)}
            pending = 0
            for p in files:
                groups = (known.get((p.name, p.stat().st_size)) or {}).get("groups") or {}
                if not groups or any(not g.get("done") for g in groups.values()):
                    pending += 1
            return len(files), pending

        try:
            total, pending = await asyncio.to_thread(check)
        except OSError as exc:
            return HealthStatus(ok=False, state=Health.DOWN, detail=f"无法访问导入目录：{type(exc).__name__}",
                                hint=f"检查目录权限：{self.inbox}")
        data = {"inbox": str(self.inbox), "files": total, "pending": pending}
        if not total:
            return HealthStatus(ok=True, state=Health.OK, data=data, detail="导入目录为空",
                                hint=f"把导出的 JSON / CSV / TXT 文件放进 {self.inbox}，或在工作台里直接粘贴聊天记录")
        return HealthStatus(ok=True, state=Health.OK, data=data,
                            detail=f"导入目录里有 {total} 个文件，其中 {pending} 个还有未处理的消息")

    async def list_groups(self) -> list[GroupInfo]:
        scanned = await asyncio.to_thread(self._scan)
        groups: dict[str, GroupInfo] = {}
        for p, _digest, results, err in scanned:
            if err:
                self.ctx.logger.warning("导入文件无法识别：%s（%s）", p.name, err[:80])
                continue
            for r in results or []:
                g = groups.get(r.group.native_id)
                if g is None:
                    g = r.group.model_copy(update={"extra": {**r.group.extra, "files": [], "messages": 0}})
                    groups[r.group.native_id] = g
                g.extra["files"].append(p.name)
                g.extra["messages"] += len(r.messages)
                g.extra["format"] = r.format
        return list(groups.values())

    async def fetch_messages(self, group: GroupInfo, since: datetime, until: datetime, *,
                             cursor: str | None = None, limit: int = 5000) -> FetchResult:
        return await asyncio.to_thread(self._fetch_sync, group, since, until, limit)


    def _fetch_sync(self, group: GroupInfo, since: datetime, until: datetime, limit: int) -> FetchResult:
        state = self._load_state()
        found: dict[str, Any] = {}
        warnings: list[str] = []
        updates: dict[str, dict[str, Any]] = {}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for p in self._files():
            digest = _sha256(p)
            if ((state.get(digest) or {}).get("groups") or {}).get(group.native_id, {}).get("done"):
                continue
            try:
                results = _parse_cached(p, digest, self.platform, self.ctx.tz)
            except (ImportFormatError, OSError, ValueError) as exc:
                warnings.append(f"{p.name} 无法解析：{exc}"[:200])
                continue
            upd = updates.setdefault(digest, {"name": p.name, "size": p.stat().st_size, "groups": {}})
            for r in results:
                upd["groups"].setdefault(r.group.native_id, {
                    "name": r.group.name, "count": len(r.messages), "format": r.format, "done": False,
                    "last": r.messages[-1].sent_at.isoformat() if r.messages else None})
            matched = [r for r in results if r.group.native_id == group.native_id] or \
                      [r for r in results if r.group.name == group.name]
            for r in matched:
                for m in r.messages:
                    if since <= m.sent_at < until:
                        found.setdefault(m.native_id, m.model_copy(update={"group_native_id": group.native_id}))
                warnings.extend(f"{p.name}：{w}" for w in r.warnings)
                if not r.messages or r.messages[-1].sent_at < until:
                    upd["groups"][r.group.native_id].update(done=True, processed_at=now)
                    if r.group.native_id != group.native_id:       # 按群名匹配上的，也按查询用的 ID 记一份
                        upd["groups"][group.native_id] = {**upd["groups"][r.group.native_id], "name": group.name}
        if updates:
            self._merge_state(updates)
        msgs = sorted(found.values(), key=lambda r: (r.sent_at, r.native_id))
        complete = True
        if len(msgs) > limit:
            msgs, complete = msgs[-limit:], False
            warnings.append(f"超过单群上限 {limit} 条，只保留最近的 {limit} 条")
        return FetchResult(messages=msgs, complete=complete, warnings=list(dict.fromkeys(warnings)))

    def _merge_state(self, updates: dict[str, dict[str, Any]]) -> None:
        """按 文件 × 群 合并写入进度，避免同平台并发拉取时互相覆盖。"""
        with _STATE_LOCK:
            cur = self._load_state()
            for digest, upd in updates.items():
                entry = cur.setdefault(digest, {"groups": {}})
                entry["name"], entry["size"] = upd["name"], upd["size"]
                groups = entry.setdefault("groups", {})
                for gid, g in upd["groups"].items():
                    old = groups.get(gid) or {}
                    groups[gid] = old if old.get("done") else {**old, **g}
            try:
                self._save_state(cur)
            except OSError as exc:
                self.ctx.logger.warning("写入导入进度失败：%s", type(exc).__name__)