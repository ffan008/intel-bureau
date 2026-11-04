/** mock 工具：固定种子随机数、东八区时间 */
export function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
export const pick = <T>(r: () => number, xs: readonly T[]): T => xs[Math.floor(r() * xs.length)]!
export const between = (r: () => number, lo: number, hi: number): number => lo + r() * (hi - lo)
export const intBetween = (r: () => number, lo: number, hi: number): number => Math.floor(between(r, lo, hi + 1))
export function shuffle<T>(r: () => number, xs: T[]): T[] {
  const a = [...xs]
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(r() * (i + 1))
    ;[a[i], a[j]] = [a[j]!, a[i]!]
  }
  return a
}

export const HOUR = 3600_000
export const DAY = 24 * HOUR
const CN_OFFSET = 8 * HOUR

/** ms → 2026-10-28T08:00:00+08:00 */
export function iso(ms: number): string {
  return new Date(ms + CN_OFFSET).toISOString().slice(0, 19) + '+08:00'
}
/** 东八区某天 hh:mm 的时间戳；dayOffset 相对「今天」 */
export function cnAt(dayOffset: number, h: number, m = 0, base = Date.now()): number {
  const d = new Date(base + CN_OFFSET)
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate() + dayOffset, h, m) - CN_OFFSET
}
/** 东八区的年月日与星期 */
export function cnParts(ms: number): { y: number; mo: number; d: number; h: number; mi: number; wd: number } {
  const d = new Date(ms + CN_OFFSET)
  return { y: d.getUTCFullYear(), mo: d.getUTCMonth() + 1, d: d.getUTCDate(), h: d.getUTCHours(), mi: d.getUTCMinutes(), wd: d.getUTCDay() }
}
const p2 = (n: number) => String(n).padStart(2, '0')
const WD = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']
export const dateLabel = (ms: number): string => { const p = cnParts(ms); return `${p.y}-${p2(p.mo)}-${p2(p.d)}（${WD[p.wd]}）` }
export const mdhm = (ms: number): string => { const p = cnParts(ms); return `${p2(p.mo)}-${p2(p.d)} ${p2(p.h)}:${p2(p.mi)}` }
export const hms = (ms: number): string => { const p = cnParts(ms); const s = new Date(ms + CN_OFFSET).getUTCSeconds(); return `${p2(p.h)}:${p2(p.mi)}:${p2(s)}` }
export const ymd = (ms: number): string => { const p = cnParts(ms); return `${p.y}${p2(p.mo)}${p2(p.d)}` }

/** 最近一份报告的窗口终点：今天 08:00（还没到 8 点则取昨天 08:00） */
export function latestReportEnd(now = Date.now()): number {
  const today8 = cnAt(0, 8, 0, now)
  return now >= today8 ? today8 : today8 - DAY
}

export const fmtN = (n: number): string => Math.round(n).toLocaleString('en-US')
