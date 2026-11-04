"""自包含的深色主题 HTML 报告（不含脚本、不引用外部资源；所有文本都转义，链接只允许 http/https）。"""

from __future__ import annotations

from html import escape
from typing import Any

from bureau.contracts import PLATFORM_LABELS, Platform
from bureau.core.constants import SERIOUS_RISKS, TREND_LABELS
from bureau.core.textutil import fmt_int
from bureau.pipeline.models import Item
from bureau.pipeline.render_css import CSS
from bureau.pipeline.report_model import source_line, suggest_action


def e(x: Any) -> str:
    return escape(str(x if x is not None else ""), quote=True)


def link(url: str, text: str | None = None) -> str:
    if not url.startswith(("http://", "https://")):
        return e(text or url)
    return f'<a href="{e(url)}" target="_blank" rel="noopener noreferrer">{e(text or url)}</a>'


def _badges(it: Item) -> str:
    out = [f'<span class="badge t-{it.trend}">{TREND_LABELS.get(it.trend, it.trend)}</span>',
           f'<span class="badge">{e(it.category)}</span>', f'<span class="badge">{e(it.kind)}</span>']
    out += [f'<span class="badge risk">{e(f)}</span>' for f in it.risk_flags]
    return "".join(out)


def _bars(it: Item) -> str:
    names = {"novelty": "新颖", "actionability": "可执行", "credibility": "可信", "heat": "热度", "relevance": "相关"}
    return "".join(f'<span>{n}<span class="bar"><i style="width:{min(100, 20 * it.scores.get(k, 0)):.0f}%"></i></span></span>'
                   for k, n in names.items())


def _risk_card(i: int, it: Item) -> str:
    flags = "".join(f'<span class="badge risk">{e(x)}</span>' for x in it.risk_flags)
    unv = e("（待核实：" + "、".join(it.unverified) + "）") if it.unverified else ""
    action = "已降权，不建议照做" if set(it.risk_flags) & SERIOUS_RISKS else "使用前请核实"
    return (f'<div class="card" style="border-left-color:var(--red)"><h3>{i}. {e(it.title)}</h3>'
            f'<div class="row">{flags}</div><p class="hook">{e(it.hook)}{unv}</p>'
            f'<div class="row">来源：{e(source_line(it))}；处理：{action}</div></div>')


def _section(no: str, title: str, body: str) -> str:
    return f'<section><h2><span>{no}</span>{e(title)}</h2>{body}</section>'


