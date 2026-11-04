/**
 * 模拟一次完整运行：12 个阶段依次推进（每阶段 0.8~2.5 秒），
 * 逐条推送 run.stage / run.log / delivery.result，最后生成报告（report.created）并 run.finished。
 */
import type { LogDTO, RunCreate, RunDTO, StageDTO } from '@/api/types'
import { STAGES } from '@/utils/meta'
import { broadcast } from './bus'
import { EXTRA_SEEDS, TODAY_SEEDS, buildItems } from './build/items'
import { buildStats } from './build/stats'
import { DELIV_OK, TODAY_JUDGMENTS, assembleReport } from './build/reports'
import { attachV2 } from './build/v2'
import { S } from './state'
import { agentOf, buildPlan } from './stages'
import { DAY, hms, iso, ymd } from './util'

/** 同一时间只有一个运行、一个挂起的 sleep；取消时让它 reject */
let abort: (() => void) | null = null
const sleep = (ms: number, signal: { cancelled: boolean }) =>
  new Promise<void>((resolve, reject) => {
    if (signal.cancelled) { reject(new Error('cancelled')); return }
    const t = setTimeout(() => { abort = null; resolve() }, ms)
    abort = () => { signal.cancelled = true; clearTimeout(t); abort = null; reject(new Error('cancelled')) }
  })

function log(run: RunDTO, stage: StageDTO['name'], level: LogDTO['level'], message: string): void {
  const l: LogDTO = { ts: new Date().toISOString(), level, source: `pipeline.${stage}`, message, run_id: run.id, stage }
  ;(S.runLogs[run.id] ??= []).push(l)
  S.syslog.push(l)
  broadcast('run.log', l)
}

