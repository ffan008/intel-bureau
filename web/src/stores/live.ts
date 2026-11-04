/**
 * 大屏实时状态：overview + SSE。
 * - overview.dirty / 重连 / run.finished → 重新拉 /api/overview（防抖，不并发）。
 * - 运行中的 Agent 状态直接由 run.stage 事件推导，不等 overview。
 */
import { computed, reactive } from 'vue'
import { api } from '@/api/endpoints'
import { EventStream, type StreamState } from '@/api/sse'
import type { AgentCode, ChannelDTO, LogDTO, OverviewDTO, Platform, RunDTO, SettingsDTO } from '@/api/types'
import { agentsFromOverview, agentsFromRun, isActive, runProgress, type AgentView } from '@/utils/agents'
import { STAGE_AGENT, platformLabel } from '@/utils/meta'
import { fmtTime } from '@/utils/format'
import { router } from '@/router'
import { app } from './app'
import { notify } from './toast'

export interface TermLine { id: number; ts: string; level: LogDTO['level']; agent: string; text: string; sep?: boolean; instant?: boolean }
export interface Receipt { channel_id: string; channel_name: string; kind: string; ok: boolean; detail: string; at: string }
export interface TickerExtra { id: number; text: string; color: string }

const MAX_LINES = 200
let lineSeq = 0

export const live = reactive({
  overview: null as OverviewDTO | null,
  loading: false,
  loadError: '',
  stream: 'idle' as StreamState,
  retryInMs: 0,
  run: null as RunDTO | null,
  /** 本次会话里通过 SSE / 点击观察到的运行（优先于 overview.agents 显示） */
  sessionRun: false,
  taskOverride: {} as Partial<Record<AgentCode, string>>,
  log: [] as TermLine[],
  receipts: {} as Record<string, Receipt>,
  channels: [] as ChannelDTO[],
  settings: null as SettingsDTO | null,
  tickerExtra: [] as TickerExtra[],
  ingestPulse: {} as Partial<Record<Platform, number>>,
  /** report.created 时 +1，情报档案据此刷新列表 */
  reportsVersion: 0,
  intelTrend: [] as number[],
  lastEventAt: '',
})

export const agentViews = computed<AgentView[]>(() => {
  const r = live.run
  if (r && (isActive(r) || live.sessionRun)) return agentsFromRun(r, isActive(r) ? live.taskOverride : {})
  if (live.overview?.agents?.length) return agentsFromOverview(live.overview.agents)
  if (r) return agentsFromRun(r)
  return agentsFromOverview([])
})
export const running = computed(() => isActive(live.run))
export const progress = computed(() => (running.value ? runProgress(live.run) : 0))

// ───────── overview ─────────
let ovTimer: ReturnType<typeof setTimeout> | null = null
let ovInflight = false
let ovPending = false

export function refreshOverview(delay = 350): void {
  if (ovTimer) clearTimeout(ovTimer)
  ovTimer = setTimeout(() => void fetchOverview(), delay)
}

export async function fetchOverview(): Promise<void> {
  if (ovInflight) { ovPending = true; return }
  ovInflight = true
  live.loading = !live.overview
  try {
    const ov = await api.overview({ silent: !!live.overview })
    live.overview = ov
    live.loadError = ''
    if (ov.current_run && isActive(ov.current_run)) {
      if (!live.run || live.run.id !== ov.current_run.id) { live.run = ov.current_run; live.sessionRun = true }
    } else if (!live.run && ov.last_run) {
      live.run = ov.last_run
    }
  } catch (e) {
    live.loadError = (e as Error).message
  } finally {
    live.loading = false
    ovInflight = false
    if (ovPending) { ovPending = false; refreshOverview(100) }
  }
}

// ───────── 终端 ─────────
function agentLabel(l: LogDTO): string {
  if (l.stage && STAGE_AGENT[l.stage]) return STAGE_AGENT[l.stage]
  const s = (l.source || 'SYSTEM').split('.').pop() || 'SYSTEM'
  return s.toUpperCase().slice(0, 10)
}
export function pushLog(l: LogDTO, instant = false): void {
  live.log.push({ id: ++lineSeq, ts: l.ts, level: l.level, agent: agentLabel(l), text: l.message, instant })
  if (live.log.length > MAX_LINES) live.log.splice(0, live.log.length - MAX_LINES)
  if (!instant && l.stage && live.run && (!l.run_id || l.run_id === live.run.id)) live.taskOverride[STAGE_AGENT[l.stage]] = l.message
}
function pushSep(text: string): void {
  live.log.push({ id: ++lineSeq, ts: new Date().toISOString(), level: 'info', agent: '', text, sep: true })
}

export async function loadTerminalHistory(): Promise<void> {
  if (live.log.length) return
  try {
    const run = live.run
    const lines = run ? await api.runLogs(run.id, { silent: true }) : await api.logs({ limit: 60 }, { silent: true })
    const tail = lines.filter((l) => l.level !== 'debug').slice(-60)
    if (run && tail.length) pushSep(`回放 · 运行 ${run.id} · ${fmtTime(run.started_at)}`)
    for (const l of tail) pushLog(l, true)
  } catch { /* 终端历史拿不到不影响大屏 */ }
}