def render_html(ctx: dict[str, Any]) -> str:
    st = ctx["stats"]
    kpis = [("有效消息", fmt_int(st.get("messages_clean", 0))), ("原始消息", fmt_int(st.get("messages_raw", 0))),
            ("信噪比", f"{100 * st.get('snr', 0):.1f}%"), ("情报", str(len(ctx["items"]))),
            ("上升信号", str(len(st.get("rising") or [])))]
    hero = (f'<div class="hero"><div class="brand">INTEL BUREAU · DAILY BRIEF</div><h1>{e(ctx["title"])}</h1>'
            f'<p class="meta">{e(ctx["header"])}</p>'
            + ('<p class="demo-note">本报告由演示数据生成，群名、人物和对话均为虚构。</p>' if ctx["demo"] else "")
            + '<div class="kpis">' + "".join(f'<div class="kpi"><span>{k}</span><b>{e(v)}</b></div>' for k, v in kpis)
            + "</div></div>")
    parts = [hero]
    js = "".join(f"<li><b>{e(j['text'])}</b><small>依据：{e(j.get('basis', ''))}</small></li>" for j in ctx["judgments"])
    parts.append(_section("01", "今日风向", f'<ol class="j">{js}</ol>' if js else '<p class="muted">今日没有足够的信息形成判断。</p>'))
    cards = []
    for i, it in enumerate(ctx["heads"], start=1):
        unv = f'<span class="badge risk">待核实：{e("、".join(it.unverified))}</span>' if it.unverified else ""
        cards.append(f'<div class="card"><div class="top"><span class="rank">{i:02d}</span><h3>{e(it.title)}</h3>'
                     f'<span class="num">评分 {it.score:g}</span></div><p class="hook">{e(it.hook)} {unv}</p>'
                     f'<div class="row">{_badges(it)}</div><div class="row" style="margin-top:6px">{_bars(it)}</div>'
                     f'<div class="row" style="margin-top:6px">来源：{e(source_line(it))}</div>'
                     f'<div class="action">建议动作：{e(suggest_action(it))}</div></div>')
    parts.append(_section("02", f"头条情报 TOP {len(ctx['heads'])}", "".join(cards) or '<p class="muted">今日没有达到头条标准的情报。</p>'))
    arts = []
    for i, it in enumerate(ctx["feats"], start=1):
        f = it.feature or {}
        steps = "".join(f"<li>{e(p)}</li>" for p in f.get("practice") or [])
        evs = "".join(f'<blockquote>「{e(x["quote"])}」<cite>{e(x["sender"])} · {e(x["group_name"])} · '
                      f'{e(x["sent_at"][5:16].replace("T", " "))}</cite></blockquote>' for x in it.evidence)
        links = "".join(f"<li>{link(x['url'], x.get('title') or x['url'])}</li>" for x in it.links) or "<li>无</li>"
        arts.append(f'<article><h3>{i}. {e(it.title)}</h3><div class="row">{_badges(it)}</div>'
                    f'<h4>背景</h4><p>{e(f.get("background") or it.summary)}</p>'
                    f'<h4>关键做法</h4>{"<ol>" + steps + "</ol>" if steps else "<p class=muted>原文没有给出明确步骤。</p>"}'
                    f'<h4>证据（原文摘录）</h4>{evs}<h4>资源链接</h4><ul class="plain">{links}</ul>'
                    f'<h4>适用范围与风险</h4><p>{e(f.get("scope") or "")}</p></article>')
    parts.append(_section("03", "专题深读", "".join(arts) or '<p class="muted">今日没有适合深读的专题。</p>'))
    rising = st.get("rising") or []
    if rising:
        rows = []
        for r in rising:
            mx = max(r["spark"] or [1]) or 1
            spark = "".join(f'<i style="height:{max(2, 22 * v / mx):.0f}px"></i>' for v in r["spark"])
            rows.append(f"<tr><td>{e(r['word'])}</td><td class=n>{r['today']}</td><td class=n>{r['avg7']:g}</td>"
                        f"<td class=n>{r['z']:g}</td><td><span class=spark>{spark}</span></td><td>{e('、'.join(r['groups']))}</td></tr>")
        body = ("<table><tr><th>关键词</th><th class=n>今日次数</th><th class=n>7 日均值</th><th class=n>z 值</th>"
                "<th>7 日走势</th><th>主要来源群</th></tr>" + "".join(rows) + "</table>")
    else:
        body = f'<p class="muted">没有满足条件（z ≥ {ctx["rising_z"]:g} 且当日至少 {ctx["rising_min"]} 次）的上升信号。</p>'
    parts.append(_section("04", "上升信号", body))
    res = "".join(f"<h4 class=muted>{e(cat)}</h4><ul class=plain>" + "".join(f"<li>{link(x['url'], x['title'])}</li>" for x in links)
                  + "</ul>" for cat, links in ctx["resources"].items())
    parts.append(_section("05", "资源清单", res or '<p class="muted">今日没有分享链接。</p>'))
    risks = "".join(_risk_card(i, it) for i, it in enumerate(ctx["risks"], start=1))
    parts.append(_section("06", "风险与待核实", risks or '<p class="muted">今日没有需要特别提示的风险。</p>'))
    track = "".join(f"<li>{e(it.title)} <span class='badge t-{it.trend}'>{TREND_LABELS[it.trend]}</span> "
                    f"<span class=muted>关联往期「{e(it.memory_title)}」，首次出现 {e(it.memory_first_seen or '—')}</span></li>"
                    for it in ctx["tracking"])
    parts.append(_section("07", "持续追踪", f"<ol>{track}</ol>" if track else '<p class="muted">今日的话题都是首次出现。</p>'))
    parts.append(_section("附", "数据面板与方法说明", _appendix(ctx)))
    parts.append(f"<footer>情报局工作台 · 报告编号 {e(ctx['report_id'])} · 本文件可离线打开</footer>")
    return (f'<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" '
            f'content="width=device-width,initial-scale=1"><title>{e(ctx["title"])}</title><style>{CSS}</style></head>'
            f'<body><div class="wrap">{"".join(parts)}</div></body></html>')


