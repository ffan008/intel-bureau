/** v2 mock 知识库：今天 12 篇专题对应的条目（部分是合并更新，带历史版本）+ 8 条往期条目。全部虚构 */
import type { KbArticleDTO, ReportDTO } from '@/api/types'
import { RISK_DISCLAIMER } from '@/utils/risk'
import { CATEGORIES, SPEAKERS, WHITELIST } from '../data/groups'
import { DAY, iso, pick, rng } from '../util'
import { SEEDS } from './items'
import { ARTICLE_SPECS, kbIdOf, riskOf } from './v2Articles'

const OLDER = [8, 13, 14, 15, 17, 20, 23, 26]
const DAY_OFFSETS = [0, 2, 5, 9]
const NOTES = ['补充了新的群友实测数据', '合并了另一个群的同类讨论，来源 +2', '补充了参数原文和踩坑记录', '加入联网研究的公开资料对照']

const UPDATE_TEXT = [
  (tag: string) => `换了一套素材重新跑了一遍，结论一致，「${tag}」在新场景下同样有效。`,
  () => '把步骤压缩成了 3 步，新手更容易上手；原来的第 2 步可以和第 3 步合并。',
  () => '提醒注意版本差异：工具更新后部分参数名变了，按新版本文档调整即可。',
  () => '补充了一组失败案例：素材质量差时效果明显下降，先保证输入干净。',
]
interface Upd { at: number; merged?: string }
function updateSection(u: Upd, textIdx: number, r: () => number, tags: string[]): string {
  const head = `## ${iso(u.at).slice(0, 10)} 更新`
  if (u.merged) return [head, '', `合并自${u.merged}；新增来源见右侧「来源」，正文中的群内原话与做法已按今天的讨论更新。`, ''].join('\n')
  return [head, '', `${pick(r, SPEAKERS)}（${pick(r, WHITELIST).name}）补充：${UPDATE_TEXT[textIdx % UPDATE_TEXT.length]!(tags[0] ?? '这个做法')}`, ''].join('\n')
}
/** 「{日期} 更新」放在参考列表之前，参考列表保持在正文末尾；同一条目的各次更新文字不重复 */
function withUpdates(body: string, ups: Upd[], r: () => number, tags: string[]): string {
  if (!ups.length) return body
  const at = body.search(/\n---\n\n参考：/)
  const base = Math.floor(r() * UPDATE_TEXT.length)
  const md = ups.map((u, i) => updateSection(u, base + i, r, tags)).join('\n')
  return at < 0 ? `${body}\n\n${md}` : `${body.slice(0, at)}\n\n${md}${body.slice(at)}`
}

export function buildKb(today: ReportDTO, reportIds: string[], end: number): KbArticleDTO[] {
  const out: KbArticleDTO[] = []
  const created = Date.parse(today.created_at)
  const vAt = (k: number) => (k === 0 ? created + 2 * 60_000 : end - DAY_OFFSETS[k]! * DAY + 3 * 60_000)
  const rid = (k: number) => reportIds[DAY_OFFSETS[k]!] ?? ''
  ARTICLE_SPECS.forEach((spec, i) => {
    const art = today.articles?.[i]
    if (!art) return
    const s = SEEDS[spec.seeds[0]!]!, r = rng(700 + i)
    const n = spec.kb.isNew ? 1 : Math.min(spec.kb.versions, DAY_OFFSETS.length)
    const ks = Array.from({ length: n }, (_, k) => n - 1 - k) // 最旧在前
    const versions = ks.map((k, j) => ({ at: iso(vAt(k)), report_id: rid(k),
      note: j === 0 ? '新建：首次出现于当日专题' : k === 0 ? `合并更新：今日专题 ${String(art.seq).padStart(2, '0')}，来源 +${art.sources.length}` : pick(r, NOTES) }))
    const old = ks.slice(0, -1).flatMap(() => [{ group_name: pick(r, WHITELIST).name, sender: pick(r, SPEAKERS), sent_at: iso(end - (2 + r() * 6) * DAY) }])
    const ups = ks.slice(1).map((k): Upd => ({ at: vAt(k), merged: k === 0 ? `今日报告的专题 ${String(art.seq).padStart(2, '0')}，来源 +${art.sources.length}` : undefined }))
    const body = withUpdates(art.body_md.replace(/^# \d+-/, '# '), ups, r, s.tags)
    out.push({ id: kbIdOf(spec), title: art.title, category: art.category, tags: s.tags, hook: art.hook, risk_flags: art.risk_flags,
      created_at: versions[0]!.at, updated_at: versions[versions.length - 1]!.at, body_md: body, versions,
      sources: [...art.sources.map((x) => ({ group_name: x.group_name, sender: x.sender, sent_at: x.sent_at })), ...old], related: [] })
  })
  OLDER.forEach((si, i) => {
    const s = SEEDS[si]!, r = rng(800 + i)
    const n = 1 + (i % 3)
    const days = Array.from({ length: n }, (_, k) => 3 + (i % 4) - k).map((d) => Math.max(1, d))
    const versions = days.map((d, k) => ({ at: iso(end - d * DAY + 4 * 60_000), report_id: reportIds[d] ?? '', note: k === 0 ? '新建' : pick(r, NOTES) }))
    const risk = riskOf(si)
    const quotes = s.ev.flatMap(([who, q]) => [`> ${q}`, '>', `> —— ${who}`, ''])
    const L = [`# ${s.title}`, '', `> 分类：${CATEGORIES[s.cat]}`, '', `**一句话**：${s.hook}`, '', '## 背景与群内讨论', '', s.summary, '', ...quotes,
      '## 关键做法', '', ...s.steps.map((x, k) => `${k + 1}. ${x}`), '']
    if (s.links?.length) L.push('## 资源', '', ...s.links.filter((l) => /^https?:/.test(l.url)).map((l) => `- [${l.title ?? l.url}](${l.url})`), '')
    if (risk.length) L.push('## 风险提示', '', `${risk.map((x) => `\`⚠ ${x}\``).join(' ')}　以上做法来自群友经验，请结合自身情况判断。`, '', `> ${RISK_DISCLAIMER}`, '')
    out.push({ id: `kb-o${String(si).padStart(2, '0')}`, title: s.title, category: CATEGORIES[s.cat] ?? CATEGORIES['99']!, tags: s.tags, hook: s.hook, risk_flags: risk,
      created_at: versions[0]!.at, updated_at: versions[versions.length - 1]!.at,
      body_md: withUpdates(L.join('\n'), days.slice(1).map((d) => ({ at: end - d * DAY + 4 * 60_000 })), r, s.tags), versions,
      sources: s.ev.map(([who], k) => ({ group_name: pick(r, WHITELIST).name, sender: who, sent_at: iso(end - (days[0]! + k * 0.1) * DAY) })), related: [] })
  })
  for (const a of out) {
    a.related = out.filter((b) => b.id !== a.id).map((b) => ({ b, n: b.tags.filter((x) => a.tags.includes(x)).length + (b.category === a.category ? 0.5 : 0) }))
      .filter((x) => x.n >= 1).sort((x, y) => y.n - x.n).slice(0, 4).map(({ b }) => ({ id: b.id, title: b.title }))
  }
  return out
}
