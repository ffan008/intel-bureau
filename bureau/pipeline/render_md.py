"""完整版 Markdown（§9）与推送精简版（summary_md ≤ 1800 字、summary_text 纯文本）。"""

from __future__ import annotations

import re
from typing import Any

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.constants import SERIOUS_RISKS, TREND_LABELS
from bureau.core.textutil import fmt_int, truncate
from bureau.pipeline.models import Item
from bureau.pipeline.report_model import source_line, suggest_action

SUMMARY_LIMIT = 1800


def _md(text: str) -> str:
    """转义会破坏版式的字符（不允许原文注入 Markdown 结构）。"""
    t = (text or "").replace("\r", "").replace("\n", " ")
    t = re.sub(r"([\\`*_\[\]|<>])", r"\\\1", t)
    return t.strip()


def _quote(text: str) -> str:
    return _md(text).replace("\\>", "＞")


def _flags(it: Item) -> str:
    out = [f"〔{f}〕" for f in it.risk_flags]
    return " ".join(out)


def _unverified(it: Item) -> str:
    return f"（待核实：{'、'.join(it.unverified)}）" if it.unverified else ""


def _headline(n: int, it: Item) -> list[str]:
    return [
        f"### {n}. {_md(it.title)}{' ' + _flags(it) if it.risk_flags else ''}",
        f"- 一句话价值：{_md(it.hook)}{_unverified(it)}",
        f"- 评分 {it.score:g}｜{it.category}｜{it.kind}｜{TREND_LABELS.get(it.trend, it.trend)}",
        f"- 来源：{_md(source_line(it))}",
        f"- 建议动作：{suggest_action(it)}",
        "",
    ]


def _feature(n: int, it: Item) -> list[str]:
    f = it.feature or {}
    lines = [f"### {n}. {_md(it.title)}", "", f"**背景**：{_md(f.get('background') or it.summary)}", "", "**关键做法**", ""]
    practice = f.get("practice") or []
    if practice:
        lines += [f"{i}. {_md(p)}" for i, p in enumerate(practice, start=1)]
    else:
        lines.append("原文没有给出明确步骤。")
    lines += ["", "**证据（原文摘录）**", ""]
    for e in it.evidence:
        when = e["sent_at"][5:16].replace("T", " ")
        lines.append(f"> 「{_quote(e['quote'])}」—— {_md(e['sender'])} · {_md(e['group_name'])} · {when}")
        lines.append(">")
    if lines[-1] == ">":
        lines.pop()
    lines += ["", "**资源链接**", ""]
    lines += [f"- [{_md(x.get('title') or x['url'])}]({x['url']})" for x in it.links] or ["- 无"]
    lines += ["", f"**适用范围与风险**：{_md(f.get('scope') or '')}{_unverified(it)}", ""]
    return lines


