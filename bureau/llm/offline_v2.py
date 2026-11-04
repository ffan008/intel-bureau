"""offline 提取 v2：在 v1 规则提取（offline.extract_messages）的基础上补出 §4 的扩展字段。

全部从原文摘取，不改写、不编造：
- prompts：MJ 参数串、「提示词：」后面的内容、多段【】结构模板，按原文截取；
- data_points：带单位的数字 + 收益 / 阅读 / 实测等线索词，标「群友自述」；
- quotes / tool_notes：带判断词、实测词的原句；
- media_refs：同一线程里紧挨着发的图片和文件、回复到话题里的图片和文件；
- privacy：话题起点主要是某人的手机号 / 证件号 + 曝光类线索词。
风险标签用 v2 词表重新计算；可信分不再因风险标签扣分（label 策略下不降权，flag 策略在评分阶段扣）。
"""

from __future__ import annotations

import re
from typing import Any

from bureau.core.constants import RISK_FLAGS, RISK_ILLEGAL
from bureau.core.taxonomy import Taxonomy
from bureau.core.textutil import info_chars
from bureau.llm.offline import extract_messages

_MJ = re.compile(r"--(?:ar|v|stylize|s|cref|cw|sref|niji|q|chaos|seed|style|no|iw|tile)\b")
_MARK = re.compile(r"(?:提示词|咒语|prompt|Prompt|PROMPT)(?:如下|模板|原文|是)?\s*[：:]\s*")
_SEG = re.compile(r"【[^】]{1,12}】")
_KV_LINE = re.compile(r"^[^\n：:]{1,10}[：:]", re.M)
_NUM_UNIT = re.compile(r"(?<![\d.A-Za-z])(\d+(?:\.\d+)?)\s*(万|千|w|W|k|K|M)?\s*"
                       r"(元|块钱|块|粉丝|粉|阅读|播放|曝光|篇|集|条|单|张|页|分钟|小时|秒|天|周|积分|token|人|%|倍)?")
DATA_CUES = ("收入", "收益", "流量主", "涨粉", "阅读", "播放", "曝光", "实测", "花了", "成本", "耗时", "预算", "报价",
             "一单", "一张", "单价", "千次", "变现", "接单", "赚")
QUOTE_CUES = ("其实", "关键", "本质", "核心", "千万", "一定要", "建议", "不如", "才是", "记住", "最重要", "比较重要",
              "别碰", "别信", "别用", "别贪", "重要", "省事", "应该", "要先", "比我", "靠谱", "够用")
VERDICT_CUES = ("实测", "对比", "更快", "更稳", "稳定", "好用", "不好用", "崩", "一次跑通", "推荐", "首选", "最稳",
                "省", "便宜", "能跑", "跑不动", "不崩", "效果好")
VERIFIED_CUES = ("跑通", "实测", "验证", "照着做", "照着试", "试了", "亲测", "效果")
_CLAUSE = re.compile(r"[^，,。；;！!？?\n]+")
_PII = ("[手机号]", "[身份证]", "[银行卡]")
_RAW_PII = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)|(?<!\d)\d{17}[\dXx](?!\d)")


def cluster_taxonomy(tax: Taxonomy) -> Taxonomy:
    """切话题用的词表：v1 的风险类别 + 违法高危（违法内容不与普通讨论混在一起；平台规则等不再拆开话题）。"""
    keep = [f for f in tax.risk_flags if f in RISK_FLAGS or f == RISK_ILLEGAL]
    return Taxonomy(categories=tax.categories, kinds=tax.kinds, risk_flags=keep,
                    risk_lexicon={k: v for k, v in tax.risk_lexicon.items() if k in keep}, tools=tax.tools, cues=tax.cues)


def find_prompt(raw: str) -> str | None:
    """在一条消息的原文里找提示词，返回原文中的一段（逐字）。"""
    t = (raw or "").strip()
    if len(t) < 20:
        return None
    m = _MARK.search(t)
    if m and len(t) - m.end() >= 20:
        return t[m.end():].strip()
    body = None
    words = [w for w in re.findall(r"(?<![-\w])[A-Za-z][A-Za-z-]{2,}", _MJ.sub(" ", t))]
    if _MJ.search(t) and len(words) >= 4:            # 只有参数（如「--cref 加上 --cw 100」）不算完整提示词
        lead = re.match(r"^[^\n]{0,24}?[：:]\s*(?=[A-Za-z(（\[【])", t)      # 去掉「MJ 里用这个：」这类引导语
        body = t[lead.end():] if lead else t
    elif len(_SEG.findall(t)) >= 2:
        seg = _SEG.search(t)                     # 「分享一个……模板：\n【画面风格】……」只取【】结构本身
        body = t[seg.start():] if seg and seg.start() <= 60 else t
    elif len(_KV_LINE.findall(t)) >= 3:
        body = t
    body = (body or "").strip()
    return body if len(body) >= 20 else None


def _clauses(text: str) -> list[str]:
    return [c.strip() for c in _CLAUSE.findall(text or "") if c.strip()]


