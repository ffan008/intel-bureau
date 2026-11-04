"""阶段 3 stats：纯代码统计 + 关键词风向（与过去 7 天比较的 z 值）。overview 也复用这里的函数。"""

from __future__ import annotations

import asyncio
import math
import threading
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from bureau.core.constants import MSG_KIND_LABELS
from bureau.core.dto import empty_stats
from bureau.core.nlp import NLP_INSTANCE
from bureau.core.timeutil import epoch, from_epoch
from bureau.pipeline.clean import clean_rows
from bureau.pipeline.models import CleanMsg, RunContext, StageResult

_BASE_CACHE: dict[tuple[Any, ...], Counter[str] | None] = {}
_BASE_LOCK = threading.Lock()


def msg_words(text: str) -> set[str]:
    return set(NLP_INSTANCE.tokens(text))


def baseline_counts(app: Any, keys: list[str], end: datetime, scope: str, cfg: dict[str, Any],
                    privacy: dict[str, Any]) -> list[Counter[str] | None]:
    """过去 7 天每天（以 end 为准往前 24 小时为一天）每个词出现在多少条有效消息里；没有数据的日子为 None。"""
    out: list[Counter[str] | None] = []
    days = [(end - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7, 0, -1)]
    stored = app.store.keyword_daily_days(scope, days)
    for i in range(7, 0, -1):
        s, e = end - timedelta(days=i + 1), end - timedelta(days=i)
        q = ",".join("?" * len(keys)) or "''"
        sig = app.db.query_one(f"SELECT COUNT(*) AS n, MAX(id) AS mx FROM messages WHERE group_key IN ({q}) "
                               "AND ts>=? AND ts<?", [*keys, epoch(s), epoch(e)]) or {"n": 0, "mx": 0}
        ck = (str(app.db.path), scope, epoch(e), int(sig["n"] or 0), int(sig["mx"] or 0), hash(tuple(sorted(keys))))
        with _BASE_LOCK:
            hit = _BASE_CACHE.get(ck, "miss")
        if hit != "miss":
            out.append(hit)                                    # type: ignore[arg-type]
            continue
        counter: Counter[str] | None = None
        if sig["n"]:
            rows = app.store.messages_in_window(keys, s, e)
            clean, _ = clean_rows(rows, cfg, privacy)
            counter = Counter()
            for m in clean:
                counter.update(msg_words(m.text))
        else:
            day = (end - timedelta(days=i)).strftime("%Y-%m-%d")
            if day in stored:
                counter = Counter(stored[day])
        with _BASE_LOCK:
            if len(_BASE_CACHE) > 200:
                _BASE_CACHE.clear()
            _BASE_CACHE[ck] = counter
        out.append(counter)
    return out


