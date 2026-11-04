import { reactive } from 'vue'

export type ToastLevel = 'info' | 'success' | 'warn' | 'error'

export interface Toast {
  id: number
  level: ToastLevel
  title: string
  detail?: string
  hint?: string
  action?: { label: string; run: () => void }
  ttl: number
}

export const toasts = reactive<Toast[]>([])
let seq = 0
const timers = new Map<number, ReturnType<typeof setTimeout>>()

export function dismissToast(id: number): void {
  const i = toasts.findIndex((t) => t.id === id)
  if (i >= 0) toasts.splice(i, 1)
  const tm = timers.get(id)
  if (tm) clearTimeout(tm)
  timers.delete(id)
}

/** 弹出提示。相同标题和详情的提示在屏上时只保留一条（刷新计时）。 */
export function toast(level: ToastLevel, title: string, extra: Partial<Omit<Toast, 'id' | 'level' | 'title'>> = {}): number {
  const dup = toasts.find((t) => t.title === title && t.detail === extra.detail)
  if (dup) dismissToast(dup.id)
  const ttl = extra.ttl ?? (level === 'error' ? 7000 : level === 'warn' ? 5500 : 3600)
  const t: Toast = { id: ++seq, level, title, ttl, ...extra }
  toasts.push(t)
  while (toasts.length > 5) dismissToast(toasts[0]!.id)
  if (ttl > 0) timers.set(t.id, setTimeout(() => dismissToast(t.id), ttl))
  return t.id
}

type Extra = Partial<Omit<Toast, 'id' | 'level' | 'title'>>
export const notify = {
  info: (title: string, extra?: Extra) => toast('info', title, extra),
  ok: (title: string, extra?: Extra) => toast('success', title, extra),
  warn: (title: string, extra?: Extra) => toast('warn', title, extra),
  error: (title: string, extra?: Extra) => toast('error', title, extra),
}
