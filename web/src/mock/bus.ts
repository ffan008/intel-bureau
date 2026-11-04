/** mock SSE：与 EventSource 相同的接口，事件按 API.md 的 event 名派发 */
import type { EventSourceLike } from '@/api/client'
import type { SseEventMap, SseEventName } from '@/api/types'

const sources = new Set<MockEventSource>()

export class MockEventSource implements EventSourceLike {
  private target = new EventTarget()
  readyState = 0
  onerror: ((ev: Event) => void) | null = null

  constructor(hello: () => SseEventMap['hello']) {
    setTimeout(() => {
      if (this.readyState === 2) return
      this.readyState = 1
      sources.add(this)
      this.emit('hello', hello())
    }, 120)
  }
  addEventListener(type: string, fn: (ev: MessageEvent) => void): void {
    this.target.addEventListener(type, fn as EventListener)
  }
  emit<K extends SseEventName>(type: K, data: SseEventMap[K]): void {
    this.target.dispatchEvent(new MessageEvent(type, { data: JSON.stringify(data) }))
  }
  close(): void {
    this.readyState = 2
    sources.delete(this)
  }
}

export function broadcast<K extends SseEventName>(type: K, data: SseEventMap[K]): void {
  for (const s of sources) s.emit(type, data)
}
