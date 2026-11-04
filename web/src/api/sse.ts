/**
 * SSE 订阅：GET /api/events?token=。
 * - 浏览器 EventSource 自带的重连无法换令牌、也没有退避，这里关闭它，自己做指数退避（1s → 30s，带抖动）。
 * - 连续失败 2 次后强制重取 session token（后端重启后令牌可能变了）。
 * - 45 秒收不到任何事件（心跳 15 秒一次）视为假死，主动重连。
 * - 每次「重新」连上都会触发 onReconnect，由调用方刷新 overview。
 */
import { eventsUrl, mockTransport, type EventSourceLike } from './client'
import { SSE_EVENTS, type SseEventMap, type SseEventName } from './types'

export type StreamState = 'idle' | 'connecting' | 'open' | 'retrying' | 'closed'
type Handler<K extends SseEventName> = (data: SseEventMap[K]) => void
type AnyHandler = (data: unknown) => void

export interface StreamHooks {
  onState?: (s: StreamState, info: { attempt: number; retryInMs?: number }) => void
  onReconnect?: () => void
}

const MAX_BACKOFF = 30000
const STALE_MS = 45000

export class EventStream {
  private src: EventSourceLike | null = null
  private handlers = new Map<string, Set<AnyHandler>>()
  private attempt = 0
  private everOpened = false
  private retryTimer: ReturnType<typeof setTimeout> | null = null
  private watchdog: ReturnType<typeof setInterval> | null = null
  private lastEventAt = 0
  private stopped = true
  state: StreamState = 'idle'

  constructor(private hooks: StreamHooks = {}) {}

  on<K extends SseEventName>(event: K, fn: Handler<K>): () => void {
    let set = this.handlers.get(event)
    if (!set) this.handlers.set(event, (set = new Set()))
    set.add(fn as AnyHandler)
    return () => set!.delete(fn as AnyHandler)
  }

  start(): void {
    if (!this.stopped) return
    this.stopped = false
    void this.connect()
    this.watchdog = setInterval(() => {
      if (this.state === 'open' && Date.now() - this.lastEventAt > STALE_MS) this.fail()
    }, 10000)
  }

  stop(): void {
    this.stopped = true
    this.teardown()
    if (this.retryTimer) clearTimeout(this.retryTimer)
    if (this.watchdog) clearInterval(this.watchdog)
    this.retryTimer = this.watchdog = null
    this.setState('closed')
  }

  private setState(s: StreamState, retryInMs?: number): void {
    this.state = s
    this.hooks.onState?.(s, { attempt: this.attempt, retryInMs })
  }

  private teardown(): void {
    if (this.src) {
      this.src.onerror = null
      this.src.close()
      this.src = null
    }
  }

  private async connect(): Promise<void> {
    if (this.stopped) return
    this.setState('connecting')
    let src: EventSourceLike
    try {
      const m = mockTransport()
      src = m ? m.openEvents() : new EventSource(await eventsUrl(this.attempt >= 2))
    } catch {
      this.fail()
      return
    }
    if (this.stopped) { src.close(); return }
    this.src = src
    this.lastEventAt = Date.now()
    for (const name of SSE_EVENTS) {
      src.addEventListener(name, (ev: MessageEvent) => this.dispatch(name, ev))
    }
    src.onerror = () => this.fail()
  }

  private dispatch(name: SseEventName, ev: MessageEvent): void {
    this.lastEventAt = Date.now()
    if (name === 'hello' && this.state !== 'open') {
      const reconnected = this.everOpened
      this.everOpened = true
      this.attempt = 0
      this.setState('open')
      if (reconnected) this.hooks.onReconnect?.()
    }
    let data: unknown = {}
    try { data = typeof ev.data === 'string' && ev.data ? JSON.parse(ev.data) : {} } catch { return }
    this.handlers.get(name)?.forEach((fn) => {
      try { fn(data) } catch (e) { console.error(`[sse] 处理 ${name} 出错`, e) }
    })
  }

  private fail(): void {
    if (this.stopped) return
    this.teardown()
    if (this.retryTimer) return
    this.attempt += 1
    const base = Math.min(MAX_BACKOFF, 1000 * 2 ** (this.attempt - 1))
    const delay = Math.min(MAX_BACKOFF, Math.round(base * (0.8 + Math.random() * 0.4)))
    this.setState('retrying', delay)
    this.retryTimer = setTimeout(() => {
      this.retryTimer = null
      void this.connect()
    }, delay)
  }
}
