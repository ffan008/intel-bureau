/** 情报素材 → IntelItemDTO（证据时间、来源计数、评分由固定种子生成） */
import type { Evidence, IntelItemDTO } from '@/api/types'
import { INTEL_A } from '../data/intelA'
import { INTEL_B } from '../data/intelB'
import { INTEL_C } from '../data/intelC'
import type { IntelSeed } from '../data/seedTypes'
import { CATEGORIES, INTERESTS, SPEAKERS, groupById, groupKey } from '../data/groups'
import { HOUR, intBetween, iso, pick, rng, ymd } from '../util'

export const SEEDS: IntelSeed[] = [...INTEL_A, ...INTEL_B, ...INTEL_C]
const round1 = (n: number) => Math.round(n * 10) / 10

export function relevanceOf(s: IntelSeed): number {
  const hits = s.tags.filter((t) => INTERESTS.includes(t)).length
  return Math.min(5, round1(2.3 + hits * 0.85))
}

/** riskPenalty=false：v2 的 label 策略，风险标签不扣分（V2_KNOWLEDGE §2） */
export function scoreOf(s: IntelSeed, riskPenalty = true): number {
  const [n, a, c] = s.sc
  const base = 0.22 * n + 0.24 * a + 0.2 * c + 0.18 * s.heat + 0.16 * relevanceOf(s)
  const risk = riskPenalty && s.risk?.length ? 0.35 + 0.15 * (s.risk.length - 1) : 0
  const repeat = s.trend === 'repeat' ? 0.3 : 0
  return round1(Math.max(0, base - risk - repeat))
}

/** v2 报告里按 §2 重新标注的风险标签（素材里的旧标签是 v1 口径） */
export const V2_RISK: Record<number, string[]> = {
  7: ['平台规则'], 9: ['账号风险', '平台规则'], 10: ['违法高危', '账号风险'], 21: ['版权风险'], 27: ['金钱风险', '广告引流', '未核实'],
}

/** 证据时间集中在晚间与午间 */
function evidenceTime(r: () => number, windowEnd: number, spanH: number): number {
  const hoursBack = [1.5, 2.5, 3.5, 11, 12.5, 13.5, 9, 6][Math.floor(r() * 8)]! * (spanH / 24)
  return windowEnd - Math.round((hoursBack + r() * 1.2) * HOUR)
}

export function buildItems(reportId: string, seedIdx: number[], windowEnd: number, seed: number, spanH = 24, opt: { v2?: boolean } = {}): IntelItemDTO[] {
  const r = rng(seed)
  const items = seedIdx.map((si) => {
    const s = SEEDS[si]!
    const groups = s.groups.map(groupById)
    const evidence: Evidence[] = s.ev.map(([sender, quote], j) => {
      const g = groups[j % groups.length]!
      return {
        message_id: `m${(si * 977 + j * 131 + seed) % 99991}`,
        group_key: groupKey(g), group_name: g.name, platform: g.platform,
        sender, sent_at: iso(evidenceTime(r, windowEnd, spanH)), quote,
      }
    }).sort((a, b) => a.sent_at.localeCompare(b.sent_at))
    const sources = groups.map((g, j) => ({
      group_key: groupKey(g), group_name: g.name, platform: g.platform,
      count: j === 0 ? intBetween(r, 9, 26) : intBetween(r, 3, 11),
    }))
    const participants = [...new Set([...s.ev.map((e) => e[0]), pick(r, SPEAKERS), pick(r, SPEAKERS)])].slice(0, 5)
    const item: IntelItemDTO = {
      id: `itm-${ymd(windowEnd)}-${String(si).padStart(2, '0')}`,
      report_id: reportId, rank: 0, title: s.title, hook: s.hook, summary: s.summary,
      category: CATEGORIES[s.cat] ?? CATEGORIES['99']!, kind: s.kind, score: scoreOf(s, !opt.v2),
      scores: { novelty: s.sc[0], actionability: s.sc[1], credibility: s.sc[2], heat: s.heat, relevance: relevanceOf(s) },
      trend: s.trend, risk_flags: (opt.v2 ? V2_RISK[si] : undefined) ?? s.risk ?? [], tags: s.tags, steps: s.steps, tools: s.tools,
      links: s.links ?? [], evidence, sources, participants, is_headline: false, is_feature: false,
    }
    return item
  })
  items.sort((a, b) => b.score - a.score)
  if (opt.v2) {
    // v2：风险内容可进头条，只有违法高危不进；专题由 build/v2.ts 按专题文章标记
    let heads = 0
    items.forEach((it, i) => {
      it.rank = i + 1
      it.is_headline = heads < 5 && !it.risk_flags.includes('违法高危') && ++heads > 0
      it.is_feature = false
    })
    return items
  }
  items.forEach((it, i) => {
    it.rank = i + 1
    it.is_headline = i < 5
    it.is_feature = i < 8 && !it.risk_flags.includes('广告引流')
  })
  return items
}

/** 今天这份报告收录的素材下标（其余素材分给往期） */
export const TODAY_SEEDS = [0, 1, 2, 3, 4, 5, 6, 7, 9, 10, 12, 16, 19, 21, 24, 27]
export const EXTRA_SEEDS = [13, 28]
export const shortOf = (seedIndex: number): string => SEEDS[seedIndex]?.short ?? ''
export const seedIndexOfItem = (id: string): number => Number(id.slice(-2))
