/** 报告：今天一份 v2（手写风向判断 + 板块 / 专题 / 资源 / 媒体 / 分群）+ 往期 6 份 v1 */
import type { IntelItemDTO, ReportDTO, StatsDTO } from '@/api/types'
import { DAY, dateLabel, mdhm, rng, shuffle, ymd } from '../util'
import { SEEDS, TODAY_SEEDS, buildItems } from './items'
import { buildStats, historyStats } from './stats'
import { buildFullMd, buildSummaryMd } from './markdown'
import { attachV2 } from './v2'

export const TODAY_JUDGMENTS: ReportDTO['judgments'] = [
  { text: 'Agent 编排从「单会话」转向「多 Agent 并行 + 隔离工作区」', basis: '「子 Agent」今日 46 次（7 日均值 6.1，z=4.1）；Claude Code 实战营与飞书 · 增长小组同时出现 worktree 并行实践' },
  { text: 'AI 绘画讨论的重心从「出图」转向「角色一致性」', basis: '线稿上色两步法、多图融合点名法、AI 漫画工作流三条情报都在解决同一个问题，「角色一致性」词频上升' },
  { text: '短剧出海进入精细化运营：开头钩子、字幕本地化、AI 分镜岗位同时升温', basis: '短剧出海交流「冲突前置」z=3.6；A/B 数据完播率 18%→31%；本周已有 3 家公司招 AI 分镜' },
  { text: '「代开学生认证」话术跨群扩散，按违法高危只记录不扩展', basis: '同一话术出现在 3 个群；另有付费训练营退款、数字人限流两条带风险标注的专题照常收录' },
]

export const winLabelOf = (start: number, end: number): string => `${mdhm(start)} ~ ${mdhm(end)}`

export type Deliv = ReportDTO['deliveries']
export const DELIV_OK: Deliv = [
  { channel_id: 'ch-feishu-bot', channel_name: '飞书 · 情报群机器人', kind: 'feishu_webhook', ok: true },
  { channel_id: 'ch-serverchan', channel_name: '微信 · Server酱', kind: 'serverchan', ok: true },
  { channel_id: 'ch-qq', channel_name: 'QQ · 私聊主号', kind: 'qq_onebot', ok: true },
  { channel_id: 'ch-local', channel_name: '本地归档', kind: 'local_archive', ok: true },
]

function genericJudgments(items: IntelItemDTO[]): ReportDTO['judgments'] {
  return items.slice(0, 3).map((it) => ({
    text: `「${it.title.split(/[：:，,]/)[0]}」成为当日讨论焦点`,
    basis: `${it.sources.map((s) => s.group_name).join('、')} 合计 ${it.sources.reduce((a, s) => a + s.count, 0)} 条相关消息，评分 ${it.score.toFixed(1)}`,
  }))
}

export function assembleReport(o: {
  id: string; runId: string; start: number; end: number; created: number; stats: StatsDTO; items: IntelItemDTO[]
  judgments?: ReportDTO['judgments']; deliveries: Deliv; suffix?: string
}): ReportDTO {
  const title = `情报局 · 每日风向标 | ${dateLabel(o.end)}${o.suffix ?? ''}`
  const win = winLabelOf(o.start, o.end)
  const judgments = o.judgments ?? genericJudgments(o.items)
  return {
    id: o.id, run_id: o.runId, title, date_label: dateLabel(o.end), window_label: win, created_at: new Date(o.created).toISOString(),
    items_total: o.items.length,
    headlines: o.items.filter((i) => i.is_headline).map((i) => ({ title: i.title, category: i.category, score: i.score })),
    deliveries: o.deliveries, judgments, items: o.items, stats: o.stats,
    full_md: buildFullMd(title, win, o.stats, o.items, judgments),
    summary_md: buildSummaryMd(title, win, o.stats, o.items, judgments),
  }
}

export function buildAllReports(latestEnd: number): ReportDTO[] {
  const out: ReportDTO[] = []
  const id0 = `rpt-${ymd(latestEnd)}-0800`
  // 今天这份是 v2 报告（板块阅读器）；往期 6 份保持 v1 结构，用来验证旧报告退回单页阅读器
  out.push(attachV2(assembleReport({
    id: id0, runId: `run-${ymd(latestEnd)}-0800`, start: latestEnd - DAY, end: latestEnd, created: latestEnd + 3 * 60_000 + 12_000,
    stats: buildStats(20261028), items: buildItems(id0, TODAY_SEEDS, latestEnd, 7, 24, { v2: true }), judgments: TODAY_JUDGMENTS, deliveries: DELIV_OK,
  }), latestEnd))
  const freshToday = new Set(TODAY_SEEDS.filter((i) => SEEDS[i]!.trend === 'new'))
  const pool = SEEDS.map((_, i) => i).filter((i) => !freshToday.has(i))
  for (let d = 1; d <= 6; d++) {
    const end = latestEnd - d * DAY
    const r = rng(900 + d)
    const idx = shuffle(r, pool).slice(0, 10 + Math.floor(r() * 5))
    const id = `rpt-${ymd(end)}-0800`
    const deliveries = d === 3
      ? DELIV_OK.map((x) => (x.kind === 'qq_onebot' ? { ...x, ok: false } : x))
      : DELIV_OK
    out.push(assembleReport({
      id, runId: `run-${ymd(end)}-0800`, start: end - DAY, end, created: end + (2 + d % 3) * 60_000 + 40_000,
      stats: historyStats(5000 + d), items: buildItems(id, idx, end, 100 + d), deliveries,
    }))
  }
  return out
}
