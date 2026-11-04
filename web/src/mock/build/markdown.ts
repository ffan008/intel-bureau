/** 报告正文（ARCHITECTURE §9 结构）。计数与序号全部由代码生成。 */
import type { IntelItemDTO, ReportDTO, StatsDTO } from '@/api/types'
import { fmtN, mdhm } from '../util'

const PL: Record<string, string> = { wechat: '微信', qq: 'QQ', feishu: '飞书', demo: '演示' }
const src = (it: IntelItemDTO) => it.sources.map((s) => `${PL[s.platform]}·${s.group_name}`).join('、')
const evTime = (iso: string) => mdhm(new Date(iso).getTime())
const pct = (v: number) => (v * 100).toFixed(1) + '%'

export function windowLine(stats: StatsDTO, items: IntelItemDTO[], winLabel: string): string {
  const plat = stats.by_platform.filter((p) => p.groups > 0).map((p) => `${PL[p.platform]} ${p.groups} 群`).join(' · ')
  const n = (t: string) => items.filter((i) => i.trend === t).length
  return `窗口 ${winLabel}｜${plat}｜有效消息 ${fmtN(stats.messages_clean)} / ${fmtN(stats.messages_raw)}（信噪比 ${pct(stats.snr)}）｜情报 ${items.length} 条（新 ${n('new')} · 持续 ${n('developing')} · 重复 ${n('repeat')}）`
}

export function buildFullMd(title: string, winLabel: string, stats: StatsDTO, items: IntelItemDTO[], judgments: ReportDTO['judgments']): string {
  const L: string[] = []
  const heads = items.filter((i) => i.is_headline)
  const feats = items.filter((i) => i.is_feature)
  const risky = items.filter((i) => i.risk_flags.length)
  L.push(`# ${title}`, '', `> ${windowLine(stats, items, winLabel)}`, '')
  L.push('## 一、今日风向', '')
  judgments.forEach((j, i) => L.push(`${i + 1}. **${j.text}**`, `   依据：${j.basis}`))
  L.push('', `## 二、头条情报 TOP ${heads.length}`, '', '| # | 标题 | 一句话价值 | 评分 | 分类 | 来源 |', '|---|---|---|---|---|---|')
  heads.forEach((h, i) => L.push(`| ${i + 1} | ${h.title} | ${h.hook} | ${h.score.toFixed(1)} | ${h.category} | ${src(h)} |`))
  L.push('')
  heads.forEach((h, i) => {
    const e = h.evidence[0]
    L.push(`${i + 1}. **${h.title}** — 建议动作：${h.steps[0] ?? '持续关注'}${e ? `（${e.group_name}·${e.sender}·${evTime(e.sent_at)}）` : ''}`)
  })
  L.push('', `## 三、专题深读（${feats.length} 篇）`, '')
  feats.forEach((f, i) => {
    L.push(`### ${i + 1}. ${f.title}`, '', `\`${f.category}\` \`${f.kind}\` \`评分 ${f.score.toFixed(1)}\`${f.risk_flags.map((r) => ` \`⚠ ${r}\``).join('')}`, '')
    L.push(`**背景**　${f.summary}`, '', '**关键做法**', '')
    f.steps.forEach((s, k) => L.push(`${k + 1}. ${s}`))
    L.push('', '**证据**', '')
    f.evidence.forEach((e) => L.push(`> ${e.quote}`, `> —— ${e.sender} · ${PL[e.platform]}「${e.group_name}」· ${evTime(e.sent_at)}`, ''))
    if (f.links.length) {
      L.push('**资源链接**', '')
      f.links.forEach((l) => L.push(`- [${l.title ?? l.url}](${l.url})`))
      L.push('')
    }
    L.push(`**适用范围与风险**　${f.risk_flags.length ? `已标注：${f.risk_flags.join('、')}。` : ''}来源 ${src(f)}，参与 ${f.participants.length} 人。`, '')
  })
  L.push('## 四、上升信号', '', '| 关键词 | 今日次数 | 7 日均值 | z 值 | 主要来源群 |', '|---|---|---|---|---|')
  stats.rising.forEach((r) => L.push(`| ${r.word} | ${r.today} | ${r.avg7.toFixed(1)} | ${r.z.toFixed(1)} | ${r.groups.join('、')} |`))
  const links = new Map<string, { title: string; cat: string }>()
  items.forEach((it) => it.links.forEach((l) => { if (/^https?:/.test(l.url) && !links.has(l.url)) links.set(l.url, { title: l.title ?? l.url, cat: it.category }) }))
  L.push('', `## 五、资源清单（${links.size} 个链接）`, '')
  const byCat = new Map<string, string[]>()
  links.forEach((v, url) => byCat.set(v.cat, [...(byCat.get(v.cat) ?? []), `- [${v.title}](${url})`]))
  ;[...byCat.keys()].sort().forEach((c) => L.push(`**${c}**`, '', ...byCat.get(c)!, ''))
  L.push(`## 六、风险与待核实（${risky.length} 条）`, '')
  risky.forEach((r, i) => L.push(`${i + 1}. ${r.title} —— ${r.risk_flags.join('、')}。${r.hook}`))
  const dev = items.filter((i) => i.trend === 'developing')
  L.push('', '## 七、持续追踪', '')
  dev.forEach((d) => L.push(`- ${d.title}（持续发酵，来源 ${src(d)}）`))
  L.push('', '## 附录：数据面板', '', '| 平台 | 群数 | 消息数 |', '|---|---|---|')
  stats.by_platform.forEach((p) => L.push(`| ${PL[p.platform]} | ${p.groups} | ${fmtN(p.messages)} |`))
  L.push('', '| 群 | 消息 | 发言人 | 热度 |', '|---|---|---|---|')
  stats.top_groups.forEach((g) => L.push(`| ${g.name} | ${fmtN(g.messages)} | ${g.speakers} | ${g.heat} |`))
  const peak = stats.hourly.reduce((a, b) => (b.wechat + b.qq + b.feishu > a.wechat + a.qq + a.feishu ? b : a))
  L.push('', `活跃高峰 ${String(peak.hour).padStart(2, '0')}:00；发言榜：${stats.top_speakers.slice(0, 5).map((s) => `${s.name}（${s.messages}）`).join('、')}。`)
  L.push('', '**方法说明**　计数、序号、统计数字由代码生成；证据摘录均为对应消息原文的子串；原文找不到的数字标「待核实」。')
  return L.join('\n')
}

export function buildSummaryMd(title: string, winLabel: string, stats: StatsDTO, items: IntelItemDTO[], judgments: ReportDTO['judgments']): string {
  const L = [`**${title}**`, '', windowLine(stats, items, winLabel), '', '**今日风向**']
  judgments.slice(0, 3).forEach((j, i) => L.push(`${i + 1}. ${j.text}`))
  L.push('', '**头条 TOP 5**')
  items.filter((i) => i.is_headline).forEach((h, i) => L.push(`${i + 1}. ${h.title}：${h.hook}（${src(h)}）`))
  const risky = items.filter((i) => i.risk_flags.length).length
  if (risky) L.push('', `⚠ 风险提示：${risky} 条情报带风险标签，详见完整报告。`)
  L.push('', '完整报告：http://127.0.0.1:8765/reports')
  return L.join('\n').slice(0, 1800)
}