def _appendix(ctx: dict[str, Any]) -> str:
    st = ctx["stats"]
    out = []
    if ctx["others"]:
        out.append(f"<h4>其余情报（{len(ctx['others'])} 条）</h4><ol>" + "".join(
            f"<li>{e(it.title)} <span class=muted>{e(it.category)} · 评分 {it.score:g} · {e(source_line(it))}</span></li>"
            for it in ctx["others"]) + "</ol>")
    rows = "".join(f"<tr><td class='pf-{g['platform']}'>{PLATFORM_LABELS[Platform(g['platform'])]}</td><td>{e(g['name'])}</td>"
                   f"<td class=n>{fmt_int(g['messages'])}</td><td class=n>{g['speakers']}</td><td class=n>{g['heat']:g}</td></tr>"
                   for g in st.get("top_groups", []))
    out.append("<h4>平台与群</h4><table><tr><th>平台</th><th>群</th><th class=n>消息</th><th class=n>发言人</th>"
               f"<th class=n>热度</th></tr>{rows}</table>")
    hours = [sum(v for k, v in h.items() if k != "hour") for h in st.get("hourly", [])]
    mx = max(hours or [1]) or 1
    out.append("<h4>24 小时活跃度</h4><div class=hours>" + "".join(
        f'<i title="{h:02d}:00 · {n} 条" style="height:{max(1, 90 * n / mx):.0f}px"></i>' for h, n in enumerate(hours))
        + "</div><div class=hlabels><span>00</span><span>06</span><span>12</span><span>18</span><span>23</span></div>")
    grid = {(d, h): n for d, h, n in st.get("heat_7x24", [])}
    gmx = max(grid.values() or [1]) or 1
    cells = []
    for d in range(7):
        cells.append(f"<span>{'今日' if d == 6 else f'前{6 - d}天'}</span>")
        for h in range(24):
            v = grid.get((d, h), 0) / gmx
            cells.append(f'<i title="{grid.get((d, h), 0)} 条" style="background:rgba(34,228,255,{0.06 + 0.9 * v:.2f})"></i>')
    out.append("<h4>7 × 24 活跃热力</h4><div class=heat>" + "".join(cells) + "</div>")
    spk = "".join(f"<li>{e(s['name'])} <span class=muted>{e(s['group_name'])} · {s['messages']} 条</span></li>"
                  for s in st.get("top_speakers", [])[:10])
    out.append(f"<h4>发言榜</h4><ol>{spk}</ol>")
    engine = "程序从原文摘录" if ctx["provider"] == "offline" else f"模型（{ctx['provider']}）撰写、程序校验"
    out.append("<h4>方法说明</h4><ul class=plain>"
               f"<li>统计数字、计数和序号由程序计算；文字{e(engine)}。</li>"
               "<li>评分由新颖、可执行、可信、热度、相关五个维度加权得出（0~100），风险与重复内容扣分。</li>"
               f"<li>上升信号：关键词当日次数与过去 7 日均值比较，z ≥ {ctx['rising_z']:g} 且至少 {ctx['rising_min']} 次。</li>"
               "<li>每条情报都附原文摘录；摘录必须与原消息一致，否则剔除。原文里找不到的数字标「待核实」。</li></ul>")
    return "".join(out)