export function startRun(body: RunCreate, trigger: RunDTO['trigger'] = 'manual'): RunDTO {
  const now = Date.now()
  const id = `run-${ymd(now)}-${hms(now).replace(/:/g, '')}`
  const seed = now % 100000
  const stats = buildStats(seed, 1.04)
  const reportId = `rpt-${ymd(now)}-${hms(now).slice(0, 5).replace(':', '')}`
  const items = buildItems(reportId, [...TODAY_SEEDS, ...EXTRA_SEEDS], now, seed % 997, 24, { v2: true })
  const chosen = body.channel_ids?.length ? S.channels.filter((c) => body.channel_ids!.includes(c.id)) : S.channels
  const plan = buildPlan({ stats, items, channels: body.dry_run ? [] : chosen, seed })
  const run: RunDTO = {
    id, trigger, status: 'running', dry_run: !!body.dry_run, window_start: iso(now - (body.window_hours ?? 24) * 3600_000), window_end: iso(now),
    started_at: iso(now), stages: STAGES.map((name) => ({ name, agent: agentOf(name), status: 'pending', metrics: {} })),
    totals: { messages_raw: 0, messages_clean: 0, chunks: 0, candidates: 0, items: 0, tokens_in: 0, tokens_out: 0, cost_cny: 0, llm_provider: String((S.settings.llm as { provider?: string }).provider ?? 'offline') },
  }
  S.current = run
  const signal = { cancelled: false }
  broadcast('run.started', structuredClone(run))
  void (async () => {
    try {
      await sleep(400, signal)
      let tokIn = 0, tokOut = 0
      for (const sc of plan.stages) {
        const st = run.stages.find((s) => s.name === sc.name)!
        const dur = body.dry_run && sc.name === 'deliver' ? 300 : sc.duration
        Object.assign(st, { status: 'running', started_at: new Date().toISOString(), message: sc.message })
        broadcast('run.stage', { run_id: run.id, stage: structuredClone(st) })
        let elapsed = 0
        if (body.dry_run && sc.name === 'deliver') log(run, 'deliver', 'info', '仅预览：跳过投递')
        else for (const l of sc.logs) {
          const at = Math.round(l.at * dur)
          await sleep(Math.max(0, at - elapsed), signal)
          elapsed = at
          log(run, sc.name, l.level ?? 'info', l.text)
          if (l.metrics) { st.metrics = { ...st.metrics, ...l.metrics }; broadcast('run.stage', { run_id: run.id, stage: structuredClone(st) }) }
          if (l.channel) {
            const ch = S.channels.find((c) => c.id === l.channel)!
            const ok = l.level !== 'error'
            ch.last_result = { ok, detail: ok ? '已送达' : 'NapCat 未登录', at: new Date().toISOString() }
            broadcast('delivery.result', { run_id: run.id, report_id: reportId, channel_id: ch.id, channel_name: ch.name, kind: ch.kind, ok, detail: ch.last_result.detail })
          }
        }
        await sleep(Math.max(0, dur - elapsed), signal)
        const skipped = body.dry_run && sc.name === 'deliver'
        Object.assign(st, { status: skipped ? 'skipped' : 'done', finished_at: new Date().toISOString(), duration_ms: dur, metrics: { ...st.metrics, ...sc.final } })
        if (sc.name === 'extract' || sc.name === 'compose') { tokIn += Number(sc.final.tokens_in ?? 0); tokOut += Number(sc.final.tokens_out ?? 0) }
        if (sc.name === 'collect') { run.totals.messages_raw = stats.messages_raw; S.extraMessages += Math.round(stats.messages_raw * 0.06); broadcast('overview.dirty', {}) }
        if (sc.name === 'clean') run.totals.messages_clean = stats.messages_clean
        if (sc.name === 'segment') run.totals.chunks = plan.totals.chunks
        if (sc.name === 'extract') run.totals.candidates = plan.totals.candidates
        run.totals.tokens_in = tokIn; run.totals.tokens_out = tokOut
        run.totals.cost_cny = Math.round(((tokIn * 2 + tokOut * 8) / 1e6) * 100) / 100
        broadcast('run.stage', { run_id: run.id, stage: structuredClone(st) })
        if ((!body.dry_run && sc.name === 'archive') || (body.dry_run && sc.name === 'render')) {
          const hhmm = hms(now).slice(0, 5)
          const rep = attachV2(assembleReport({ id: reportId, runId: run.id, start: now - DAY, end: now, created: Date.now(), stats, items,
            judgments: TODAY_JUDGMENTS, suffix: ` · 加刊 ${hhmm}`, deliveries: body.dry_run ? [] : DELIV_OK.filter((d) => chosen.some((c) => c.id === d.channel_id && c.enabled)) }), now)
          S.reports.unshift(rep)
          run.report_id = rep.id
          broadcast('report.created', { id: rep.id, run_id: rep.run_id, title: rep.title, date_label: rep.date_label, window_label: rep.window_label,
            created_at: rep.created_at, items_total: rep.items_total, headlines: rep.headlines, deliveries: rep.deliveries })
        }
      }
      run.totals.items = items.length
      finish(run, 'success')
      S.tokensToday += tokIn + tokOut
      S.costToday += run.totals.cost_cny
    } catch {
      const st = run.stages.find((s) => s.status === 'running')
      if (st) Object.assign(st, { status: 'skipped', finished_at: new Date().toISOString(), message: '已取消' })
      run.stages.forEach((s) => { if (s.status === 'pending') s.status = 'skipped' })
      if (st) { broadcast('run.stage', { run_id: run.id, stage: structuredClone(st) }); log(run, st.name, 'warn', '收到取消指令，已停止后续阶段') }
      finish(run, 'cancelled')
    }
  })()
  return structuredClone(run)
}

function finish(run: RunDTO, status: RunDTO['status']): void {
  run.status = status
  run.finished_at = new Date().toISOString()
  S.current = null
  S.runs.unshift(structuredClone(run))
  const sch = S.schedules.find((s) => s.id === 'sch-morning')
  if (sch && run.trigger === 'schedule') sch.last_run = { id: run.id, status, finished_at: run.finished_at }
  broadcast('run.finished', structuredClone(run))
  setTimeout(() => broadcast('overview.dirty', {}), 150)
}

export function cancelRun(id: string): RunDTO | null {
  if (!S.current || S.current.id !== id) return null
  const snapshot = structuredClone(S.current)
  abort?.()
  return snapshot
}
