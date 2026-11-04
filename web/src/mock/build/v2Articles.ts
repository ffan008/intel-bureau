/** v2 mock：专题文章（body_md 按 V2_KNOWLEDGE §3.2 模板，序号、来源、计数由代码生成，提示词原文照录） */
import type { ArticleDTO, Evidence, IntelItemDTO } from '@/api/types'
import { RISK_DISCLAIMER } from '@/utils/risk'
import { ARTICLES_A } from '../data/articlesA'
import { ARTICLES_B } from '../data/articlesB'
import { RESOURCES } from '../data/resourcesV2'
import type { ArticleSpec, PromptSpec } from '../data/v2types'
import { CATEGORIES } from '../data/groups'
import { mdhm } from '../util'
import { SEEDS, V2_RISK, seedIndexOfItem } from './items'

export const ARTICLE_SPECS: ArticleSpec[] = [...ARTICLES_A, ...ARTICLES_B]
export const ARTICLE_SEEDS = new Set(ARTICLE_SPECS.flatMap((a) => a.seeds))
export const PL: Record<string, string> = { wechat: '微信', qq: 'QQ', feishu: '飞书', demo: '演示' }
export const pad2 = (n: number) => String(n).padStart(2, '0')
export const kbIdOf = (spec: ArticleSpec) => `kb-s${pad2(spec.seeds[0]!)}`
export const riskOf = (si: number): string[] => V2_RISK[si] ?? SEEDS[si]?.risk ?? []
const t = (e: { sent_at: string }) => mdhm(Date.parse(e.sent_at))

/** 每篇专题收录的资源（按链接匹配） */
const ART_RES: Record<number, RegExp> = {
  1: /anthropics\/claude-code|worktree/i, 2: /ComfyUI\/|Lineart|ai_drawing_lab/, 4: /shortdrama_ops|DramaAB/, 5: /kling/i, 6: /hooks/,
  7: /whisper|subtitle/i, 8: /n8n/i, 9: /picturebook/, 10: /Storyboard/,
}

/** 提示词的群以证据里同一发言人的群为准（证据的群由 items.ts 按种子分配），找不到时用素材里写的群 */
export const promptGroup = (p: PromptSpec, ev: Evidence[]): string => ev.find((e) => e.sender === p.who)?.group_name ?? p.group

export function evidenceFor(items: IntelItemDTO[], seeds: number[]): Evidence[] {
  return items.filter((i) => seeds.includes(seedIndexOfItem(i.id))).flatMap((i) => i.evidence).sort((a, b) => a.sent_at.localeCompare(b.sent_at))
}

function resourceLines(seq: number, seedIdx: number): string[] {
  const re = ART_RES[seq]
  const out = re ? RESOURCES.filter((r) => re.test(r.url)).map((r) => {
    if (r.kind === 'github') return `- [${r.title}](${r.url}) · ★ ${Number(r.meta?.stars).toLocaleString('en-US')} · ${r.meta?.language} · ${r.meta?.description}`
    if (r.kind === 'netdisk') return `- [${r.title}](${r.url}) · 提取码：${r.code ? `\`${r.code}\`` : '无'}${r.note ? ` · ${r.note}` : ''}`
    return `- [${r.title}](${r.url})${r.note ? ` · ${r.note}` : ''}`
  }) : []
  for (const l of SEEDS[seedIdx]?.links ?? []) if (/^https?:/.test(l.url) && !out.some((x) => x.includes(l.url))) out.push(`- [${l.title ?? l.url}](${l.url})`)
  return out
}

export function buildArticle(spec: ArticleSpec, seq: number, items: IntelItemDTO[]): ArticleDTO {
  const si = spec.seeds[0]!
  const main = SEEDS[si]!
  const ev = evidenceFor(items, spec.seeds)
  const title = spec.title ?? main.title
  const hook = spec.hook ?? main.hook
  const category = CATEGORIES[spec.cat ?? main.cat] ?? CATEGORIES['99']!
  const risk = riskOf(si)
  const chips = risk.map((r) => `\`⚠ ${r}\``).join(' ')
  const L: string[] = [`# ${pad2(seq)}-${title}`, '',
    `> 分类：${category}｜来源：${ev.slice(0, 3).map((e) => `${PL[e.platform]}·${e.group_name}·${e.sender}·${t(e)}`).join('；')}${chips ? `｜${chips}` : ''}`, '',
    `**一句话**：${hook}`, '', '## 背景与群内讨论', '']
  // 每段配一条原话：优先选段落里提到的发言人，没有就按时间顺序取下一条
  const used = new Set<Evidence>()
  spec.background.forEach((p) => {
    L.push(p, '')
    const e = ev.find((x) => !used.has(x) && p.includes(x.sender)) ?? ev.find((x) => !used.has(x))
    if (!e) return
    used.add(e)
    L.push(`> ${e.quote}`, '>', `> —— ${e.sender} · ${e.group_name} · ${t(e)}`, '')
  })
  L.push('## 关键做法', '', ...(spec.steps ?? main.steps).map((s, i) => `${i + 1}. ${s}`), '')
  if (spec.prompts?.length) {
    L.push('## 提示词 / 参数原文', '')
    for (const p of spec.prompts) L.push(`**${p.label}**（${p.who} · ${promptGroup(p, ev)} · 用途：${p.use}）`, '', p.text.trimStart().startsWith('{') ? '```json' : '```text', p.text, '```', '')
  }
  if (spec.research.length) {
    L.push('## 扩展研究', '', ...spec.research.map((r) => `- ${r}`), '')
    if (spec.conflict) L.push(`**与群内说法的差异**：${spec.conflict}`, '')
  }
  const res = resourceLines(seq, si)
  if (res.length) L.push('## 资源', '', ...res, '')
  L.push('## 适用范围、成本与数据', '', ...spec.scope.map((s) => `- ${s}`), '')
  L.push('## 风险提示', '')
  if (risk.length) L.push(`${chips}　${spec.riskNote ?? '以上做法来自群友经验，请结合自身情况判断。'}`, '', `> ${RISK_DISCLAIMER}`, '')
  else L.push('无特别风险标签。', '')
  if (spec.refs.length) L.push('---', '', '参考：', ...spec.refs.map((r, i) => `[${i + 1}] ${r.title} · ${r.url}`))
  return {
    id: `art-${pad2(seq)}-s${pad2(si)}`, seq, title, hook, category, body_md: L.join('\n'), risk_flags: risk, risk_note: spec.riskNote,
    sources: ev.map((e) => ({ group_name: e.group_name, platform: e.platform, sender: e.sender, sent_at: e.sent_at })),
    images: spec.images ?? [], kb_id: kbIdOf(spec), research_refs: spec.refs.map((r, i) => ({ n: i + 1, title: r.title, url: r.url })),
  }
}
