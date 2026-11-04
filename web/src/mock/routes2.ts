/** mock 路由（二）：报告、情报、通道、设置、模型、提示词、日志、体检、演示数据 */
import type { ChannelDTO, ContextMsg, LogDTO, ReportDTO } from '@/api/types'
import { deepMerge } from '@/api/settingsPaths'
import { escapeHtml } from '@/utils/markdown'
import { SPEAKERS } from './data/groups'
import { DOCTOR } from './fixtures/misc'
import { CHANNEL_KINDS, S } from './state'
import { clone, err, maskSecret, mergeConfig, ok, type Route } from './routes'
import { iso, pick, rng } from './util'

const summary = (r: ReportDTO) => ({ id: r.id, run_id: r.run_id, title: r.title, date_label: r.date_label, window_label: r.window_label,
  created_at: r.created_at, items_total: r.items_total, headlines: r.headlines, deliveries: r.deliveries })

const CHATTER = ['有人试过吗', '我晚上回去试一下', '这个靠谱', '收藏了', '有链接吗', '同问', '我们组也在用', '确实，昨天刚踩坑', '先 mark', '细说', '这个思路不错', '价格多少']
const SECRET_KEY = /(key|token|secret|password|sendkey|spt)$/i

function maskDeep(cur: Record<string, unknown>, next: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(next)) {
    if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = maskDeep((cur[k] ?? {}) as Record<string, unknown>, v as Record<string, unknown>)
    else if (SECRET_KEY.test(k) && typeof v === 'string') { if (v && !v.startsWith('••')) out[k] = maskSecret(v) }
    else out[k] = v
  }
  return out
}

