"""阶段 2 clean：去噪、跨群去重（记录扩散度）、抽取 URL、按配置脱敏。

v2：图片和文件消息不再丢弃。带有可取回信息（链接、平台文件标识、文件名）的图片 / 文件作为媒体候选保留，
正文换成占位符 ``[图片#m12]``、``[文件:名称#m13]`` 进入对话块，让模型能引用。表情包照旧丢弃；
没有任何可取回信息的 ``[图片]`` 也照旧按低信息量剔除（没人能看到它）。
"""

from __future__ import annotations

import asyncio
import re
from collections import Counter
from typing import Any

from bureau.core.textutil import desensitize, extract_urls, info_chars, is_emoji_only, norm_for_dedupe
from bureau.pipeline.models import CleanMsg, RunContext, StageResult, StopPipeline

DROP_LABELS = {"kind": "系统 / 撤回 / 红包 / 表情", "low_info": "低信息量", "short": "过短", "emoji": "纯表情",
               "dup_cross": "跨群重复", "dup_same": "同群重复", "self": "自己发的"}
MEDIA_LABEL = {"image": "图片", "file": "文件"}
_LEAD = re.compile(r"^\[(?:图片|文件|视频)\]\s*")


def media_of(r: dict[str, Any]) -> dict[str, Any] | None:
    """图片 / 文件消息 → 媒体候选；没有可取回信息时返回 None。"""
    kind = r.get("kind")
    if kind not in MEDIA_LABEL:
        return None
    atts = [a for a in (r.get("attachments") or []) if isinstance(a, dict) and a.get("kind") == kind]
    if not atts:
        return None
    a = atts[0]
    extra = a.get("extra") or {}
    if not (a.get("url") or extra or a.get("title")):
        return None
    name = str(a.get("title") or "").strip()
    if kind == "file" and not name:
        name = _LEAD.sub("", (r.get("text") or "").strip()).strip()
    key = extra.get("imageMd5") or extra.get("fileMd5") or extra.get("sha256") or a.get("url") or ""
    return {"kind": kind, "name": name[:80], "attachment": a, "dedupe": f"media:{key}" if key else ""}


def _caption(text: str, name: str) -> str:
    t = _LEAD.sub("", (text or "").strip())
    if name and t.startswith(name):
        t = t[len(name):]
    return t.strip(" ：:")


