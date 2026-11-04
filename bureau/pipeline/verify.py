"""阶段 8 verify：
- 证据摘录必须是对应消息原文的子串（忽略空白）；URL 必须出现在来源消息里；没有有效证据的条目剔除；
- 导语、摘要、步骤里有原文找不到的数字时标"待核实"；
- v2：prompts、quotes、data_points、media_refs、tool_notes 的消息引用必须指向话题内的真实消息；
  提示词原文和网盘提取码由代码从数据库原文截取（不用模型给的文字），截取不到的丢弃。
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from bureau.core.textutil import desensitize, norm_url, number_supported, numbers_in, share_code, strip_ws
from bureau.pipeline.links import classify, default_title, netdisk_provider
from bureau.pipeline.models import CleanMsg, Item, RunContext, StageResult
from bureau.pipeline.risk import policy_of
from bureau.pipeline.score import max_features_of, select_v2

_ELLIPSIS = re.compile(r"…+|\.{3,}|。。。")
PROMPT_MIN = 12


def quote_in(quote: str, source: str) -> bool:
    q, s = strip_ws(quote), strip_ws(source)
    if not q:
        return False
    if q in s:
        return True
    parts = [p for p in (strip_ws(x) for x in _ELLIPSIS.split(quote)) if p]
    if len(parts) > 1 and all(len(p) >= 4 for p in parts):
        pos = 0
        for p in parts:
            idx = s.find(p, pos)
            if idx < 0:
                return False
            pos = idx + len(p)
        return True
    return False


def evidence_dto(m: CleanMsg, quote: str, platform_of: dict[str, str]) -> dict[str, Any]:
    return {"message_id": str(m.id), "group_key": m.group_key, "group_name": m.group_name,
            "platform": platform_of.get(m.group_key, m.platform), "sender": m.sender, "sent_at": m.sent_at,
            "quote": quote[:80], "ref": m.ref}


def _norm_index(raw: str) -> tuple[str, list[int]]:
    """原文去空白、全角转半角（NFKC）后的字符串，以及每个字符在原文里的位置。"""
    chars: list[str] = []
    pos: list[int] = []
    for i, ch in enumerate(raw):
        n = unicodedata.normalize("NFKC", ch)
        for c in n:
            if not c.isspace():
                chars.append(c)
                pos.append(i)
    return "".join(chars), pos


def slice_original(raw: str, excerpt: str) -> str | None:
    """在数据库原文 raw 里定位 excerpt，返回原文中的那一段（逐字，不用模型的文字）。
    依次尝试：原样子串 → 忽略空白与全半角的子串 → 按首尾各几个字定位（容忍模型改了中间个别字）。
    都找不到返回 None（调用方丢弃这段提示词）。"""
    raw = raw or ""
    ex = (excerpt or "").strip()
    if not ex:
        return raw.strip() or None
    i = raw.find(ex)
    if i >= 0:
        return raw[i:i + len(ex)]
    norm, pos = _norm_index(raw)
    exn = strip_ws(ex)
    if not exn or not norm:
        return None
    k = norm.find(exn)
    if k >= 0:
        return raw[pos[k]:pos[k + len(exn) - 1] + 1]
    n = min(8, max(4, len(exn) // 4))
    a = norm.find(exn[:n])
    if a < 0:
        return None
    b = norm.find(exn[-n:], a + n)
    if b < 0 or abs((b + n - a) - len(exn)) > max(12, len(exn) // 5):
        return None
    return raw[pos[a]:pos[b + n - 1] + 1]


def _meta(m: CleanMsg) -> dict[str, Any]:
    return {"msg": m.ref, "message_id": str(m.id), "sender": m.sender, "group_key": m.group_key,
            "group_name": m.group_name, "platform": m.platform, "sent_at": m.sent_at}


def verify_v2_fields(it: Item, by_ref: dict[str, CleanMsg], pool: set[str], kinds: list[str]) -> dict[str, int]:
    st = {"prompts": 0, "prompts_dropped": 0, "quotes": 0, "data": 0, "media": 0, "tools": 0, "refs_dropped": 0}

    def msg_of(ref: str) -> CleanMsg | None:
        m = by_ref.get(ref)
        if m is None or ref not in pool:
            st["refs_dropped"] += 1
            return None
        return m

    prompts = []
    for p in it.prompts:
        m = msg_of(p.get("msg", ""))
        if m is None:
            continue
        text = slice_original(m.raw_text or m.text, p.get("excerpt", ""))
        if not text or len(strip_ws(text)) < PROMPT_MIN:
            st["prompts_dropped"] += 1
            continue
        masked, n = desensitize(text, kinds) if kinds else (text, 0)
        if any(x["text"] == masked for x in prompts):
            continue
        prompts.append({**_meta(m), "text": masked, "verbatim": n == 0, "purpose": (p.get("purpose") or "")[:30]})
    it.prompts, st["prompts"] = prompts, len(prompts)
    quotes = []
    for q in it.quotes:
        m = msg_of(q.get("msg", ""))
        if m is None:
            continue
        quote = (q.get("quote") or "").strip()
        if not quote and len(m.text) <= 80:
            quote = m.text
        if quote and quote_in(quote, m.text) and not any(x["quote"] == quote for x in quotes):
            quotes.append({**_meta(m), "quote": quote[:120]})
    it.quotes, st["quotes"] = quotes, len(quotes)
    data = []
    for d in it.data_points:
        m = msg_of(d.get("msg", ""))
        if m is None:
            continue
        nums = numbers_in(str(d.get("value", ""))) or re.findall(r"\d+(?:\.\d+)?", str(d.get("value", "")))
        if nums and all(number_supported(n, m.source_text) for n in nums):
            data.append({**_meta(m), "label": str(d.get("label") or "")[:20], "value": str(d["value"]),
                         "unit": str(d.get("unit") or "")[:8], "self_reported": bool(d.get("self_reported", True))})
    it.data_points, st["data"] = data, len(data)
    tools = []
    for t in it.tool_notes:
        m = msg_of(t.get("msg", ""))
        if m is None:
            continue
        verdict = str(t.get("verdict") or "").strip()
        bad = [n for n in numbers_in(verdict) if not number_supported(n, m.source_text)]
        tools.append({**_meta(m), "tool": str(t["tool"])[:30], "scene": str(t.get("scene") or "")[:30],
                      "verdict": verdict + ("（待核实）" if bad else "")})
    it.tool_notes, st["tools"] = tools, len(tools)
    media = []
    groups = {by_ref[r].group_key for r in pool if r in by_ref}
    for r in it.media_refs:
        m = by_ref.get(r.get("msg", ""))   # 媒体消息常常只挨着话题、不在回复链里：要求是同群的真实媒体消息
        if m is None or m.media is None or m.group_key not in groups:
            st["refs_dropped"] += 1
            continue
        media.append({**_meta(m), "why": str(r.get("why") or "")[:30], "kind": m.media["kind"],
                      "name": m.media.get("name") or "", "attachment": m.media.get("attachment") or {}})
    it.media_refs, st["media"] = media, len(media)
    return st


def verify_item(it: Item, by_ref: dict[str, CleanMsg], min_chars: int = 4,
                kinds: list[str] | None = None) -> dict[str, int]:
    stats = {"checked": 0, "valid": 0, "relinked": 0, "links_removed": 0}
    platform_of = {m.group_key: m.platform for m in by_ref.values()}
    pool = [by_ref[r] for r in sorted(it.refs, key=lambda r: int(r[1:]) if r[1:].isdigit() else 0) if r in by_ref]
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for ev in it.evidence:
        stats["checked"] += 1
        quote = (ev.get("quote") or "").strip()
        if len(strip_ws(quote)) < min_chars:
            continue
        m = by_ref.get(ev.get("msg", ""))
        if m is None or not quote_in(quote, m.source_text):
            alt = next((x for x in pool if quote_in(quote, x.source_text)), None)
            if alt is None:
                continue
            m = alt
            stats["relinked"] += 1
        if m.ref in seen and any(e["quote"] == quote[:80] for e in out):
            continue
        seen.add(m.ref)
        out.append(evidence_dto(m, quote, platform_of))
        stats["valid"] += 1
    it.evidence = out
    source = "\n".join(x.source_text for x in pool) or "\n".join(by_ref[e["ref"]].source_text for e in out)
    src_msgs = pool or [by_ref[e["ref"]] for e in out]
    links = []
    for link in it.links:
        url = link["url"]
        origin = next((x for x in src_msgs if norm_url(url) in {norm_url(u) for u in x.urls} or url in x.source_text
                       or url in (x.raw_text or "")), None)
        if origin is None:
            stats["links_removed"] += 1
            continue
        kind = link.get("kind") or classify(url)
        meta = dict(link.get("meta") or {})
        if kind == "netdisk" and netdisk_provider(url):
            meta.setdefault("provider", netdisk_provider(url))
        links.append({**link, "kind": kind, "title": link.get("title") or default_title(url, kind), "meta": meta,
                      "code": share_code(origin.raw_text or origin.text, url), "shared_by": origin.sender,
                      "group_name": origin.group_name, "platform": origin.platform, "sent_at": origin.sent_at,
                      "msg": origin.ref})
    it.links = links
    unverified = []
    texts = [it.title, it.hook, it.summary, *it.steps, *it.sop_steps]
    for p in it.points:
        texts += [p.get("title", ""), p.get("hook", ""), p.get("summary", "")]
    for field in texts:
        for num in numbers_in(field):
            if not number_supported(num, source) and num not in unverified:
                unverified.append(num)
    it.unverified = unverified
    if unverified and "未核实" not in it.risk_flags:
        it.risk_flags.append("未核实")
    if kinds is not None:
        stats.update(verify_v2_fields(it, by_ref, {x.ref for x in pool}, kinds))
    return stats


async def run(rc: RunContext) -> StageResult:
    min_chars = int(rc.cfg("pipeline.min_quote_chars", 4))
    kinds = list(rc.cfg("privacy.desensitize", []) or []) if rc.cfg("pipeline.clean.desensitize", True) else []
    keys = ("checked", "valid", "relinked", "links_removed", "prompts", "prompts_dropped", "quotes", "data", "media",
            "tools", "refs_dropped")
    totals = dict.fromkeys(keys, 0)
    kept: list[Item] = []
    dropped = 0
    for it in rc.items:
        s = verify_item(it, rc.by_ref, min_chars, kinds)
        for k in totals:
            totals[k] += s.get(k, 0)
        if it.evidence:
            kept.append(it)
        else:
            dropped += 1
    rc.items = kept
    select_v2(rc.items, rc.top_n, max_features_of(rc), policy_of(rc))
    report_id = rc.report.get("id", rc.run_id)
    for it in rc.items:                                   # 最终 id 与序号一致，由代码决定
        it.id = f"{report_id}-{it.rank:02d}"
    flagged = sum(1 for it in kept if it.unverified)
    rc.totals["items"] = len(kept)
    rc.log.info("AUDITOR", f"核验证据 {totals['valid']}/{totals['checked']} 条有效；剔除无证据条目 {dropped} 条，"
                           f"移除来源中找不到的链接 {totals['links_removed']} 个，{flagged} 条含待核实数字", "verify")
    rc.log.info("AUDITOR", f"提示词原文 {totals['prompts']} 段（从数据库原文截取；对不上原文丢弃 {totals['prompts_dropped']} 段），"
                           f"原话 {totals['quotes']} 句、数据点 {totals['data']} 个、媒体引用 {totals['media']} 个；"
                           f"引用了话题外消息被丢弃 {totals['refs_dropped']} 处", "verify")
    return StageResult(metrics={"evidence_checked": totals["checked"], "evidence_valid": totals["valid"],
                                "relinked": totals["relinked"], "items_dropped": dropped, "items": len(kept),
                                "links_removed": totals["links_removed"], "numbers_flagged": flagged,
                                "prompts": totals["prompts"], "prompts_dropped": totals["prompts_dropped"],
                                "data_points": totals["data"], "media_refs": totals["media"],
                                "refs_dropped": totals["refs_dropped"],
                                "headlines": sum(1 for i in kept if i.is_headline),
                                "features": sum(1 for i in kept if i.is_feature)},
                       message=f"证据 {totals['valid']}/{totals['checked']}")
