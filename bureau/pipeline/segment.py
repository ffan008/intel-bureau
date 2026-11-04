"""阶段 4 segment：按时间间隔与回复链切成对话线程，再打包成不超过预算的块；块内消息带编号 [m123]。"""

from __future__ import annotations

import asyncio
import hashlib
from collections import defaultdict
from typing import Any

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.timeutil import from_epoch
from bureau.pipeline.models import Chunk, CleanMsg, RunContext, StageResult, Thread

MAX_LINE = 1200          # v2：长提示词要完整进入对话块（原文照录由代码从数据库截取）


def format_line(m: CleanMsg, tz: str) -> str:
    t = from_epoch(m.ts, tz).strftime("%m-%d %H:%M")
    reply = f" ↩{m.reply_ref}" if m.reply_ref else ""
    body = m.text.replace("\n", " / ")
    if len(body) > MAX_LINE:
        body = body[:MAX_LINE] + "…（截断）"
    extra = [u for u in m.urls if u not in body]
    if extra:
        body += " " + " ".join(extra)
    return f"[{m.ref}] {t} {m.sender}{reply}：{body}"


def build_threads(msgs: list[CleanMsg], gap_minutes: int = 20) -> list[Thread]:
    """每个群内：回复链挂到被回复消息所在线程；否则与上一条间隔超过 gap 就开新线程。"""
    by_group: dict[str, list[CleanMsg]] = defaultdict(list)
    for m in msgs:
        by_group[m.group_key].append(m)
    threads: list[Thread] = []
    gap = gap_minutes * 60
    for key, gm in by_group.items():
        gm.sort(key=lambda m: (m.ts, m.id))
        ref_thread: dict[str, Thread] = {}
        current: Thread | None = None
        last_ts = None
        for m in gm:
            target = ref_thread.get(m.reply_ref) if m.reply_ref else None   # 回复链优先
            if target is None:
                if current is None or last_ts is None or m.ts - last_ts > gap:
                    current = Thread(id=f"t{len(threads) + 1}", group_key=key)
                    threads.append(current)
                target = current
            target.msgs.append(m)
            m.thread_id = target.id
            ref_thread[m.ref] = target
            last_ts = m.ts
    return threads


def pack_chunks(threads: list[Thread], tz: str, budget: int = 6000) -> list[Chunk]:
    by_group: dict[str, list[Thread]] = defaultdict(list)
    for t in threads:
        by_group[t.group_key].append(t)
    chunks: list[Chunk] = []
    for key, ts in by_group.items():
        ts.sort(key=lambda t: t.msgs[0].ts)
        first = ts[0].msgs[0]
        header = f"群：{first.group_name}（{PLATFORM_LABELS.get(Platform(first.platform), first.platform)}）"
        cur_msgs: list[CleanMsg] = []
        cur_lines: list[str] = []
        size = len(header)

        def flush() -> None:
            nonlocal cur_msgs, cur_lines, size
            if cur_msgs:
                text = header + "\n" + "\n".join(cur_lines)
                h = hashlib.sha256(text.encode("utf-8")).hexdigest()
                speakers = len({m.sender for m in cur_msgs})
                prio = len(cur_msgs) + 2 * speakers + 3 * sum(1 for m in cur_msgs if m.urls) + \
                    2 * sum(1 for m in cur_msgs if m.reply_ref) + sum(len(m.text) for m in cur_msgs) / 200
                prio *= max(0.2, cur_msgs[0].group_weight)
                chunks.append(Chunk(id=f"c{len(chunks) + 1}", group_key=key, group_name=first.group_name,
                                    platform=first.platform, msgs=cur_msgs, text=text, hash=h, priority=round(prio, 2)))
            cur_msgs, cur_lines, size = [], [], len(header)

        for t in ts:
            lines = [format_line(m, tz) for m in t.msgs]
            tsize = sum(len(x) + 1 for x in lines)
            if size + tsize > budget and cur_msgs:
                flush()
            for m, line in zip(t.msgs, lines):
                if size + len(line) + 1 > budget and cur_msgs:
                    flush()
                cur_msgs.append(m)
                cur_lines.append(line)
                size += len(line) + 1
        flush()
    return chunks


def route_chunks(chunks: list[Chunk], max_llm: int) -> None:
    """按优先级选出最多 max_llm 块交给模型，其余用离线规则提取。"""
    ranked = sorted(chunks, key=lambda c: -c.priority)
    llm_ids = {c.id for c in ranked[:max(0, max_llm)]}
    for c in chunks:
        c.route = "llm" if c.id in llm_ids else "offline"


async def run(rc: RunContext) -> StageResult:
    gap = int(rc.cfg("pipeline.segment_gap_minutes", 20))
    budget = int(rc.cfg("llm.chunk_chars", 6000))

    def work() -> tuple[list[Thread], list[Chunk]]:
        threads = build_threads(rc.clean, gap)
        return threads, pack_chunks(threads, rc.tz, budget)

    rc.threads, rc.chunks = await asyncio.to_thread(work)
    route_chunks(rc.chunks, int(rc.cfg("llm.max_chunks", 40)))
    rc.totals["chunks"] = len(rc.chunks)
    sizes: dict[str, Any] = {"threads": len(rc.threads), "chunks": len(rc.chunks),
                             "avg_chunk_chars": int(sum(len(c.text) for c in rc.chunks) / len(rc.chunks)) if rc.chunks else 0,
                             "multi_msg_threads": sum(1 for t in rc.threads if len(t.msgs) > 1)}
    rc.log.info("ANALYST", f"切分出 {len(rc.threads):,} 个对话线程，打包成 {len(rc.chunks)} 个块（每块不超过 {budget:,} 字）",
                "segment")
    return StageResult(metrics=sizes, message=f"{len(rc.chunks)} 块")