export const ROUTES_B: Route[] = [
  ['GET', /^\/reports$/, ({ q }) => {
    const kw = q.get('q')?.trim()
    let xs = S.reports
    if (kw) xs = xs.filter((r) => r.title.includes(kw) || r.items.some((i) => i.title.includes(kw) || i.tags.some((t) => t.includes(kw))))
    const off = Number(q.get('offset') ?? 0), lim = Number(q.get('limit') ?? 20)
    return ok({ items: xs.slice(off, off + lim).map(summary), total: xs.length })
  }],
  ['GET', /^\/reports\/([\w-]+)$/, ({ m }) => {
    const r = S.reports.find((x) => x.id === m[1])
    return r ? ok(clone(r)) : err(404, 'not_found', '报告不存在')
  }],
  ['GET', /^\/reports\/([\w-]+)\/export$/, ({ m, q }) => {
    const r = S.reports.find((x) => x.id === m[1])
    if (!r) return err(404, 'not_found', '报告不存在')
    const fmt = q.get('format') ?? 'md'
    const base = `情报局-每日风向标-${r.id.replace(/^rpt-/, '')}`
    if (fmt === 'json') return { status: 200, body: JSON.stringify(r, null, 2), filename: `${base}.json`, contentType: 'application/json;charset=utf-8' }
    if (fmt === 'html') {
      const html = `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>${escapeHtml(r.title)}</title><body style="background:#03060f;color:#eaf6ff;font:15px/1.8 'Microsoft YaHei',sans-serif;max-width:860px;margin:40px auto"><pre style="white-space:pre-wrap">${escapeHtml(r.full_md)}</pre></body></html>`
      return { status: 200, body: html, filename: `${base}.html`, contentType: 'text/html;charset=utf-8' }
    }
    return { status: 200, body: r.full_md, filename: `${base}.md`, contentType: 'text/markdown;charset=utf-8' }
  }],
  ['POST', /^\/reports\/([\w-]+)\/deliver$/, async ({ m, body }) => {
    const r = S.reports.find((x) => x.id === m[1])
    if (!r) return err(404, 'not_found', '报告不存在')
    const ids = ((body ?? {}) as { channel_ids?: string[] }).channel_ids ?? []
    if (!ids.length) return err(422, 'validation', '请至少选择一个通道')
    await new Promise((res) => setTimeout(res, 900))
    const results = ids.map((id) => {
      const ch = S.channels.find((c) => c.id === id)
      const okk = !!ch && ch.enabled
      const detail = !ch ? '通道不存在' : !ch.enabled ? '通道未启用' : '已重新投递'
      if (ch) ch.last_result = { ok: okk, detail, at: new Date().toISOString() }
      return { channel_id: id, ok: okk, detail }
    })
    return ok({ results })
  }],
  ['GET', /^\/items\/([\w-]+)$/, ({ m }) => {
    for (const r of S.reports) {
      const it = r.items.find((i) => i.id === m[1])
      if (!it) continue
      const rr = rng(it.id.length * 31 + it.rank)
      const t0 = new Date(it.evidence[0]?.sent_at ?? r.created_at).getTime()
      const mk = (d: number): ContextMsg => ({ message_id: `m${Math.floor(rr() * 90000)}`, sender: pick(rr, SPEAKERS), sent_at: iso(t0 + d * 60_000), text: pick(rr, CHATTER), group_name: it.evidence[0]?.group_name })
      return ok({ ...clone(it), context: { before: [-9, -7, -5, -3, -1].map(mk), after: [1, 2, 4, 6, 9].map(mk) } })
    }
    return err(404, 'not_found', '情报不存在')
  }],
  ['GET', /^\/channel-kinds$/, () => ok(clone(CHANNEL_KINDS))],
  ['GET', /^\/channels$/, () => ok(clone(S.channels))],
  ['POST', /^\/channels$/, ({ body }) => {
    const b = (body ?? {}) as Partial<ChannelDTO>
    const kind = CHANNEL_KINDS.find((k) => k.kind === b.kind)
    if (!kind) return err(422, 'validation', '未知的通道类型')
    if (!b.name?.trim()) return err(422, 'validation', '请填写通道名称')
    const miss = kind.config_schema.find((f) => f.required && !(b.config ?? {})[f.key] && (b.config ?? {})[f.key] !== 0)
    if (miss) return err(422, 'validation', `缺少必填项：${miss.label}`)
    const ch: ChannelDTO = { id: `ch-${Date.now().toString(36)}`, kind: kind.kind, name: b.name.trim(), enabled: b.enabled !== false, config: mergeConfig(kind.config_schema, {}, b.config ?? {}) }
    S.channels.push(ch)
    return ok(clone(ch), 201)
  }],
  ['PUT', /^\/channels\/([\w-]+)$/, ({ m, body }) => {
    const ch = S.channels.find((c) => c.id === m[1])
    if (!ch) return err(404, 'not_found', '通道不存在')
    const b = (body ?? {}) as Partial<ChannelDTO>
    const kind = CHANNEL_KINDS.find((k) => k.kind === ch.kind)
    if (typeof b.name === 'string' && b.name.trim()) ch.name = b.name.trim()
    if (typeof b.enabled === 'boolean') ch.enabled = b.enabled
    if (b.config) ch.config = mergeConfig(kind?.config_schema ?? [], ch.config, b.config)
    return ok(clone(ch))
  }],
  ['DELETE', /^\/channels\/([\w-]+)$/, ({ m }) => {
    const i = S.channels.findIndex((c) => c.id === m[1])
    if (i < 0) return err(404, 'not_found', '通道不存在')
    if (S.channels[i]!.kind === 'local_archive') return err(409, 'protected', '本地归档是兜底通道，不能删除', '不需要时可以停用')
    S.channels.splice(i, 1)
    return ok({ ok: true })
  }],
  ['POST', /^\/channels\/([\w-]+)\/test$/, async ({ m }) => {
    const ch = S.channels.find((c) => c.id === m[1])
    if (!ch) return err(404, 'not_found', '通道不存在')
    await new Promise((res) => setTimeout(res, 800))
    const okk = ch.enabled || ch.kind !== 'email_smtp'
    const detail = okk ? '测试消息已发送，请到对应客户端确认' : 'SMTP 登录失败：授权码错误（535）'
    ch.last_result = { ok: okk, detail, at: new Date().toISOString() }
    return ok({ ok: okk, detail })
  }],
  ['GET', /^\/settings$/, () => ok(clone(S.settings))],
  ['PUT', /^\/settings$/, ({ body }) => {
    const patch = maskDeep(S.settings as unknown as Record<string, unknown>, (body ?? {}) as Record<string, unknown>)
    deepMerge(S.settings as unknown as Record<string, unknown>, patch)
    return ok(clone(S.settings))
  }],
  ['POST', /^\/llm\/test$/, async () => {
    const consent = (S.settings.privacy as { cloud_llm_consent?: boolean }).cloud_llm_consent
    const provider = String((S.settings.llm as { provider?: string }).provider ?? 'offline')
    await new Promise((res) => setTimeout(res, 1100))
    if (!consent && provider !== 'offline') return ok({ ok: false, provider, model: '', latency_ms: 0, detail: '未开启云端同意，已退回离线规则；开启后才会调用云端模型' })
    return ok({ ok: true, provider, model: String((S.settings.llm as { model?: string }).model ?? ''), latency_ms: 780 + Math.round(Math.random() * 200), detail: '最小调用成功，返回 JSON 校验通过' })
  }],
  ['GET', /^\/prompts$/, () => ok(clone(S.prompts))],
  ['PUT', /^\/prompts\/(\w+)$/, ({ m, body }) => {
    const p = S.prompts.find((x) => x.name === m[1])
    if (!p) return err(404, 'not_found', '提示词模板不存在')
    const content = String(((body ?? {}) as { content?: unknown }).content ?? '')
    if (content.trim().length < 20) return err(422, 'validation', '提示词太短（至少 20 字）')
    p.content = content
    return ok(clone(p))
  }],
  ['GET', /^\/logs$/, ({ q }) => {
    const rank: Record<LogDTO['level'], number> = { debug: 0, info: 1, warn: 2, error: 3 }
    const lv = (q.get('level') ?? 'debug') as LogDTO['level']
    const lim = Number(q.get('limit') ?? 200)
    const xs = S.syslog.filter((l) => rank[l.level] >= (rank[lv] ?? 0))
    return ok(clone(xs.slice(-lim)))
  }],
  ['GET', /^\/doctor$/, async () => {
    await new Promise((res) => setTimeout(res, 600))
    const consent = (S.settings.privacy as { cloud_llm_consent?: boolean }).cloud_llm_consent
    return ok(DOCTOR.map((d) => (d.id === 'consent' && !consent ? { ...d, status: 'unconfigured' as const, detail: '未同意云端模型：大模型阶段改用离线规则提取', hint: '在「智能体」页开启云端同意' } : d)))
  }],
  ['POST', /^\/demo\/seed$/, async () => {
    await new Promise((res) => setTimeout(res, 1200))
    S.demoSeeded = true
    return ok({ groups: 9, messages: 18742 })
  }],
  ['POST', /^\/demo\/clear$/, () => { S.demoSeeded = false; return ok({ ok: true }) }],
]