def clean_rows(rows: list[dict[str, Any]], cfg: dict[str, Any], privacy: dict[str, Any]) -> tuple[list[CleanMsg], dict[str, Any]]:
    """纯函数：原始消息行 → 清洗后的消息与统计。rows 需按时间升序。"""
    drop_kinds = set(cfg.get("drop_kinds") or ["system", "recall", "redpacket", "sticker"])
    patterns = [re.compile(p) for p in (cfg.get("low_info_patterns") or [])]
    min_chars = int(cfg.get("min_chars", 4))
    dedupe_min = int(cfg.get("dedupe_min_chars", 12))
    kinds = (privacy.get("desensitize") or []) if cfg.get("desensitize", True) else []
    drops: Counter[str] = Counter()
    seen: dict[str, CleanMsg] = {}
    out: list[CleanMsg] = []
    masked = 0
    for r in rows:
        raw_text = (r.get("text") or "").strip()
        text = raw_text
        if r.get("kind") in drop_kinds:
            drops["kind"] += 1
            continue
        media = media_of(r)
        if media is None:
            if any(p.search(text) for p in patterns):
                drops["low_info"] += 1
                continue
            if is_emoji_only(text):
                drops["emoji"] += 1
                continue
        att_urls = [a.get("url") for a in (r.get("attachments") or [])
                    if isinstance(a, dict) and a.get("url") and a.get("kind") not in MEDIA_LABEL]
        urls = list(dict.fromkeys([*extract_urls(text), *att_urls]))
        if media is None and info_chars(text) < min_chars and not urls:
            drops["short"] += 1
            continue
        key = media["dedupe"] if media else norm_for_dedupe(text)
        if (media is not None or len(key) >= dedupe_min) and key and key in seen:
            first = seen[key]
            first.dup_count += 1
            if r["group_key"] != first.group_key:
                if r["group_key"] not in first.spread_groups:
                    first.spread_groups.append(r["group_key"])
                drops["dup_cross"] += 1
            else:
                drops["dup_same"] += 1
            continue
        if media is not None:
            text = _caption(text, media["name"])
        if kinds:
            text, n = desensitize(text, kinds)
            masked += n
            if media is not None and media["name"]:
                media["name"], n2 = desensitize(media["name"], kinds)
                masked += n2
        m = CleanMsg(id=r["id"], ref="", group_key=r["group_key"], group_name=r.get("group_name") or r["group_key"],
                     platform=r["platform"], native_id=r["native_id"], sender=r.get("sender_name") or "匿名",
                     sent_at=r["sent_at"], ts=int(r["ts"]), kind=r.get("kind") or "text", text=text, urls=urls,
                     reply_to=r.get("reply_to"), group_weight=float(r.get("group_weight") or 1.0),
                     raw_text=raw_text, media=media)
        if key and (media is not None or len(key) >= dedupe_min):
            seen[key] = m
        out.append(m)
    by_native: dict[tuple[str, str], CleanMsg] = {}
    for i, m in enumerate(out, start=1):
        m.ref = f"m{i}"
        by_native[(m.group_key, m.native_id)] = m
        if m.media is not None:
            label = MEDIA_LABEL[m.media["kind"]]
            ph = f"[{label}:{m.media['name']}#{m.ref}]" if m.media["kind"] == "file" and m.media["name"] else \
                f"[{label}#{m.ref}]"
            m.text = ph + (" " + m.text if m.text else "")
    for m in out:
        if m.reply_to:
            target = by_native.get((m.group_key, m.reply_to))
            if target is not None:
                m.reply_ref = target.ref
    raw_n = len(rows)
    info = {"raw": raw_n, "clean": len(out), "snr": round(len(out) / raw_n, 4) if raw_n else 0.0,
            "drops": dict(drops), "masked": masked,
            "spread": sum(1 for m in out if m.spread_groups),
            "media": sum(1 for m in out if m.media is not None)}
    return out, info


async def run(rc: RunContext) -> StageResult:
    cfg = rc.cfg("pipeline.clean", {}) or {}
    privacy = rc.cfg("privacy", {}) or {}
    rc.clean, info = await asyncio.to_thread(clean_rows, rc.raw, cfg, privacy)
    rc.by_ref = {m.ref: m for m in rc.clean}
    rc.totals["messages_clean"] = len(rc.clean)
    drops = info["drops"]
    metrics = {"raw": info["raw"], "clean": info["clean"], "snr": info["snr"], "dropped": info["raw"] - info["clean"],
               "cross_group_dups": drops.get("dup_cross", 0), "spread_msgs": info["spread"], "masked": info["masked"],
               "media_candidates": info["media"]}
    detail = "、".join(f"{DROP_LABELS.get(k, k)} {v}" for k, v in sorted(drops.items(), key=lambda kv: -kv[1]))
    rc.log.info("SWEEPER", f"清洗 {info['raw']:,} → {info['clean']:,} 条（信噪比 {info['snr'] * 100:.1f}%）；剔除：{detail or '无'}",
                "clean")
    if info["media"]:
        rc.log.info("SWEEPER", f"保留图片 / 文件候选 {info['media']} 条（正文用占位符，供提取时引用）", "clean")
    if info["masked"]:
        rc.log.info("SWEEPER", f"已脱敏 {info['masked']} 处（手机号、邮箱、证件号等）", "clean")
    if not rc.clean:
        raise StopPipeline("清洗后没有有效消息")
    return StageResult(metrics=metrics, message=f"{info['raw']:,} → {info['clean']:,}")
