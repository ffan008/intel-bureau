/**
 * 演示数据（MOCK）：在浏览器内实现 docs/API.md 的全部接口与 SSE 事件。
 * 启用条件见 stores/app.ts：VITE_MOCK=1 或后端不可达。
 */
import type { MockTransport } from '@/api/client'
import type { Platform } from '@/api/types'
import { broadcast, MockEventSource } from './bus'
import { WHITELIST } from './data/groups'
import { ROUTES_A, err, type Route } from './routes'
import { ROUTES_B } from './routes2'
import { ROUTES_C } from './routes3'
import { S } from './state'
import { pick, rng } from './util'

const ROUTES: Route[] = [...ROUTES_A, ...ROUTES_B, ...ROUTES_C]
const PREVIEWS = ['这个工作流我晚上试试', 'worktree 那个方法有人实测吗', '可灵新版运镜确实稳了', '求一个线稿上色的工作流', '短剧前三秒怎么剪', '多图融合点名法好用', '有人在招分镜师吗', '今天的风向标出了吗']

let timersStarted = false
function startAmbient(): void {
  if (timersStarted) return
  timersStarted = true
  const r = rng(4242)
  setInterval(() => broadcast('heartbeat', { server_time: new Date().toISOString() }), 15000)
  // 实时上报（QQ 走 NapCat 上报；微信只是模拟增量）
  const tick = () => {
    const qqOrWx: Platform = r() < 0.7 ? 'qq' : 'wechat'
    const g = pick(r, WHITELIST.filter((x) => x.platform === qqOrWx))
    const count = 1 + Math.floor(r() * 3)
    S.ingest[qqOrWx as 'qq' | 'wechat'] += count
    const live = (S.settings.privacy as { live_preview?: boolean }).live_preview === true
    broadcast('ingest.message', { platform: g.platform, group_name: g.name, count, ...(live ? { sender: pick(r, ['老K', 'Leo', '阿青', '短剧老炮', '十三']), preview: pick(r, PREVIEWS) } : {}) })
    setTimeout(tick, 2500 + r() * 4500)
  }
  setTimeout(tick, 3000)
}

export function createMockServer(): MockTransport {
  return {
    async handle(req) {
      const route = ROUTES.find(([m, re]) => m === req.method && re.test(req.path))
      await new Promise((res) => setTimeout(res, req.path === '/overview' ? 60 : 90 + Math.random() * 140))
      if (!route) return err(404, 'not_found', `演示数据未实现：${req.method} ${req.path}`)
      const [, re, handler] = route
      const m = re.exec(req.path)!
      try {
        return await handler({ m, q: req.query, body: req.body })
      } catch (e) {
        console.error('[mock]', e)
        return err(500, 'mock_error', `演示数据出错：${(e as Error).message}`)
      }
    },
    openEvents() {
      startAmbient()
      return new MockEventSource(() => ({ server_time: new Date().toISOString(), mode: 'live' }))
    },
  }
}