export async function loadAux(): Promise<void> {
  const [ch, st, rp] = await Promise.allSettled([
    api.channels({ silent: true }), api.settings({ silent: true }), api.reports({ limit: 7 }, { silent: true }),
  ])
  if (ch.status === 'fulfilled') live.channels = ch.value
  if (st.status === 'fulfilled') live.settings = st.value
  if (rp.status === 'fulfilled') live.intelTrend = rp.value.items.map((r) => r.items_total).reverse()
}
// ───────── 跑马灯附加条目（投递回执、新报告） ─────────
let tickSeq = 0
function addTicker(text: string, color: string): void {
  live.tickerExtra.unshift({ id: ++tickSeq, text, color })
  if (live.tickerExtra.length > 12) live.tickerExtra.length = 12
}

// ───────── SSE ─────────
let stream: EventStream | null = null
let lastIngestLine = 0

async function syncRun(id: string): Promise<void> {
  try {
    const r = await api.run(id, { silent: true })
    if (!live.run || live.run.id === id || isActive(r)) { live.run = r; live.sessionRun = true }
  } catch { /* 下一次 overview 会补上 */ }
}

export function startLive(): void {
  if (stream) return
  stream = new EventStream({
    onState: (s, info) => { live.stream = s; live.retryInMs = info.retryInMs ?? 0 },
    onReconnect: () => {
      refreshOverview(0)
      if (live.run && isActive(live.run)) void syncRun(live.run.id)
    },
  })
  const s = stream
  s.on('hello', (d) => { live.lastEventAt = d.server_time; if (!app.mock) app.serverMode = d.mode })
  s.on('heartbeat', (d) => { live.lastEventAt = d.server_time })
  s.on('run.started', (r) => {
    live.run = r
    live.sessionRun = true
    live.taskOverride = {}
    pushSep(`▶ 运行 ${r.id} 启动 · ${r.trigger === 'schedule' ? '定时任务' : r.trigger === 'catchup' ? '补跑' : '手动'}${r.dry_run ? ' · 仅预览' : ''}`)
  })
  s.on('run.stage', ({ run_id, stage }) => {
    const r = live.run
    if (!r || r.id !== run_id) { void syncRun(run_id); return }
    const i = r.stages.findIndex((x) => x.name === stage.name)
    if (i >= 0) r.stages.splice(i, 1, stage)
    else r.stages.push(stage)
    if (r.status === 'queued') r.status = 'running'
    if (stage.status !== 'running') delete live.taskOverride[stage.agent]
  })
  s.on('run.log', (l) => { if (l.level !== 'debug') pushLog(l) })
  s.on('run.finished', (r) => {
    live.run = r
    live.sessionRun = true
    live.taskOverride = {}
    const label = r.status === 'success' ? '完成' : r.status === 'partial' ? '部分完成' : r.status === 'cancelled' ? '已取消' : '失败'
    pushSep(`■ 运行 ${r.id} ${label}${r.error ? ' · ' + r.error : ''}`)
    if (r.status === 'failed') notify.error('本次出报失败', { detail: r.error })
    else if (r.status === 'partial') notify.warn('本次出报部分完成', { detail: r.error ?? '部分群或通道失败，详见作战日志' })
    else if (r.status === 'cancelled') notify.info('已取消本次运行')
    refreshOverview(200)
  })
  s.on('report.created', (rep) => {
    live.reportsVersion++
    addTicker(`新报告 ${rep.title} · ${rep.items_total} 条情报`, '#22e4ff')
    notify.ok('新报告已生成', {
      detail: `${rep.title}，共 ${rep.items_total} 条情报`,
      action: { label: '查看', run: () => void router.push({ path: '/reports', query: { id: rep.id } }) },
      ttl: 9000,
    })
    void loadAux()
  })
  s.on('delivery.result', (d) => {
    const at = new Date().toISOString()
    live.receipts[d.channel_id] = { channel_id: d.channel_id, channel_name: d.channel_name, kind: d.kind, ok: d.ok, detail: d.detail, at }
    const ch = live.channels.find((c) => c.id === d.channel_id)
    if (ch) ch.last_result = { ok: d.ok, detail: d.detail, at }
    addTicker(`${d.ok ? '✓' : '✗'} 投递 ${d.channel_name} ${d.ok ? '成功' : '失败：' + d.detail}`, d.ok ? '#2bff9a' : '#ff4d5e')
  })
  s.on('ingest.message', (d) => {
    live.ingestPulse[d.platform] = Date.now()
    const now = Date.now()
    if (now - lastIngestLine > 2500) {
      lastIngestLine = now
      const who = d.sender ? ` ${d.sender}` : ''
      const pv = d.preview ? `：${d.preview}` : ''
      pushLog({ ts: new Date().toISOString(), level: 'info', source: 'INGEST', message: `${platformLabel(d.platform)}「${d.group_name}」+${d.count}${who}${pv}` })
    }
  })
  s.on('platform.health', (p) => {
    const ov = live.overview
    if (!ov) return
    const i = ov.platforms.findIndex((x) => x.platform === p.platform)
    if (i >= 0) ov.platforms.splice(i, 1, p)
    else ov.platforms.push(p)
  })
  s.on('overview.dirty', () => refreshOverview())
  s.start()
}

/** 立即出报；运行中再次调用 = 取消（调用方先确认） */
export async function runNow(): Promise<void> {
  const r = await api.createRun({})
  live.run = r
  live.sessionRun = true
  live.taskOverride = {}
}
export async function cancelRun(): Promise<void> {
  if (!live.run) return
  const r = await api.cancelRun(live.run.id)
  live.run = r
}