def render_full_md(ctx: dict[str, Any]) -> str:
    st = ctx["stats"]
    L: list[str] = [f"# {ctx['title']}", "", f"> {ctx['header']}", ""]
    if ctx["demo"]:
        L += ["> 本报告由演示数据生成，群名、人物和对话均为虚构。", ""]
    L += ["## 一、今日风向", ""]
    if ctx["judgments"]:
        for i, j in enumerate(ctx["judgments"], start=1):
            L += [f"{i}. **{_md(j['text'])}**", f"   依据：{_md(j.get('basis', ''))}"]
    else:
        L.append("今日没有足够的信息形成判断。")
    heads = ctx["heads"]
    L += ["", f"## 二、头条情报 TOP {len(heads)}", ""]
    for i, it in enumerate(heads, start=1):
        L += _headline(i, it)
    if not heads:
        L += ["今日没有达到头条标准的情报。", ""]
    L += ["## 三、专题深读", ""]
    for i, it in enumerate(ctx["feats"], start=1):
        L += _feature(i, it)
    if not ctx["feats"]:
        L += ["今日没有适合深读的专题。", ""]
    L += ["## 四、上升信号", ""]
    rising = st.get("rising") or []
    if rising:
        L += ["| 关键词 | 今日次数 | 7 日均值 | z 值 | 主要来源群 |", "|---|---:|---:|---:|---|"]
        L += [f"| {_md(r['word'])} | {r['today']} | {r['avg7']:g} | {r['z']:g} | {_md('、'.join(r['groups']))} |" for r in rising]
    else:
        L.append(f"没有满足条件（z ≥ {ctx['rising_z']:g} 且当日至少 {ctx['rising_min']} 次）的上升信号。")
    L += ["", "## 五、资源清单", ""]
    if ctx["resources"]:
        for cat, links in ctx["resources"].items():
            L += [f"**{cat}**", ""] + [f"- [{_md(x['title'])}]({x['url']})" for x in links] + [""]
    else:
        L += ["今日没有分享链接。", ""]
    L += ["## 六、风险与待核实", ""]
    for i, it in enumerate(ctx["risks"], start=1):
        flags = "、".join(it.risk_flags) or "待核实"
        L += [f"{i}. **{_md(it.title)}**（{flags}）", f"   {_md(it.hook)}{_unverified(it)}",
              f"   来源：{_md(source_line(it))}；处理：{'已降权，不建议照做' if set(it.risk_flags) & SERIOUS_RISKS else '使用前请核实'}"]
    if not ctx["risks"]:
        L.append("今日没有需要特别提示的风险。")
    L += ["", "## 七、持续追踪", ""]
    for i, it in enumerate(ctx["tracking"], start=1):
        L.append(f"{i}. **{_md(it.title)}**（{TREND_LABELS[it.trend]}；关联往期话题「{_md(it.memory_title or '')}」，"
                 f"首次出现 {it.memory_first_seen or '—'}）")
    if not ctx["tracking"]:
        L.append("今日的话题都是首次出现。")
    L += ["", "## 附录：数据面板与方法说明", ""]
    if ctx["others"]:
        L += [f"### 其余情报（{len(ctx['others'])} 条）", ""]
        L += [f"{i}. {_md(it.title)}｜{it.category}｜评分 {it.score:g}｜{_md(source_line(it))}"
              for i, it in enumerate(ctx["others"], start=1)] + [""]
    L += ["### 平台与群", "", "| 平台 | 群 | 消息 | 发言人 | 热度 |", "|---|---|---:|---:|---:|"]
    L += [f"| {PLATFORM_LABELS[Platform(g['platform'])]} | {_md(g['name'])} | {fmt_int(g['messages'])} | {g['speakers']} | {g['heat']:g} |"
          for g in st.get("top_groups", [])]
    hourly = sorted(((sum(v for k, v in h.items() if k != "hour"), h["hour"]) for h in st.get("hourly", [])), reverse=True)
    peaks = "、".join(f"{h:02d}:00（{n} 条）" for n, h in hourly[:3] if n)
    L += ["", f"### 活跃时段", "", f"最活跃的时段：{peaks or '—'}。", "", "### 发言榜", ""]
    L += [f"{i}. {_md(s['name'])}（{_md(s['group_name'])}）{s['messages']} 条" for i, s in enumerate(st.get("top_speakers", [])[:10], 1)]
    w = ctx["weights"]
    L += ["", "### 方法说明", "",
          f"- 统计数字、计数和序号由程序计算；文字{'由程序从原文摘录' if ctx['provider'] == 'offline' else '由模型（' + ctx['provider'] + '）撰写、程序校验'}。",
          "- 评分 = 新颖 × {novelty:g} + 可执行 × {actionability:g} + 可信 × {credibility:g} + 热度 × {heat:g} + 相关 × {relevance:g}"
          "（按权重归一化到 0~100）− 风险惩罚 − 重复惩罚。".format(**{k: float(w.get(k, 1)) for k in
                                                     ("novelty", "actionability", "credibility", "heat", "relevance")}),
          f"- 上升信号：关键词当日出现次数与过去 7 日均值比较，z ≥ {ctx['rising_z']:g} 且至少 {ctx['rising_min']} 次。",
          "- 每条情报都附原文摘录；摘录必须与原消息一致，否则剔除。原文里找不到的数字标「待核实」。", ""]
    return "\n".join(L)


def render_summary_md(ctx: dict[str, Any], *, hook_len: int = 40, basis: bool = True) -> str:
    L = [f"**{ctx['title']}**", "", ctx["header"], ""]
    if ctx["judgments"]:
        L.append("**今日风向**")
        for i, j in enumerate(ctx["judgments"][:3], start=1):
            L.append(f"{i}. {_md(j['text'])}" + (f"（{_md(truncate(j.get('basis', ''), 50))}）" if basis else ""))
        L.append("")
    if ctx["heads"]:
        L.append(f"**头条 TOP {len(ctx['heads'])}**")
        for i, it in enumerate(ctx["heads"], start=1):
            src = "、".join(s["group_name"] for s in it.sources[:2])
            L.append(f"{i}. **{_md(it.title)}**：{_md(truncate(it.hook, hook_len))}（{_md(src)}）")
        L.append("")
    risky = [it for it in ctx["items"] if set(it.risk_flags) & SERIOUS_RISKS]
    L.append(f"风险提示：{len(risky)} 条灰色或高风险内容已降权，详见完整报告「风险与待核实」。" if risky
             else "风险提示：今日未发现明显的灰色或高风险内容。")
    L += ["", f"完整报告：{ctx['dashboard_url']}"]
    return "\n".join(L)


def summary_within_limit(ctx: dict[str, Any]) -> str:
    for kw in ({}, {"basis": False}, {"basis": False, "hook_len": 24}, {"basis": False, "hook_len": 0}):
        s = render_summary_md(ctx, **kw)
        if len(s) <= SUMMARY_LIMIT:
            return s
    return truncate(s, SUMMARY_LIMIT)


def to_plain(md: str) -> str:
    t = re.sub(r"\*\*(.+?)\*\*", r"\1", md)
    t = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r"\1 \2", t)
    t = re.sub(r"\\([\\`*_\[\]|<>])", r"\1", t)
    return re.sub(r"^#+\s*", "", t, flags=re.M)
