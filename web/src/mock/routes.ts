/** mock 路由（一）：会话、总览、平台、群、导入、定时任务、运行 */
import type { ConfigField, GroupDTO, Platform, ScheduleDTO, ScheduleInput } from '@/api/types'
import { nextRuns, parseCron } from '@/utils/cron'
import { platformDTO } from './build/overview'
import { cancelRun, startRun } from './sim'
import { S, overviewNow } from './state'
import { iso } from './util'

export interface Req { m: RegExpExecArray; q: URLSearchParams; body: unknown }
export interface Res { status: number; body: unknown; filename?: string; contentType?: string }
export type Handler = (r: Req) => Res | Promise<Res>
export type Route = [method: string, pattern: RegExp, handler: Handler]

export const ok = (body: unknown, status = 200): Res => ({ status, body })
export const err = (status: number, code: string, message: string, hint?: string): Res => ({ status, body: { error: { code, message, hint } } })
export const clone = <T>(x: T): T => structuredClone(x)
type RealP = 'wechat' | 'qq' | 'feishu'
const isReal = (p: string): p is RealP => p === 'wechat' || p === 'qq' || p === 'feishu'

export const maskSecret = (v: string) => `••••${v.slice(-4)}`
/** 按 schema 合并配置：secret 字段空串或掩码 = 不修改，其它值存掩码（mock 不保存明文） */
export function mergeConfig(schema: ConfigField[], cur: Record<string, unknown>, next: Record<string, unknown>): Record<string, unknown> {
  const out = { ...cur }
  for (const [k, v] of Object.entries(next)) {
    const f = schema.find((x) => x.key === k)
    if (f?.type === 'secret') {
      if (typeof v === 'string' && v && !v.startsWith('••')) out[k] = maskSecret(v)
    } else out[k] = v
  }
  return out
}

const plat = (p: RealP) => platformDTO(p, S.platforms[p], S.groups, Date.now())

