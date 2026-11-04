<script setup lang="ts">
/**
 * 情报星图（§4.3）：力导向 graph（平台枢纽 / 群 / 话题）+ CSS 雷达 + lines 光点 + 每 3 秒随机高亮一个话题。
 */
import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue'
import { live } from '@/stores/live'
import { fx } from '@/stores/fx'
import { tooltipBase, useChart, type ECharts } from '@/composables/useChart'
import { useInterval } from '@/composables/useTimers'
import { categoryColor, categoryName, platformColor, PLATFORM, REAL_PLATFORMS } from '@/utils/meta'
import { escapeHtml } from '@/utils/markdown'
import { fmtInt } from '@/utils/format'
import { HEX_PATH, layoutConstellation, type LaidNode } from './constellationLayout'
import HudPanel from '../hud/HudPanel.vue'
import KbChip from './KbChip.vue'

const el = ref<HTMLElement | null>(null)
const laid = shallowRef<LaidNode[]>([])
const hovering = ref(false)
const data = computed(() => live.overview?.constellation)
const empty = computed(() => !data.value?.nodes.length)
const counts = computed(() => ({
  groups: data.value?.nodes.filter((n) => n.type === 'group').length ?? 0,
  topics: data.value?.nodes.filter((n) => n.type === 'topic').length ?? 0,
  links: data.value?.links.length ?? 0,
}))

const colorOf = (n: LaidNode) => (n.type === 'topic' ? categoryColor(n.category) : platformColor(n.platform))

function build(c: ECharts): void {
  const d = data.value
  const W = el.value?.clientWidth ?? 0, H = el.value?.clientHeight ?? 0
  if (!d || !d.nodes.length || W < 50 || H < 50) { c.clear(); laid.value = []; return }
  const nodes = layoutConstellation(d.nodes, d.links, W, H)
  laid.value = nodes
  const byId = new Map(nodes.map((n) => [n.id, n]))
  const vmax = (t: string) => Math.max(1, ...nodes.filter((n) => n.type === t).map((n) => n.value))
  const gmax = vmax('group'), tmax = vmax('topic')
  const gData = nodes.map((n) => {
    const col = colorOf(n)
    if (n.type === 'platform') {
      return { id: n.id, name: n.name, value: [n.x, n.y], raw: n, symbol: HEX_PATH, symbolSize: 50,
        itemStyle: { color: col, borderColor: '#eaf6ff', borderWidth: 1.5, shadowBlur: 28, shadowColor: col },
        label: { show: true, position: 'inside', color: '#03060f', fontSize: 13, fontWeight: 700 } }
    }
    if (n.type === 'group') {
      const sz = 13 + (n.value / gmax) * 13
      return { id: n.id, name: n.name, value: [n.x, n.y], raw: n, symbolSize: sz,
        itemStyle: { color: { type: 'radial', x: 0.5, y: 0.5, r: 0.5, colorStops: [{ offset: 0, color: '#eaf6ff' }, { offset: 0.35, color: col }, { offset: 1, color: col + '33' }] }, borderColor: col, borderWidth: 1.2, shadowBlur: 14, shadowColor: col },
        label: { show: true, position: n.x >= W / 2 ? 'right' : 'left', distance: 6, color: '#cfe4f7', fontSize: 11.5 } }
    }
    const sz = 7 + (n.value / tmax) * 10
    return { id: n.id, name: n.name, value: [n.x, n.y], raw: n, symbolSize: sz,
      itemStyle: { color: col, opacity: 0.92, shadowBlur: 10, shadowColor: col },
      label: { show: true, position: n.x >= W / 2 ? 'right' : 'left', distance: 4, color: col, fontSize: 11, opacity: 0.88 } }
  })
  const valid = d.links.filter((l) => byId.has(l.source) && byId.has(l.target))
  const gLinks = valid.map((l) => {
    const a = byId.get(l.source)!, b = byId.get(l.target)!
    const [c0, c1] = a.x <= b.x ? [colorOf(a), colorOf(b)] : [colorOf(b), colorOf(a)]
    const hub = a.type === 'platform'
    return { source: l.source, target: l.target, value: l.value,
      lineStyle: { width: hub ? 1.4 : 0.9, opacity: hub ? 0.55 : 0.38, curveness: 0.18,
        color: { type: 'linear', x: 0, y: 0, x2: 1, y2: 0, colorStops: [{ offset: 0, color: c0 }, { offset: 1, color: c1 }] } } }
  })
  const flows = valid.map((l) => {
    const a = byId.get(l.source)!, b = byId.get(l.target)!
    return { coords: [[a.x, a.y], [b.x, b.y]], lineStyle: { color: colorOf(b) } }
  })
  c.setOption({
    animation: fx.loops,
    animationDurationUpdate: 600,
    grid: { left: 0, right: 0, top: 0, bottom: 0, containLabel: false },
    xAxis: { type: 'value', min: 0, max: W, show: false },
    yAxis: { type: 'value', min: 0, max: H, inverse: true, show: false },
    tooltip: { ...tooltipBase, trigger: 'item', confine: true, formatter: tip },
    series: [
      { id: 'g', type: 'graph', coordinateSystem: 'cartesian2d', layout: 'none', roam: false, draggable: false, z: 3,
        data: gData, links: gLinks, edgeSymbol: ['none', 'none'],
        labelLayout: { hideOverlap: true },
        emphasis: { focus: 'adjacency', scale: 1.25, lineStyle: { width: 2, opacity: 0.95 }, label: { show: true, color: '#fff' } },
        blur: { itemStyle: { opacity: 0.32 }, lineStyle: { opacity: 0.1 }, label: { opacity: 0.4 } } },
      { id: 'flow', type: 'lines', coordinateSystem: 'cartesian2d', z: 4, silent: true, polyline: false,
        lineStyle: { width: 0, opacity: 0, curveness: 0.18 },
        effect: { show: fx.flowDots, period: 4.2, trailLength: 0.2, symbol: 'circle', symbolSize: 3, loop: true },
        data: flows },
    ],
  }, { notMerge: true })
}

