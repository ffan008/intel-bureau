/** 从 RunDTO 的阶段推导 8 个 Agent 的状态、任务、指标 */
import type { AgentCode, AgentDTO, RunDTO, StageDTO, StageStatus } from '@/api/types'
import { AGENTS, STAGE_LABEL } from './meta'
import { fmtInt, fmtPct } from './format'

export interface AgentView { code: AgentCode; name: string; status: StageStatus; task: string; metric: string; stages: StageDTO[] }

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : typeof v === 'string' && v.trim() !== '' && Number.isFinite(+v) ? +v : null)

/** 某个前缀的数值指标求和，比如 collect 的 msgs_wechat / msgs_qq / msgs_feishu */
const sumPrefix = (m: Record<string, number | string>, prefix: string): number | null => {
  const vs = Object.entries(m).filter(([k]) => k.startsWith(prefix)).map(([, v]) => num(v)).filter((v): v is number => v !== null)
  return vs.length ? vs.reduce((a, b) => a + b, 0) : null
}

/**
 * 指标文案。键名以后端 bureau/pipeline/* 的 StageResult.metrics 为准，同时兼容 mock 的建议键；未知键时退回通用格式。
 * collect: msgs_<平台> · clean: raw, clean, snr · stats: speakers, keywords, rising · segment: threads, chunks
 * extract: chunks_done, chunks, candidates · merge: topics · score: items, new, developing, repeat
 * verify: evidence_checked, evidence_valid, items_dropped · compose: judgments, features · render: full_md_chars, headlines
 * deliver: channels, ok, failed, dry_run · archive: report_id
 */
const METRIC: Record<AgentCode, (m: Record<string, number | string>) => string | null> = {
  SCOUT: (m) => {
    const n = num(m.messages) ?? sumPrefix(m, 'msgs_')
    return n !== null ? `已采集 ${fmtInt(n)} 条` : null
  },
  SWEEPER: (m) => {
    const c = num(m.messages_clean) ?? num(m.clean)
    return c !== null ? `有效 ${fmtInt(c)} 条${num(m.snr) !== null ? ` · 信噪比 ${fmtPct(num(m.snr)!)}` : ''}` : null
  },
  ANALYST: (m) => num(m.chunks) !== null ? `线程 ${fmtInt(num(m.threads) ?? 0)} · 块 ${fmtInt(num(m.chunks))}`
    : num(m.keywords) !== null ? `关键词 ${fmtInt(num(m.keywords))} · 上升 ${fmtInt(num(m.rising) ?? 0)}` : null,
  DECODER: (m) => num(m.candidates) !== null
    ? `${num(m.chunks) ? `块 ${fmtInt(num(m.chunks_done) ?? num(m.chunks))}/${fmtInt(num(m.chunks))} · ` : ''}候选 ${fmtInt(num(m.candidates))} 条` : null,
  STRATEGIST: (m) => num(m.headlines) !== null ? `头条 ${num(m.headlines)} · 专题 ${num(m.features) ?? 0}`
    : num(m.items) !== null ? `情报 ${fmtInt(num(m.items))} 条 · 新 ${fmtInt(num(m.new) ?? 0)}`
    : num(m.topics) !== null ? `合并为 ${fmtInt(num(m.topics))} 个话题` : null,
  AUDITOR: (m) => num(m.evidence_valid) !== null
    ? `证据 ${fmtInt(num(m.evidence_valid))}/${fmtInt(num(m.evidence_checked) ?? 0)} 有效${num(m.items_dropped) ? ` · 剔除 ${num(m.items_dropped)}` : ''}`
    : num(m.passed) !== null ? `通过 ${num(m.passed)} · 剔除 ${num(m.dropped) ?? 0}` : null,
  WRITER: (m) => num(m.full_md_chars) !== null ? `报告 ${fmtInt(num(m.full_md_chars))} 字 · 风向 ${fmtInt(num(m.judgments) ?? 0)} 条`
    : num(m.judgments) !== null ? `风向 ${fmtInt(num(m.judgments))} 条 · 专题 ${fmtInt(num(m.features) ?? 0)}`
    : num(m.bytes) !== null ? `报告 ${(num(m.bytes)! / 1024).toFixed(1)} KB`
    : num(m.tokens_out) !== null ? `输出 ${fmtInt(num(m.tokens_out))} tokens` : null,
  COURIER: (m) => num(m.delivered) !== null ? `投递 ${num(m.delivered)} 成功${num(m.failed) ? ` · ${num(m.failed)} 失败` : ''}`
    : num(m.dry_run) ? '仅预览 · 已归档'
    : num(m.channels) !== null ? `投递 ${fmtInt(num(m.ok) ?? 0)}/${fmtInt(num(m.channels))}${num(m.failed) ? ` · ${num(m.failed)} 失败` : ''}` : null,
}

function genericMetric(m: Record<string, number | string>): string {
  const first = Object.entries(m).find(([, v]) => v !== '' && v !== null && v !== undefined)
  if (!first) return '—'
  const [k, v] = first
  return `${k} ${typeof v === 'number' ? fmtInt(v) : v}`
}

export function agentStatus(stages: StageDTO[]): StageStatus {
  if (!stages.length) return 'pending'
  if (stages.some((s) => s.status === 'failed')) return 'failed'
  if (stages.some((s) => s.status === 'running')) return 'running'
  if (stages.every((s) => s.status === 'done' || s.status === 'skipped')) return stages.every((s) => s.status === 'skipped') ? 'skipped' : 'done'
  if (stages.some((s) => s.status === 'done')) return 'running' // 一个阶段完成、下一个还没开始：仍算执行中
  return 'pending'
}

export function agentsFromRun(run: RunDTO, taskOverride: Partial<Record<AgentCode, string>> = {}): AgentView[] {
  return AGENTS.map((a) => {
    const stages = a.stages.map((n) => run.stages.find((s) => s.name === n)).filter((s): s is StageDTO => !!s)
    const status = agentStatus(stages)
    const merged: Record<string, number | string> = Object.assign({}, ...stages.map((s) => s.metrics ?? {}))
    const active = [...stages].reverse().find((s) => s.status !== 'pending')
    const task = taskOverride[a.code]
      ?? active?.message
      ?? (status === 'pending' ? `待命 · 等待${STAGE_LABEL[a.stages[0]!]}` : a.role)
    const metric = Object.keys(merged).length ? METRIC[a.code](merged) ?? genericMetric(merged) : '—'
    return { code: a.code, name: a.name, status, task, metric, stages }
  })
}

export function agentsFromOverview(list: AgentDTO[] | undefined): AgentView[] {
  return AGENTS.map((a) => {
    const o = list?.find((x) => x.code === a.code)
    return { code: a.code, name: o?.name || a.name, status: o?.status ?? 'pending', task: o?.task || a.role, metric: o?.metric || '—', stages: [] }
  })
}

/** 完成阶段数 / 12 */
export function runProgress(run?: RunDTO | null): number {
  if (!run || !run.stages.length) return 0
  const done = run.stages.filter((s) => s.status === 'done' || s.status === 'skipped' || s.status === 'failed').length
  return done / Math.max(12, run.stages.length)
}

export const isActive = (run?: RunDTO | null): boolean => !!run && (run.status === 'running' || run.status === 'queued')
