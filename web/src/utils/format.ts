/** 数字与时间格式化。时间一律按 Asia/Shanghai 展示。 */
export const TZ = 'Asia/Shanghai'

const intFmt = new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 })
export const fmtInt = (n: number | null | undefined): string =>
  n === null || n === undefined || !Number.isFinite(n) ? '—' : intFmt.format(Math.round(n))

export function fmtCompact(n: number): string {
  if (!Number.isFinite(n)) return '—'
  if (Math.abs(n) >= 1e8) return (n / 1e8).toFixed(1).replace(/\.0$/, '') + '亿'
  if (Math.abs(n) >= 1e4) return (n / 1e4).toFixed(1).replace(/\.0$/, '') + '万'
  return fmtInt(n)
}

/** 比例统一成 0~100：snr 可能是 0.417 也可能是 41.7 */
export const toPercent = (v: number): number => (Math.abs(v) <= 1 ? v * 100 : v)
export const fmtPct = (v: number, digits = 1): string => (Number.isFinite(v) ? toPercent(v).toFixed(digits) + '%' : '—')

/**
 * *_delta 的含义 API.md 没有写死：整数按「绝对差值」，带小数且在 (-1,1) 内按「比率」。
 */
export function fmtDelta(d: number | undefined | null): { text: string; dir: 'up' | 'down' | 'flat' } | null {
  if (d === undefined || d === null || !Number.isFinite(d)) return null
  const dir = d > 0 ? 'up' : d < 0 ? 'down' : 'flat'
  const ratio = !Number.isInteger(d) && Math.abs(d) < 1
  const abs = Math.abs(d)
  const text = ratio ? (abs * 100).toFixed(1) + '%' : fmtInt(abs)
  return { text, dir }
}

export const fmtCny = (v: number, digits = 2): string => (Number.isFinite(v) ? '¥' + v.toFixed(digits) : '—')

export function fmtDuration(ms?: number | null): string {
  if (ms === undefined || ms === null || !Number.isFinite(ms)) return '—'
  if (ms < 1000) return `${Math.round(ms)}ms`
  const s = ms / 1000
  if (s < 60) return `${s.toFixed(s < 10 ? 1 : 0)}s`
  const m = Math.floor(s / 60)
  return `${m}m${String(Math.round(s % 60)).padStart(2, '0')}s`
}

const partsFmt = new Intl.DateTimeFormat('en-US', {
  timeZone: TZ, hourCycle: 'h23', year: 'numeric', month: '2-digit', day: '2-digit',
  hour: '2-digit', minute: '2-digit', second: '2-digit', weekday: 'short',
})
const WD: Record<string, number> = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 }
export const WEEK_CN = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

export interface ZonedParts { y: number; mo: number; d: number; h: number; mi: number; s: number; wd: number }
export function zoned(input: string | number | Date): ZonedParts | null {
  const dt = input instanceof Date ? input : new Date(input)
  if (Number.isNaN(dt.getTime())) return null
  const p: Record<string, string> = {}
  for (const x of partsFmt.formatToParts(dt)) p[x.type] = x.value
  return { y: +p.year!, mo: +p.month!, d: +p.day!, h: +p.hour! % 24, mi: +p.minute!, s: +p.second!, wd: WD[p.weekday!] ?? 0 }
}

const p2 = (n: number) => String(n).padStart(2, '0')
export function fmtTime(input?: string | number | Date | null, withSec = true): string {
  const z = input ? zoned(input) : null
  if (!z) return '--:--'
  return withSec ? `${p2(z.h)}:${p2(z.mi)}:${p2(z.s)}` : `${p2(z.h)}:${p2(z.mi)}`
}
export function fmtDate(input?: string | number | Date | null): string {
  const z = input ? zoned(input) : null
  return z ? `${z.y}-${p2(z.mo)}-${p2(z.d)}` : '—'
}
export function fmtMD(input?: string | number | Date | null): string {
  const z = input ? zoned(input) : null
  return z ? `${p2(z.mo)}-${p2(z.d)}` : '—'
}
export function fmtDateTime(input?: string | number | Date | null, withSec = false): string {
  const z = input ? zoned(input) : null
  if (!z) return '—'
  return `${z.y}-${p2(z.mo)}-${p2(z.d)} ${p2(z.h)}:${p2(z.mi)}${withSec ? ':' + p2(z.s) : ''}`
}
export function fmtShort(input?: string | number | Date | null): string {
  const z = input ? zoned(input) : null
  return z ? `${p2(z.mo)}-${p2(z.d)} ${p2(z.h)}:${p2(z.mi)}` : '—'
}

export function fmtAgo(input?: string | null, now = Date.now()): string {
  if (!input) return '—'
  const t = new Date(input).getTime()
  if (Number.isNaN(t)) return '—'
  const s = Math.round((now - t) / 1000)
  if (s < 0) return fmtShort(input)
  if (s < 60) return '刚刚'
  if (s < 3600) return `${Math.floor(s / 60)} 分钟前`
  if (s < 86400) return `${Math.floor(s / 3600)} 小时前`
  if (s < 86400 * 7) return `${Math.floor(s / 86400)} 天前`
  return fmtDate(input)
}

/** 倒计时 HH:MM:SS（超过 99 小时显示天数） */
export function fmtCountdown(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '00:00:00'
  const total = Math.floor(ms / 1000)
  const h = Math.floor(total / 3600)
  if (h > 99) return `${Math.floor(h / 24)}天${p2(h % 24)}时`
  return `${p2(h)}:${p2(Math.floor((total % 3600) / 60))}:${p2(total % 60)}`
}

export function hashStr(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619)
  return h >>> 0
}
