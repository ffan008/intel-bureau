/** OverviewDTO 组装（mock 服务端状态 → 大屏数据） */
import type { GroupDTO, OverviewDTO, PlatformDTO, ReportDTO, RunDTO } from '@/api/types'
import { agentsFromRun } from '@/utils/agents'
import { GROUP_SEEDS, WHITELIST, groupKey } from '../data/groups'
import { ADAPTERS, PLATFORM_LABEL, type PlatformState } from '../fixtures/platforms'
import { DAY, iso } from '../util'
import { seedIndexOfItem, shortOf } from './items'

type RealP = 'wechat' | 'qq' | 'feishu'

export function platformDTO(p: RealP, st: PlatformState, groups: GroupDTO[], now: number): PlatformDTO {
  const gs = groups.filter((g) => g.platform === p)
  const wl = gs.filter((g) => g.whitelisted)
  return {
    platform: p, label: PLATFORM_LABEL[p], enabled: st.enabled, adapter: st.adapter, adapters: ADAPTERS[p],
    health: st.enabled ? st.health : 'disabled', detail: st.enabled ? st.detail : '已停用', hint: st.enabled ? st.hint : '在「情报源」页启用该平台',
    checked_at: iso(now - st.checkedMinAgo * 60_000), groups_total: gs.length, groups_whitelisted: wl.length,
    messages_24h: wl.reduce((a, g) => a + g.messages_24h, 0), last_collect_at: iso(now - st.collectedMinAgo * 60_000),
  }
}

export function initialGroups(report: ReportDTO, now: number): GroupDTO[] {
  return GROUP_SEEDS.map((g, i) => {
    const s = report.stats.top_groups.find((x) => x.name === g.name)
    const m24 = s?.messages ?? 0
    return {
      key: groupKey(g), platform: g.platform, native_id: g.native, name: g.name, member_count: g.members, whitelisted: g.whitelisted,
      weight: g.weight, tags: [...g.tags], messages_24h: m24, messages_7d: g.whitelisted ? Math.round(m24 * (6.1 + (i % 3) * 0.4)) : 0,
      last_message_at: g.whitelisted ? iso(now - (3 + i * 7) * 60_000) : iso(now - (2 + i) * 3600_000),
      last_collect_at: g.whitelisted ? iso(now - 186 * 60_000) : undefined,
    }
  })
}

export function constellation(report: ReportDTO, groups: GroupDTO[]): OverviewDTO['constellation'] {
  const nodes: OverviewDTO['constellation']['nodes'] = []
  const links: OverviewDTO['constellation']['links'] = []
  const wl = groups.filter((g) => g.whitelisted)
  for (const p of ['wechat', 'qq', 'feishu'] as RealP[]) {
    nodes.push({ id: `platform:${p}`, name: PLATFORM_LABEL[p], type: 'platform', platform: p, value: wl.filter((g) => g.platform === p).reduce((a, g) => a + g.messages_24h, 0) })
  }
  for (const g of wl) {
    nodes.push({ id: g.key, name: g.name, type: 'group', platform: g.platform, value: g.messages_24h })
    links.push({ source: `platform:${g.platform}`, target: g.key, value: g.messages_24h })
  }
  for (const it of report.items.slice(0, 12)) {
    const id = `topic:${it.id}`
    nodes.push({ id, name: shortOf(seedIndexOfItem(it.id)) || it.title.slice(0, 8), type: 'topic', value: it.sources.reduce((a, s) => a + s.count, 0), category: it.category })
    for (const s of it.sources) if (wl.some((g) => g.key === s.group_key)) links.push({ source: s.group_key, target: id, value: s.count })
  }
  return { nodes, links }
}

export interface OverviewInput {
  now: number; reports: ReportDTO[]; groups: GroupDTO[]; platforms: Record<RealP, PlatformState>; lastRun?: RunDTO; currentRun?: RunDTO
  nextRunAt?: string; extraMessages: number; ingest: Record<RealP, number>; llm: OverviewDTO['llm']
}

export function buildOverview(o: OverviewInput): OverviewDTO {
  const [latest, prev] = o.reports
  const stats = latest!.stats
  const groups = o.groups.map((g) => (g.whitelisted ? { ...g, messages_24h: g.messages_24h + (g.platform === 'qq' ? Math.round(o.ingest.qq / 3) : g.platform === 'wechat' ? Math.round(o.ingest.wechat / 4) : 0) } : g))
  const platforms = (['wechat', 'qq', 'feishu'] as RealP[]).map((p) => platformDTO(p, o.platforms[p], groups, o.now))
  const m24 = platforms.reduce((a, p) => a + p.messages_24h, 0) + o.extraMessages
  const prevRaw = prev?.stats.messages_raw ?? m24
  const wl = groups.filter((g) => g.whitelisted)
  const items = [...latest!.items].sort((a, b) => a.rank - b.rank)
  const tick = items.slice(0, 10).map((it) => `【${it.category}】${it.title}`)
  latest!.deliveries.forEach((d) => tick.push(`${d.ok ? '✓' : '✗'} ${d.channel_name} 投递${d.ok ? '成功' : '失败'} · ${latest!.title.split('|')[1]?.trim() ?? ''}`))
  const run = o.currentRun ?? o.lastRun
  return {
    generated_at: iso(o.now), mode: 'live', window: { start: iso(o.now - DAY), end: iso(o.now) },
    kpis: {
      messages_24h: m24, messages_delta: Math.round(((m24 - prevRaw) / Math.max(1, prevRaw)) * 1000) / 1000,
      intel_today: latest!.items_total, intel_delta: latest!.items_total - (prev?.items_total ?? latest!.items_total),
      groups_active: wl.filter((g) => g.messages_24h > 0).length, groups_whitelisted: wl.length, snr: stats.snr,
      signals_rising: stats.rising.filter((r) => r.z >= 2).length, next_run_at: o.nextRunAt, last_run_status: o.lastRun?.status,
    },
    platforms, stats, constellation: constellation(latest!, groups), headlines: items.filter((i) => i.is_headline),
    latest_report: { id: latest!.id, run_id: latest!.run_id, title: latest!.title, date_label: latest!.date_label, window_label: latest!.window_label,
      created_at: latest!.created_at, items_total: latest!.items_total, headlines: latest!.headlines, deliveries: latest!.deliveries },
    current_run: o.currentRun, last_run: o.lastRun,
    agents: run ? agentsFromRun(run).map((a) => ({ code: a.code, name: a.name, stages: a.stages.map((s) => s.name), status: a.status, task: a.task, metric: a.metric })) : [],
    ticker: tick, llm: o.llm,
  }
}

export const WHITELIST_COUNT = WHITELIST.length
