/** mock 服务端的内存状态（刷新页面即重置） */
import type { ChannelDTO, GroupDTO, KbArticleDTO, LogDTO, OverviewDTO, PromptDTO, ReportDTO, RunDTO, ScheduleDTO, SettingsDTO } from '@/api/types'
import { buildAllReports } from './build/reports'
import { buildOverview, initialGroups } from './build/overview'
import { CHANNEL_KINDS, initialChannels } from './fixtures/channels'
import { PLATFORM_STATE, type PlatformState } from './fixtures/platforms'
import { INITIAL_PROMPTS, initialSettings } from './fixtures/settings'
import { initialSchedules, runFromPlan, systemLogs } from './fixtures/misc'
import { buildPlan, planLogs } from './stages'
import { buildKb } from './build/kb'
import { DAY, latestReportEnd, ymd } from './util'

type RealP = 'wechat' | 'qq' | 'feishu'

export interface MockState {
  reports: ReportDTO[]
  groups: GroupDTO[]
  platforms: Record<RealP, PlatformState>
  channels: ChannelDTO[]
  settings: SettingsDTO
  prompts: PromptDTO[]
  schedules: ScheduleDTO[]
  runs: RunDTO[]
  runLogs: Record<string, LogDTO[]>
  syslog: LogDTO[]
  current: RunDTO | null
  extraMessages: number
  ingest: Record<RealP, number>
  tokensToday: number
  costToday: number
  demoSeeded: boolean
  /** v2 知识库（20 条） */
  kb: KbArticleDTO[]
}

function init(): MockState {
  const now = Date.now()
  const end = latestReportEnd(now)
  const reports = buildAllReports(end)
  const channels = initialChannels(now)
  const runs: RunDTO[] = []
  const runLogs: Record<string, LogDTO[]> = {}
  reports.forEach((rep, i) => {
    const winEnd = end - i * DAY
    const failChannel = rep.deliveries.find((d) => !d.ok)?.channel_id
    const plan = buildPlan({ stats: rep.stats, items: rep.items, channels, seed: 300 + i, failChannel })
    const run = runFromPlan({ plan, id: rep.run_id, trigger: 'schedule', start: winEnd + 4000, status: failChannel ? 'partial' : 'success', dry: false,
      winStart: winEnd - DAY, winEnd, reportId: rep.id, raw: rep.stats.messages_raw, clean: rep.stats.messages_clean, items: rep.items_total,
      error: failChannel ? '1 个通道投递失败：QQ · 私聊主号（NapCat 未登录）' : undefined })
    runs.push(run)
    runLogs[run.id] = planLogs(plan, run.id, winEnd + 4000)
  })
  // 一次手动「仅预览」
  const dryPlan = buildPlan({ stats: reports[1]!.stats, items: reports[1]!.items, channels, seed: 401 })
  const dry = runFromPlan({ plan: dryPlan, id: `run-dry-${reports[1]!.id.slice(4, 12)}`, trigger: 'manual', start: end - DAY + 5.2 * 3600_000, status: 'success', dry: true,
    winStart: end - 2 * DAY + 5 * 3600_000, winEnd: end - DAY + 5.2 * 3600_000, raw: reports[1]!.stats.messages_raw, clean: reports[1]!.stats.messages_clean, items: reports[1]!.items_total })
  runs.splice(1, 0, dry)
  runLogs[dry.id] = planLogs(dryPlan, dry.id, end - DAY + 5.2 * 3600_000)
  const lastSched = runs[0]
  return {
    reports, groups: initialGroups(reports[0]!, now), platforms: structuredClone(PLATFORM_STATE), channels,
    settings: initialSettings(), prompts: structuredClone(INITIAL_PROMPTS), schedules: initialSchedules(now, lastSched),
    runs, runLogs, syslog: systemLogs(now, runLogs[runs[0]!.id] ?? []), current: null, extraMessages: 0, ingest: { wechat: 0, qq: 0, feishu: 0 },
    tokensToday: runs[0]!.totals.tokens_in + runs[0]!.totals.tokens_out, costToday: runs[0]!.totals.cost_cny, demoSeeded: false,
    kb: buildKb(reports[0]!, reports.map((r) => r.id), end),
  }
}

/**
 * overview.kb：「今日」按最近一份报告所在的东八区日期算（与大屏「今日情报」取最近一份报告一致）。
 * 08:00 之前打开时最近一份是昨天的报告，按日历日会全是 0。
 */
function kbCounts(): NonNullable<OverviewDTO['kb']> {
  const latest = S.reports[0]
  const today = ymd(latest ? Date.parse(latest.created_at) : Date.now())
  const day = (s: string) => ymd(Date.parse(s))
  const fresh = S.kb.filter((a) => day(a.created_at) === today).length
  return { total: S.kb.length, new_today: fresh, updated_today: S.kb.filter((a) => day(a.updated_at) === today && day(a.created_at) !== today).length }
}

export const S: MockState = init()
export { CHANNEL_KINDS }

export function overviewNow(): OverviewDTO {
  const settings = S.settings
  const consent = (settings.privacy as { cloud_llm_consent?: boolean }).cloud_llm_consent !== false
  const provider = consent ? String((settings.llm as { provider?: string }).provider ?? 'offline') : 'offline'
  const next = S.schedules.filter((s) => s.enabled && s.next_run_at).map((s) => s.next_run_at!).sort()[0]
  const ov = buildOverview({
    now: Date.now(), reports: S.reports, groups: S.groups, platforms: S.platforms, lastRun: S.runs[0], currentRun: S.current ?? undefined,
    nextRunAt: next, extraMessages: S.extraMessages, ingest: S.ingest,
    llm: { provider, model: provider === 'offline' ? undefined : String((settings.llm as { model?: string }).model ?? ''), ready: true,
      cloud_consent: consent, tokens_today: S.tokensToday, cost_today_cny: Math.round(S.costToday * 100) / 100 },
  })
  return { ...ov, kb: kbCounts() }
}