def data_points(m: dict[str, Any], limit: int = 4) -> list[dict[str, Any]]:
    text = m.get("text") or ""
    if not any(c in text for c in DATA_CUES):
        return []
    out: list[dict[str, Any]] = []
    for clause in _clauses(text):
        for mm in _NUM_UNIT.finditer(clause):
            if not (mm.group(2) or mm.group(3)):
                continue
            label = clause[:mm.start()].strip(" ：:，,")[-12:] or clause[mm.end():].strip()[:12]
            out.append({"label": label, "value": mm.group(1), "unit": (mm.group(2) or "") + (mm.group(3) or ""),
                        "msg": m["ref"], "self_reported": True})
            if len(out) >= limit:
                return out
    return out


def quotes(m: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for s in re.split(r"(?<=[。！？!?；;])", m.get("text") or ""):
        s = s.strip()
        if 10 <= len(s) <= 60 and any(c in s for c in QUOTE_CUES):
            out.append({"msg": m["ref"], "quote": s})
    return out[:1]


def is_privacy(text: str, alltext: str, tax: Taxonomy) -> bool:
    """话题起点主要是某个人的手机号 / 证件号：有 PII（脱敏占位符或原样），且有曝光类线索词或除此之外几乎没有信息。"""
    has_pii = any(p in text for p in _PII) or bool(_RAW_PII.search(text))
    if not has_pii:
        return False
    rest = _RAW_PII.sub("", text)
    for p in _PII:
        rest = rest.replace(p, "")
    return any(c in alltext for c in tax.privacy_cues) or info_chars(rest) < 12


def _media_refs(cluster: list[dict[str, Any]], media: list[dict[str, Any]], used: set[str],
                title: str) -> list[dict[str, Any]]:
    refs = {m["ref"] for m in cluster}
    threads = {m.get("thread_id") for m in cluster}
    out = []
    for md in media:
        if md["ref"] in used or md.get("thread_id") not in threads:
            continue
        if md.get("reply_ref") in refs:
            why = f"回复「{title[:12]}」"
        elif any(c["sender"] == md["sender"] and abs(c["ts"] - md["ts"]) <= 600 for c in cluster):
            why = f"与「{title[:12]}」同一发言人紧邻发出"
        else:
            continue
        used.add(md["ref"])
        out.append({"msg": md["ref"], "why": why})
    return out[:4]


def extract_messages_v2(msgs: list[dict[str, Any]], tax: Taxonomy, *, max_items: int = 6) -> dict[str, Any]:
    by_ref = {m["ref"]: m for m in msgs}
    text_msgs = [m for m in msgs if not m.get("media")]
    media = [m for m in msgs if m.get("media")]
    ctax = cluster_taxonomy(tax)
    base = extract_messages(text_msgs, ctax, max_items=max_items)
    used_media: set[str] = set()
    items = []
    for it in base["items"]:
        cluster = [by_ref[r] for r in it.get("refs") or [] if r in by_ref]
        alltext = "\n".join(m["text"] for m in cluster)
        anchor = by_ref.get((it.get("evidence") or [{}])[0].get("msg", ""), cluster[0] if cluster else {})
        v1_risks = ctax.risks_in(alltext)
        risks = tax.risks_in(f"{it['title']}\n{alltext}")
        cred = it["scores"]["credibility"] + 1.2 * sum(1 for r in v1_risks if r in ("广告引流", "金钱风险")) + \
            0.8 * ("未核实" in v1_risks)
        it["scores"]["credibility"] = round(min(5.0, cred), 2)
        illegal = RISK_ILLEGAL in risks
        it["risk_flags"] = risks
        it["privacy"] = is_privacy(anchor.get("text") or "", alltext, tax)
        it["prompts"], it["data_points"], it["quotes"], it["tool_notes"] = [], [], [], []
        if not illegal:
            for m in cluster:
                p = find_prompt(m.get("raw_text") or m["text"])
                if p and not any(x["excerpt"] == p for x in it["prompts"]):
                    it["prompts"].append({"msg": m["ref"], "excerpt": p, "purpose": ""})
                it["data_points"] += data_points(m)
                it["quotes"] += quotes(m)
                it["tool_notes"] += tool_notes(m, tax, it["title"])
        it["data_points"], it["quotes"], it["tool_notes"] = it["data_points"][:6], it["quotes"][:2], it["tool_notes"][:3]
        verified = any(c in alltext for c in VERIFIED_CUES)
        it["sop_steps"] = list(it["steps"]) if (len(it["steps"]) >= 3 and verified and not illegal) else []
        if illegal:
            it["steps"] = []
        it["media_refs"] = [] if illegal else _media_refs(cluster, media, used_media, it["title"])
        it["links"] = [{**x, "kind": ""} for x in it.get("links") or []]
        it["topic"] = ""
        items.append(it)
    return {"items": items, "noise_ratio": base["noise_ratio"]}


def tool_notes(m: dict[str, Any], tax: Taxonomy, scene: str) -> list[dict[str, Any]]:
    out = []
    for clause in _clauses(m.get("text") or ""):
        if not any(c in clause for c in VERDICT_CUES):
            continue
        tools = tax.tools_in(clause) or tax.tools_in(m.get("text") or "")
        if tools and len(clause) >= 6:
            out.append({"tool": tools[0], "scene": scene[:20], "verdict": clause[:60], "msg": m["ref"]})
    return out[:2]