export const ROUTES_A: Route[] = [
  ['GET', /^\/session$/, () => ok({ token: 'mock-token-0000', version: '1.0.0-mock', mode: 'live' })],
  ['GET', /^\/health$/, () => ok({ ok: true, version: '1.0.0-mock' })],
  ['GET', /^\/overview$/, () => ok(overviewNow())],
  ['GET', /^\/platforms$/, () => ok((['wechat', 'qq', 'feishu'] as RealP[]).map(plat))],
  ['PUT', /^\/platforms\/(\w+)$/, ({ m, body }) => {
    const p = m[1]!
    if (!isReal(p)) return err(404, 'not_found', `未知平台：${p}`)
    const b = (body ?? {}) as { enabled?: boolean; adapter?: string; config?: Record<string, unknown> }
    const st = S.platforms[p]
    if (typeof b.enabled === 'boolean') st.enabled = b.enabled
    if (b.adapter) st.adapter = b.adapter
    if (b.config) {
      const ad = plat(p).adapters.find((a) => a.key === st.adapter)
      const src = ((S.settings.sources ??= {}) as Record<string, Record<string, Record<string, unknown>>>)
      const bucket = (src[p] ??= {})
      bucket[st.adapter] = mergeConfig(ad?.config_schema ?? [], bucket[st.adapter] ?? {}, b.config)
    }
    return ok(plat(p))
  }],
  ['POST', /^\/platforms\/(\w+)\/test$/, async ({ m }) => {
    const p = m[1]!
    if (!isReal(p)) return err(404, 'not_found', `未知平台：${p}`)
    await new Promise((r) => setTimeout(r, 700))
    S.platforms[p].checkedMinAgo = 0
    return ok(plat(p))
  }],
  ['POST', /^\/platforms\/(\w+)\/refresh-groups$/, async ({ m }) => {
    const p = m[1]!
    if (!isReal(p)) return err(404, 'not_found', `未知平台：${p}`)
    await new Promise((r) => setTimeout(r, 900))
    if (S.platforms[p].health === 'down') return err(503, 'platform_down', `${p} 当前不可用，无法刷新群列表`, S.platforms[p].hint)
    const total = S.groups.filter((g) => g.platform === p).length
    return ok({ added: 0, updated: total, total })
  }],
  ['GET', /^\/groups$/, ({ q }) => {
    let xs = S.groups
    const p = q.get('platform'), wl = q.get('whitelisted'), kw = q.get('q')?.trim().toLowerCase()
    if (p) xs = xs.filter((g) => g.platform === p)
    if (wl === 'true' || wl === 'false') xs = xs.filter((g) => g.whitelisted === (wl === 'true'))
    if (kw) xs = xs.filter((g) => `${g.name} ${g.alias ?? ''} ${g.native_id} ${g.tags.join(' ')}`.toLowerCase().includes(kw))
    xs = [...xs].sort((a, b) => Number(b.whitelisted) - Number(a.whitelisted) || b.messages_24h - a.messages_24h)
    const off = Number(q.get('offset') ?? 0), lim = Number(q.get('limit') ?? 200)
    return ok({ items: clone(xs.slice(off, off + lim)), total: xs.length })
  }],
  ['PATCH', /^\/groups\/(.+)$/, ({ m, body }) => {
    const key = decodeURIComponent(m[1]!)
    const g = S.groups.find((x) => x.key === key)
    if (!g) return err(404, 'not_found', '群不存在')
    const b = (body ?? {}) as Partial<GroupDTO>
    if (typeof b.whitelisted === 'boolean') g.whitelisted = b.whitelisted
    if (typeof b.weight === 'number') g.weight = Math.max(0, Math.min(3, Math.round(b.weight * 10) / 10))
    if (typeof b.alias === 'string') g.alias = b.alias.trim() || undefined
    if (Array.isArray(b.tags)) g.tags = b.tags.map(String).slice(0, 12)
    return ok(clone(g))
  }],
  ['POST', /^\/groups\/bulk$/, ({ body }) => {
    const b = (body ?? {}) as { keys?: string[]; whitelisted?: boolean }
    let n = 0
    for (const g of S.groups) if (b.keys?.includes(g.key) && g.whitelisted !== b.whitelisted) { g.whitelisted = !!b.whitelisted; n++ }
    return ok({ updated: n })
  }],
  ['POST', /^\/import$/, async ({ body }) => {
    const fd = body instanceof FormData ? body : new FormData()
    const file = fd.get('file'), text = String(fd.get('text') ?? '')
    const platform = String(fd.get('platform') ?? 'wechat') as Platform
    const content = file instanceof File ? await file.text() : text
    if (!content.trim()) return err(400, 'empty', '没有收到文件或文本', '拖入导出文件，或在文本框里粘贴聊天记录')
    const fname = file instanceof File ? file.name : ''
    const name = String(fd.get('group_name') ?? '').trim() || fname.replace(/\.[^.]+$/, '') || '导入的群'
    const format = /\.json$/i.test(fname) ? (content.includes('"messages"') ? 'wda_json' : 'chatlab') : /\.csv$/i.test(fname) ? 'csv' : 'pasted_text'
    const lines = content.split(/\r?\n/).filter((l) => l.trim()).length
    const imported = format === 'pasted_text' ? Math.max(1, Math.round(lines / 3)) : Math.max(1, lines - 1)
    const g: GroupDTO = { key: `${platform}:import-${Date.now().toString(36)}`, platform, native_id: `import-${Date.now().toString(36)}`, name, whitelisted: true, weight: 1,
      tags: ['导入'], messages_24h: 0, messages_7d: imported, last_message_at: iso(Date.now() - 3600_000), last_collect_at: iso(Date.now()) }
    S.groups.push(g)
    const warnings = format === 'pasted_text' ? [`有 ${Math.round(imported * 0.05)} 行无法识别发言人，已跳过`] : []
    if (!String(fd.get('group_name') ?? '').trim()) warnings.push(`未填写群名，已使用「${name}」`)
    return ok({ group: clone(g), imported, skipped: Math.round(imported * 0.05), format, warnings })
  }],
  ['GET', /^\/schedules$/, () => ok(clone(S.schedules))],
  ['POST', /^\/schedules$/, ({ body }) => saveSchedule(null, body as ScheduleInput)],
  ['PUT', /^\/schedules\/([\w-]+)$/, ({ m, body }) => saveSchedule(m[1]!, body as ScheduleInput)],
  ['DELETE', /^\/schedules\/([\w-]+)$/, ({ m }) => {
    const i = S.schedules.findIndex((s) => s.id === m[1])
    if (i < 0) return err(404, 'not_found', '定时任务不存在')
    S.schedules.splice(i, 1)
    return ok({ ok: true })
  }],
  ['POST', /^\/schedules\/([\w-]+)\/run$/, ({ m, body }) => {
    const sch = S.schedules.find((s) => s.id === m[1])
    if (!sch) return err(404, 'not_found', '定时任务不存在')
    if (S.current) return err(409, 'run_in_progress', '已有一次运行正在进行', '等当前运行结束，或先取消它')
    const dry = (body as { dry_run?: boolean } | null)?.dry_run ?? sch.dry_run
    return ok(startRun({ platforms: sch.platforms, channel_ids: sch.channel_ids, window_hours: sch.window_hours, dry_run: dry }, 'schedule'), 202)
  }],
  ['POST', /^\/runs$/, ({ body }) => {
    if (S.current) return err(409, 'run_in_progress', '已有一次运行正在进行', '等当前运行结束，或先取消它')
    return ok(startRun((body ?? {}) as Parameters<typeof startRun>[0]), 202)
  }],
  ['GET', /^\/runs$/, ({ q }) => {
    const lim = Number(q.get('limit') ?? 20), off = Number(q.get('offset') ?? 0)
    const all = S.current ? [S.current, ...S.runs] : S.runs
    return ok({ items: clone(all.slice(off, off + lim)), total: all.length })
  }],
  ['GET', /^\/runs\/([\w-]+)$/, ({ m }) => {
    const r = S.current?.id === m[1] ? S.current : S.runs.find((x) => x.id === m[1])
    return r ? ok(clone(r)) : err(404, 'not_found', '运行记录不存在')
  }],
  ['POST', /^\/runs\/([\w-]+)\/cancel$/, ({ m }) => {
    const r = cancelRun(m[1]!)
    return r ? ok(r) : err(409, 'not_running', '这次运行已经结束，无法取消')
  }],
  ['GET', /^\/runs\/([\w-]+)\/logs$/, ({ m }) => ok(clone(S.runLogs[m[1]!] ?? []))],
]

function saveSchedule(id: string | null, b: ScheduleInput): ReturnType<Handler> {
  if (!b || !b.name?.trim()) return err(422, 'validation', '请填写任务名称')
  const pc = parseCron(b.cron ?? '')
  if (!pc.ok) return err(422, 'invalid_cron', `cron 表达式无效：${pc.error}`, '格式为「分 时 日 月 周」，例如 0 8 * * *')
  const next = nextRuns(b.cron, 1, b.timezone || 'Asia/Shanghai')[0]?.toISOString()
  if (id) {
    const s = S.schedules.find((x) => x.id === id)
    if (!s) return err(404, 'not_found', '定时任务不存在')
    Object.assign(s, b, { id, next_run_at: next })
    return ok(clone(s))
  }
  const s: ScheduleDTO = { ...b, id: `sch-${Date.now().toString(36)}`, next_run_at: next }
  S.schedules.push(s)
  return ok(clone(s), 201)
}