def compute_stats(raw: list[dict[str, Any]], clean: list[CleanMsg], *, end: datetime, tz: str,
                  week_ts: list[tuple[int, str]], baseline: list[Counter[str] | None],
                  rising_z: float = 2.0, rising_min: int = 5) -> tuple[dict[str, Any], dict[str, Any]]:
    st = empty_stats()
    raw_n, clean_n = len(raw), len(clean)
    st["messages_raw"], st["messages_clean"] = raw_n, clean_n
    st["snr"] = round(clean_n / raw_n, 4) if raw_n else 0.0
    human = [r for r in raw if r.get("kind") not in ("system", "recall")]
    st["speakers"] = len({(r["group_key"], r.get("sender_name")) for r in human})
    by_p: dict[str, dict[str, Any]] = {}
    for r in raw:
        d = by_p.setdefault(r["platform"], {"platform": r["platform"], "messages": 0, "groups": set()})
        d["messages"] += 1
        d["groups"].add(r["group_key"])
    st["by_platform"] = [{"platform": d["platform"], "messages": d["messages"], "groups": len(d["groups"])}
                         for d in sorted(by_p.values(), key=lambda d: -d["messages"])]
    for r in raw:
        h = from_epoch(r["ts"], tz).hour
        st["hourly"][h][r["platform"] if r["platform"] in ("wechat", "qq", "feishu", "demo") else "demo"] += 1
    end_ts = epoch(end)
    grid = Counter()
    for ts, _p in week_ts:
        d = 6 - int((end_ts - 1 - ts) // 86400)
        if 0 <= d <= 6:
            grid[(d, from_epoch(ts, tz).hour)] += 1
    st["heat_7x24"] = [[d, h, grid.get((d, h), 0)] for d in range(7) for h in range(24)]
    kinds = Counter(r.get("kind") or "other" for r in raw)
    st["msg_types"] = [{"kind": k, "label": MSG_KIND_LABELS.get(k, k), "count": n} for k, n in kinds.most_common()]
    # 群热度：有效消息、发言人数、回复数
    per_g: dict[str, dict[str, Any]] = {}
    for r in raw:
        g = per_g.setdefault(r["group_key"], {"group_key": r["group_key"], "name": r.get("group_name") or r["group_key"],
                                              "platform": r["platform"], "messages": 0, "speakers": set(), "clean": 0,
                                              "replies": 0})
        g["messages"] += 1
        if r.get("kind") not in ("system", "recall"):
            g["speakers"].add(r.get("sender_name"))
    for m in clean:
        g = per_g[m.group_key]
        g["clean"] += 1
        g["replies"] += 1 if m.reply_ref else 0
    raw_heat = {k: g["clean"] + 3 * len(g["speakers"]) + 2 * g["replies"] for k, g in per_g.items()}
    mx = max(raw_heat.values(), default=0) or 1
    st["top_groups"] = sorted(({"group_key": k, "name": g["name"], "platform": g["platform"], "messages": g["messages"],
                                "speakers": len(g["speakers"]), "heat": round(100 * raw_heat[k] / mx, 1)}
                               for k, g in per_g.items()), key=lambda x: -x["heat"])
    spk = Counter((r.get("sender_name"), r.get("group_name") or r["group_key"]) for r in human)
    st["top_speakers"] = [{"name": n, "group_name": g, "messages": c} for (n, g), c in spk.most_common(10)]
    # 关键词
    word_count: Counter[str] = Counter()
    word_groups: dict[str, Counter[str]] = defaultdict(Counter)
    group_names = {k: g["name"] for k, g in per_g.items()}
    for m in clean:
        ws = msg_words(m.text)
        word_count.update(ws)
        for w in ws:
            word_groups[w][m.group_key] += 1
    valid_days = [b for b in baseline if b is not None]
    rising: list[dict[str, Any]] = []
    trend: dict[str, str] = {}
    for w, today in word_count.items():
        if today < rising_min or len(valid_days) < 3:
            continue
        hist = [b.get(w, 0) for b in valid_days]
        avg = sum(hist) / len(hist)
        std = max(1.0, math.sqrt(sum((x - avg) ** 2 for x in hist) / len(hist)))
        z = (today - avg) / std
        is_new = sum(hist) == 0
        if z >= rising_z or is_new:
            trend[w] = "new" if is_new else "up"
            spark = [(b.get(w, 0) if b is not None else 0) for b in baseline[1:]] + [today]
            rising.append({"word": w, "today": today, "avg7": round(avg, 2), "z": round(z, 2),
                           "groups": [group_names.get(k, k) for k, _ in word_groups[w].most_common(3)], "spark": spark})
    rising.sort(key=lambda x: (-x["z"], -x["today"]))
    st["rising"] = rising[:6]
    weights = {w: c * NLP_INSTANCE.idf_of(w) for w, c in word_count.items() if c >= 2}
    top = sorted(weights.items(), key=lambda kv: -kv[1])[:80]
    wmax = top[0][1] if top else 1.0
    st["keywords"] = [{"word": w, "weight": round(100 * v / wmax, 1), "trend": trend.get(w, "flat")} for w, v in top]
    internal = {
        "word_count": word_count,
        "word_groups": {w: dict(word_groups[w]) for w, _ in top},
        "archive_counts": dict(word_count.most_common(400)),
        "archive_groups": {w: [group_names.get(k, k) for k, _ in word_groups[w].most_common(5)]
                           for w, _ in word_count.most_common(400)},
        "group_heat": {k: v / mx for k, v in raw_heat.items()},
        "baseline_days": len(valid_days),
    }
    return st, internal


def week_timestamps(app: Any, keys: list[str], end: datetime) -> list[tuple[int, str]]:
    if not keys:
        return []
    q = ",".join("?" * len(keys))
    rows = app.db.query(f"SELECT ts, platform FROM messages WHERE group_key IN ({q}) AND ts>=? AND ts<?",
                        [*keys, epoch(end - timedelta(days=7)), epoch(end)])
    return [(int(r["ts"]), r["platform"]) for r in rows]


def stats_for(app: Any, keys: list[str], raw: list[dict[str, Any]], clean: list[CleanMsg], end: datetime,
              scope: str, settings: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    pipe = settings.get("pipeline", {}) or {}
    base = baseline_counts(app, keys, end, scope, pipe.get("clean", {}) or {}, settings.get("privacy", {}) or {})
    return compute_stats(raw, clean, end=end, tz=app.tz, week_ts=week_timestamps(app, keys, end), baseline=base,
                         rising_z=float(pipe.get("rising_z", 2.0)), rising_min=int(pipe.get("rising_min_count", 5)))


async def run(rc: RunContext) -> StageResult:
    keys = [g["key"] for g in rc.groups]
    rc.stats, rc.stats_internal = await asyncio.to_thread(stats_for, rc.app, keys, rc.raw, rc.clean, rc.end, rc.scope,
                                                          rc.settings)
    st = rc.stats
    top_g = st["top_groups"][0]["name"] if st["top_groups"] else "—"
    rising = "、".join(r["word"] for r in st["rising"][:4]) or "无"
    rc.log.info("ANALYST", f"统计完成：{st['speakers']} 位发言人，最热群「{top_g}」，关键词 {len(st['keywords'])} 个，"
                           f"上升信号 {len(st['rising'])} 个（{rising}）", "stats")
    if rc.stats_internal.get("baseline_days", 0) < 3:
        rc.log.info("ANALYST", "历史数据不足 3 天，暂不计算上升信号", "stats")
    return StageResult(metrics={"speakers": st["speakers"], "keywords": len(st["keywords"]), "rising": len(st["rising"]),
                                "groups": len(st["top_groups"]), "baseline_days": rc.stats_internal.get("baseline_days", 0)},
                       message=f"上升信号 {len(st['rising'])} 个")