function tip(p: unknown): string {
  const x = p as { dataType?: string; data?: { raw?: LaidNode; source?: string; target?: string; value?: number } }
  if (x.dataType === 'edge') {
    const s = laid.value.find((n) => n.id === x.data?.source), t = laid.value.find((n) => n.id === x.data?.target)
    return `${escapeHtml(s?.name)} → ${escapeHtml(t?.name)}<br><span style="color:#6c86a3">关联 ${fmtInt(x.data?.value ?? 0)}</span>`
  }
  const n = x.data?.raw
  if (!n) return ''
  const col = colorOf(n)
  const kind = n.type === 'platform' ? '平台枢纽' : n.type === 'group' ? `${PLATFORM[n.platform ?? 'demo'].label}群` : categoryName(n.category)
  const metric = n.type === 'topic' ? `相关消息 ${fmtInt(n.value)} 条` : `24h 消息 ${fmtInt(n.value)} 条`
  return `<b style="color:${col}">${escapeHtml(n.name)}</b><br><span style="color:#a9c4dd">${escapeHtml(kind)}</span> · ${metric}`
}

const chart = useChart(el, (c) => {
  build(c)
  c.on('mouseover', () => (hovering.value = true))
  c.on('mouseout', () => (hovering.value = false))
  c.on('globalout', () => (hovering.value = false))
}, build)
watch([data, () => fx.flowDots, () => fx.loops], () => chart.value && build(chart.value))

// 每 3 秒随机高亮一个话题节点
let lastHi = -1
useInterval(() => {
  const c = chart.value
  if (!c || hovering.value || !fx.loops) return
  const idx = laid.value.map((n, i) => (n.type === 'topic' ? i : -1)).filter((i) => i >= 0)
  if (!idx.length) return
  let next = idx[Math.floor(Math.random() * idx.length)]!
  if (next === lastHi && idx.length > 1) next = idx[(idx.indexOf(next) + 1) % idx.length]!
  if (lastHi >= 0) c.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: lastHi })
  c.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: next })
  c.dispatchAction({ type: 'showTip', seriesIndex: 0, dataIndex: next })
  lastHi = next
  // 高亮停留 1.8 秒后恢复全图，避免整张图大部分时间处于变暗状态
  if (unHi) clearTimeout(unHi)
  unHi = setTimeout(() => {
    if (!chart.value || hovering.value) return
    chart.value.dispatchAction({ type: 'downplay', seriesIndex: 0, dataIndex: next })
    chart.value.dispatchAction({ type: 'hideTip' })
  }, 1800)
}, () => 3000)
let unHi: ReturnType<typeof setTimeout> | null = null
onBeforeUnmount(() => { lastHi = -1; if (unHi) clearTimeout(unHi) })
const hubs = computed(() => laid.value.filter((n) => n.type === 'platform'))
</script>

