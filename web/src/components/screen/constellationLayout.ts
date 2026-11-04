/**
 * 情报星图布局：先用 ECharts 自带的 force 布局（离屏实例，layoutAnimation:false 同步收敛）算出节点位置，
 * 再把位置映射到容器像素坐标：平台枢纽的重心落在容器中心（与 CSS 雷达同心）。
 * 之后正式图表用 cartesian2d + layout:'none'，graph 节点与 lines 光点共用同一坐标系。
 */
import type { ConstellationLink, ConstellationNode } from '@/api/types'
import { echarts } from '@/composables/useChart'

export interface LaidNode extends ConstellationNode { x: number; y: number; deg: number }

const HUB_ANGLE: Record<string, number> = { wechat: -150, qq: -30, feishu: 90 }

function seed(nodes: ConstellationNode[], links: ConstellationLink[], cx: number, cy: number, R: number) {
  const hubs = nodes.filter((n) => n.type === 'platform')
  const angleOf = new Map<string, number>()
  const out: Record<string, { x: number; y: number; fixed?: boolean }> = {}
  hubs.forEach((h, i) => {
    const a = HUB_ANGLE[h.platform ?? ''] ?? (i * 360) / Math.max(1, hubs.length) - 90
    angleOf.set(h.id, a)
    const rad = (a * Math.PI) / 180
    out[h.id] = { x: cx + Math.cos(rad) * R * 0.34, y: cy + Math.sin(rad) * R * 0.34, fixed: true }
  })
  const groups = nodes.filter((n) => n.type === 'group')
  const byHub = new Map<string, ConstellationNode[]>()
  for (const g of groups) {
    const hub = links.find((l) => l.target === g.id && l.source.startsWith('platform:'))?.source ?? `platform:${g.platform}`
    byHub.set(hub, [...(byHub.get(hub) ?? []), g])
  }
  byHub.forEach((gs, hub) => {
    const base = angleOf.get(hub) ?? 0
    gs.forEach((g, i) => {
      const a = base + (i - (gs.length - 1) / 2) * 26
      angleOf.set(g.id, a)
      const rad = (a * Math.PI) / 180
      out[g.id] = { x: cx + Math.cos(rad) * R * 0.5, y: cy + Math.sin(rad) * R * 0.5 }
    })
  })
  nodes.filter((n) => n.type === 'topic').forEach((t, i) => {
    const gs = links.filter((l) => l.target === t.id).map((l) => angleOf.get(l.source)).filter((a): a is number => a !== undefined)
    const a = gs.length ? Math.atan2(gs.reduce((s, x) => s + Math.sin((x * Math.PI) / 180), 0), gs.reduce((s, x) => s + Math.cos((x * Math.PI) / 180), 0)) * 180 / Math.PI : i * 31
    const rad = ((a + ((i % 3) - 1) * 9) * Math.PI) / 180
    out[t.id] = { x: cx + Math.cos(rad) * R * 0.9, y: cy + Math.sin(rad) * R * 0.9 }
  })
  return out
}

interface GraphLike { eachNode(cb: (n: { id: string; getLayout(): number[] | undefined }) => void): void }

/** 返回容器像素坐标（左上为原点） */
export function layoutConstellation(nodes: ConstellationNode[], links: ConstellationLink[], W: number, H: number): LaidNode[] {
  if (!nodes.length) return []
  const host = document.createElement('div')
  host.style.cssText = `position:fixed;left:-10000px;top:0;width:${W}px;height:${H}px;visibility:hidden;pointer-events:none`
  document.body.appendChild(host)
  const tmp = echarts.init(host, undefined, { renderer: 'canvas', width: W, height: H })
  const R = Math.min(W, H) / 2
  const s = seed(nodes, links, W / 2, H / 2, R)
  const ids = new Set(nodes.map((n) => n.id))
  try {
    tmp.setOption({
      animation: false,
      series: [{
        type: 'graph', layout: 'force', left: 0, top: 0, right: 0, bottom: 0, roam: false,
        force: { initLayout: 'none', repulsion: [70, 240], gravity: 0.06, edgeLength: [42, 96], friction: 0.15, layoutAnimation: false },
        data: nodes.map((n) => ({ id: n.id, name: n.name, x: s[n.id]!.x, y: s[n.id]!.y, fixed: !!s[n.id]!.fixed, value: n.value })),
        links: links.filter((l) => ids.has(l.source) && ids.has(l.target)).map((l) => ({ source: l.source, target: l.target, value: l.value })),
      }],
    })
    const pos = new Map<string, [number, number]>()
    const model = (tmp as unknown as { getModel(): { getSeriesByIndex(i: number): { getGraph(): GraphLike } } }).getModel()
    model.getSeriesByIndex(0).getGraph().eachNode((n) => {
      const l = n.getLayout()
      if (l && Number.isFinite(l[0]) && Number.isFinite(l[1])) pos.set(n.id, [l[0]!, l[1]!])
    })
    // 枢纽重心 → 容器中心；面板是宽屏，横向允许比纵向多拉伸一些（上限 2.1 倍）铺满画面
    const hubs = nodes.filter((n) => n.type === 'platform').map((n) => pos.get(n.id) ?? [s[n.id]!.x, s[n.id]!.y])
    const cx = hubs.reduce((a, p) => a + p[0], 0) / Math.max(1, hubs.length)
    const cy = hubs.reduce((a, p) => a + p[1], 0) / Math.max(1, hubs.length)
    let dx = 1, dy = 1
    pos.forEach(([x, y]) => { dx = Math.max(dx, Math.abs(x - cx)); dy = Math.max(dy, Math.abs(y - cy)) })
    const padX = 110, padY = 34
    const ky = (H / 2 - padY) / dy
    const kx = Math.min((W / 2 - padX) / dx, ky * 2.1)
    return nodes.map((n) => {
      const [x, y] = pos.get(n.id) ?? [s[n.id]!.x, s[n.id]!.y]
      const px = W / 2 + (x - cx) * kx, py = H / 2 + (y - cy) * ky
      return { ...n, x: px, y: py, deg: (Math.atan2(py - H / 2, px - W / 2) * 180) / Math.PI }
    })
  } finally {
    tmp.dispose()
    host.remove()
  }
}

/** 六边形枢纽符号 */
export const HEX_PATH = 'path://M50 0 93.3 25v50L50 100 6.7 75V25z'
