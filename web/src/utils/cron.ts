/**
 * 5 段 crontab：分 时 日 月 周。解析、翻译成人话、预测下次运行。
 * 「周」按标准 cron 解释（0/7=周日，1=周一）。后端 scheduler.make_trigger 会把它换算成 APScheduler 的写法，
 * 前后端含义一致。后端不接受「日」和「周」同时限定的写法（两者在标准 cron 里是"或"，容易误解）。
 */
const DOW_NAMES = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat']
const DOW_CN = ['日', '一', '二', '三', '四', '五', '六']
const FIELDS = [
  { name: '分钟', min: 0, max: 59 },
  { name: '小时', min: 0, max: 23 },
  { name: '日期', min: 1, max: 31 },
  { name: '月份', min: 1, max: 12 },
  { name: '星期', min: 0, max: 7 },
] as const

export interface CronField { values: number[]; star: boolean; step?: number }
export interface CronSpec { minute: CronField; hour: CronField; dom: CronField; month: CronField; dow: CronField }
export type CronParse = { ok: true; spec: CronSpec } | { ok: false; error: string }

function parseField(src: string, idx: number): CronField | string {
  const f = FIELDS[idx]!
  const out = new Set<number>()
  let star = false
  let step: number | undefined
  for (const partRaw of src.toLowerCase().split(',')) {
    const part = idx === 4 ? partRaw.replace(/[a-z]{3}/g, (n) => String(DOW_NAMES.indexOf(n))) : partRaw
    const m = /^(\*|\d+)(?:-(\d+))?(?:\/(\d+))?$/.exec(part)
    if (!m) return `第 ${idx + 1} 段（${f.name}）格式不对：「${partRaw}」`
    const s = m[3] ? +m[3] : 1
    if (s < 1) return `第 ${idx + 1} 段（${f.name}）步长必须 ≥ 1`
    let lo: number, hi: number
    if (m[1] === '*') { lo = f.min; hi = idx === 4 ? 6 : f.max; if (!m[3]) star = true; else step = s }
    else { lo = +m[1]!; hi = m[2] ? +m[2] : m[3] ? f.max : lo }
    if (lo < f.min || hi > f.max || lo > hi) return `第 ${idx + 1} 段（${f.name}）取值范围是 ${f.min}~${f.max}`
    for (let v = lo; v <= hi; v += s) out.add(idx === 4 && v === 7 ? 0 : v)
  }
  return { values: [...out].sort((a, b) => a - b), star, step }
}

export function parseCron(expr: string): CronParse {
  const parts = expr.trim().split(/\s+/)
  if (parts.length !== 5) return { ok: false, error: `需要 5 段（分 时 日 月 周），现在是 ${parts.length} 段` }
  const fields: CronField[] = []
  for (let i = 0; i < 5; i++) {
    const r = parseField(parts[i]!, i)
    if (typeof r === 'string') return { ok: false, error: r }
    fields.push(r)
  }
  const [minute, hour, dom, month, dow] = fields as [CronField, CronField, CronField, CronField, CronField]
  return { ok: true, spec: { minute, hour, dom, month, dow } }
}

const p2 = (n: number) => String(n).padStart(2, '0')
const joinCn = (xs: string[]) => (xs.length <= 1 ? xs.join('') : xs.slice(0, -1).join('、') + ' 和 ' + xs[xs.length - 1])

function dayPhrase(s: CronSpec): string {
  const months = s.month.star ? '' : `${s.month.values.join('、')} 月`
  let days: string
  const d = s.dow.values.join(',')
  if (s.dom.star && s.dow.star) days = '每天'
  else if (s.dom.star) days = d === '1,2,3,4,5' ? '工作日（周一至周五）' : d === '0,6' ? '周末' : `每周${s.dow.values.map((v) => DOW_CN[v]).join('、')}`
  else if (s.dow.star) days = `每月 ${s.dom.values.join('、')} 日`
  else days = `每月 ${s.dom.values.join('、')} 日及每周${s.dow.values.map((v) => DOW_CN[v]).join('、')}`
  return months ? `${months}${days.replace(/^每/, '的每')}` : days
}

export function describeCron(expr: string): string {
  const r = parseCron(expr)
  if (!r.ok) return `无法解析：${r.error}`
  const s = r.spec
  const day = dayPhrase(s)
  if (s.hour.star && s.minute.step) return `${day}每 ${s.minute.step} 分钟一次`
  if (s.hour.star && s.minute.star) return `${day}每分钟一次`
  if (s.hour.star) return `${day}每小时的第 ${s.minute.values.join('、')} 分`
  if (s.hour.step && s.minute.values.length === 1) return `${day}每 ${s.hour.step} 小时一次（第 ${s.minute.values[0]} 分）`
  const combos = s.hour.values.length * s.minute.values.length
  if (combos <= 6) {
    const times = s.hour.values.flatMap((h) => s.minute.values.map((m) => `${p2(h)}:${p2(m)}`))
    return `${day} ${joinCn(times)}`
  }
  return `${day}，${s.hour.values.length} 个小时 × ${s.minute.values.length} 个分钟点，共 ${combos} 次`
}

function tzOffsetMs(utcMs: number, tz: string): number {
  const f = new Intl.DateTimeFormat('en-US', { timeZone: tz, hourCycle: 'h23', year: 'numeric', month: 'numeric', day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric' })
  const p: Record<string, number> = {}
  for (const x of f.formatToParts(new Date(utcMs))) if (x.type !== 'literal') p[x.type] = +x.value
  return Date.UTC(p.year!, p.month! - 1, p.day!, p.hour! % 24, p.minute!, p.second!) - utcMs
}
function zonedToUtc(y: number, mo: number, d: number, h: number, mi: number, tz: string): number {
  const guess = Date.UTC(y, mo - 1, d, h, mi)
  const off = tzOffsetMs(guess, tz)
  const t = guess - off
  const off2 = tzOffsetMs(t, tz)
  return off2 === off ? t : guess - off2
}

/** 接下来 n 次运行时间（最多向后找 400 天） */
export function nextRuns(expr: string, n = 3, tz = 'Asia/Shanghai', from = Date.now()): Date[] {
  const r = parseCron(expr)
  if (!r.ok) return []
  const s = r.spec
  const out: Date[] = []
  const start = new Date(from + tzOffsetMs(from, tz))
  const y0 = start.getUTCFullYear(), m0 = start.getUTCMonth(), d0 = start.getUTCDate()
  for (let i = 0; i < 400 && out.length < n; i++) {
    const day = new Date(Date.UTC(y0, m0, d0 + i))
    const y = day.getUTCFullYear(), mo = day.getUTCMonth() + 1, d = day.getUTCDate(), wd = day.getUTCDay()
    if (!s.month.values.includes(mo)) continue
    const domOk = s.dom.values.includes(d), dowOk = s.dow.values.includes(wd)
    const match = s.dom.star && s.dow.star ? true : s.dom.star ? dowOk : s.dow.star ? domOk : domOk || dowOk
    if (!match) continue
    for (const h of s.hour.values) for (const mi of s.minute.values) {
      const t = zonedToUtc(y, mo, d, h, mi, tz)
      if (t > from && out.length < n) out.push(new Date(t))
    }
  }
  return out
}

export const CRON_PRESETS = [
  { key: 'daily8', label: '每天 08:00', cron: '0 8 * * *' },
  { key: 'twice', label: '每天 12:00 和 20:00', cron: '0 12,20 * * *' },
  { key: 'workday9', label: '工作日 09:00', cron: '0 9 * * mon-fri' },
] as const