<template>
  <HudPanel title="情报星图" code="INTEL CONSTELLATION" :index="4" flush>
    <template #head><KbChip /></template>
    <template #actions>
      <span class="legend">
        <span v-for="p in REAL_PLATFORMS" :key="p"><i :style="{ background: PLATFORM[p].color }" />{{ PLATFORM[p].label }}</span>
        <span><i class="tp" />话题</span>
      </span>
    </template>
    <div class="cst">
      <div class="radar" aria-hidden="true">
        <span class="ring r1" /><span class="ring r2" /><span class="ring r3" />
        <span class="cross h" /><span class="cross v" />
        <span class="arm fx-loop" />
        <span class="ticks" />
      </div>
      <span v-for="h in hubs" :key="h.id" class="hubpulse fx-loop" :style="{ left: h.x + 'px', top: h.y + 'px', '--c': platformColor(h.platform) }" aria-hidden="true" />
      <div ref="el" class="chart" @mouseleave="hovering = false" />
      <div v-if="empty" class="wait"><span class="disp">AWAITING SIGNAL</span>等待情报……</div>
      <div class="ro tl num">NODES {{ String(laid.length).padStart(3, '0') }} · LINKS {{ String(counts.links).padStart(3, '0') }}</div>
      <div class="ro tr num">GROUPS {{ counts.groups }} · TOPICS {{ counts.topics }}</div>
      <div class="ro bl"><i class="blink fx-loop" />雷达扫描 · 4s/圈</div>
      <div class="ro br num">FORCE · {{ live.overview ? new Date(live.overview.generated_at).toLocaleTimeString('zh-CN', { hour12: false, timeZone: 'Asia/Shanghai' }) : '--:--:--' }}</div>
    </div>
  </HudPanel>
</template>

<style scoped>
.legend { display: flex; gap: 12px; font-size: 11px; color: var(--text-2); }
.legend i { display: inline-block; width: 7px; height: 7px; border-radius: 50%; margin-right: 5px; vertical-align: 0; box-shadow: 0 0 6px currentColor; }
.legend i.tp { background: conic-gradient(#22e4ff, #8b5cff, #ff3db8, #ffb020, #2bff9a, #22e4ff); }
.cst { position: absolute; inset: 0; overflow: hidden; }
.chart { position: absolute; inset: 0; z-index: 2; }
.radar { position: absolute; left: 50%; top: 50%; width: 400px; height: 400px; margin: -200px 0 0 -200px; z-index: 1; pointer-events: none; }
.ring { position: absolute; border-radius: 50%; border: 1px solid rgba(34, 228, 255, 0.16); }
.r1 { inset: 0; border-color: rgba(34, 228, 255, 0.22); box-shadow: inset 0 0 40px rgba(34, 228, 255, 0.05); }
.r2 { inset: 66px; border-style: dashed; }
.r3 { inset: 133px; }
.cross { position: absolute; background: linear-gradient(90deg, transparent, rgba(34, 228, 255, 0.18), transparent); }
.cross.h { left: -60px; right: -60px; top: 50%; height: 1px; }
.cross.v { top: -30px; bottom: -30px; left: 50%; width: 1px; background: linear-gradient(180deg, transparent, rgba(34, 228, 255, 0.18), transparent); }
.arm {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: conic-gradient(from 0deg, rgba(34, 228, 255, 0) 0deg, rgba(34, 228, 255, 0) 290deg, rgba(34, 228, 255, 0.05) 320deg, rgba(34, 228, 255, 0.28) 359deg, rgba(34, 228, 255, 0) 360deg);
  animation: kf-spin 4s linear infinite;
  transform: rotate(40deg);
  will-change: transform;
}
.arm::after { content: ''; position: absolute; left: 50%; top: 0; width: 1px; height: 50%; background: linear-gradient(0deg, rgba(34, 228, 255, 0.1), rgba(34, 228, 255, 0.8)); box-shadow: 0 0 6px var(--cyan); transform: translateX(-0.5px); }
.ticks { position: absolute; inset: -8px; border-radius: 50%; background: repeating-conic-gradient(rgba(34, 228, 255, 0.35) 0deg 0.6deg, transparent 0.6deg 10deg); -webkit-mask: radial-gradient(circle, transparent 205px, #000 206px); mask: radial-gradient(circle, transparent 205px, #000 206px); }
.hubpulse { position: absolute; z-index: 1; width: 64px; height: 64px; margin: -32px 0 0 -32px; border-radius: 50%; border: 1px solid var(--c); opacity: 0; animation: kf-pulse-ring 2.6s ease-out infinite; pointer-events: none; }
.wait { position: absolute; inset: 0; z-index: 3; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; color: var(--text-1); font-size: 14px; }
.wait .disp { font-size: 10px; letter-spacing: 4px; color: var(--cyan); }
.ro { position: absolute; z-index: 3; font-size: 10px; color: rgba(108, 134, 163, 0.85); letter-spacing: 1px; pointer-events: none; }
.tl { left: 14px; top: 10px; }
.tr { right: 14px; top: 10px; }
.bl { left: 14px; bottom: 10px; display: flex; align-items: center; gap: 6px; font-size: 10.5px; letter-spacing: 0; }
.br { right: 14px; bottom: 10px; }
.blink { width: 5px; height: 5px; border-radius: 50%; background: var(--cyan); box-shadow: 0 0 6px var(--cyan); animation: kf-blink 1.2s steps(1) infinite; }
</style>
