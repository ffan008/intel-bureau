/**
 * 应用级状态：后端/演示模式判定。
 * 启用演示数据（MOCK）的条件：VITE_MOCK=1，或后端不可达。
 * 因后端不可达而进入 MOCK 时，每 20 秒探测一次，恢复后提示刷新。
 */
import { reactive } from 'vue'
import { installMock, probeBackend } from '@/api/client'
import { notify } from './toast'

export const app = reactive({
  ready: false,
  mock: false,
  mockReason: '',
  version: '',
  /** 后端报告的模式（live / demo），MOCK 时由 mock 数据决定 */
  serverMode: 'live' as 'live' | 'demo',
})

async function enableMock(reason: string): Promise<void> {
  const { createMockServer } = await import('@/mock')
  installMock(createMockServer())
  app.mock = true
  app.mockReason = reason
  app.version = '1.0.0-mock'
}

let watcher: ReturnType<typeof setInterval> | null = null
function watchBackend(): void {
  if (watcher) return
  watcher = setInterval(async () => {
    if (document.hidden) return
    const r = await probeBackend(2500)
    if (r.ok) {
      if (watcher) clearInterval(watcher)
      watcher = null
      notify.ok('后端已上线', {
        detail: '当前仍在显示演示数据，刷新后切换到真实数据。',
        ttl: 0,
        action: { label: '刷新', run: () => location.reload() },
      })
    }
  }, 20000)
}

export async function bootstrap(): Promise<void> {
  if (import.meta.env.VITE_MOCK === '1') {
    await enableMock('已用 VITE_MOCK=1 启动（npm run dev:mock）')
  } else {
    const r = await probeBackend()
    if (r.ok) {
      app.version = r.session.version
      app.serverMode = r.session.mode
    } else {
      await enableMock(r.reason)
      notify.warn('后端不可用，已切换到演示数据', { detail: r.reason, hint: '启动后端后会自动提示刷新', ttl: 8000 })
      watchBackend()
    }
  }
  app.ready = true
}
