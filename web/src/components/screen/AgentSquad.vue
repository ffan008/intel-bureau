<script setup lang="ts">
/**
 * Agent 编队（§4.5）：2 列 × 4 行，蛇形流水线：
 *   01 SCOUT → 02 SWEEPER
 *                  ↓
 *   04 DECODER ← 03 ANALYST
 *       ↓
 *   05 STRATEGIST → 06 AUDITOR
 *                      ↓
 *   08 COURIER ← 07 WRITER
 * 卡片之间用 SVG 连线串起来，数据光点沿线移动（WAAPI translate）；运行到哪段，哪段变亮。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { agentViews, running } from '@/stores/live'
import { fx } from '@/stores/fx'
import { AGENTS } from '@/utils/meta'
import HudPanel from '../hud/HudPanel.vue'
import AgentCard from './AgentCard.vue'

// 网格位置（行, 列），按流水线顺序
const CELL: [number, number][] = [[0, 0], [0, 1], [1, 1], [1, 0], [2, 0], [2, 1], [3, 1], [3, 0]]
const grid = ref<HTMLElement | null>(null)
const cards = ref<HTMLElement[]>([])
const segs = ref<{ d: string; pts: [number, number][]; len: number }[]>([])
const size = ref({ w: 0, h: 0 })
const dots = ref<SVGGElement[]>([])
let anims: Animation[] = []
let ro: ResizeObserver | null = null

const views = computed(() => agentViews.value)
const doneCount = computed(() => views.value.filter((a) => a.status === 'done').length)

function measure(): void {
  const g = grid.value
  if (!g || cards.value.length < 8) return
  size.value = { w: g.clientWidth, h: g.clientHeight }
  const box = (i: number) => { const c = cards.value[i]!; return { l: c.offsetLeft, t: c.offsetTop, r: c.offsetLeft + c.offsetWidth, b: c.offsetTop + c.offsetHeight, cy: c.offsetTop + c.offsetHeight / 2 } }
  const out: { d: string; pts: [number, number][]; len: number }[] = []
  for (let i = 0; i < 7; i++) {
    const a = box(i), b = box(i + 1)
    const [ra] = CELL[i]!, [rb] = CELL[i + 1]!
    let pts: [number, number][]
    if (ra === rb) {
      pts = a.l < b.l ? [[a.r, a.cy], [b.l, b.cy]] : [[a.l, a.cy], [b.r, b.cy]]
    } else {
      const right = CELL[i]![1] === 1
      const x = right ? a.r + 7 : a.l - 7
      const ax = right ? a.r : a.l
      pts = [[ax, a.cy], [x, a.cy], [x, b.cy], [ax, b.cy]]
    }
    const len = pts.slice(1).reduce((s, p, k) => s + Math.hypot(p[0] - pts[k]![0], p[1] - pts[k]![1]), 0)
    out.push({ pts, len, d: pts.map((p, k) => `${k ? 'L' : 'M'}${p[0]} ${p[1]}`).join('') })
  }
  segs.value = out
  void nextTick(animate)
}

/** i 段的状态：active（上游已完成、下游正在执行）/ done（两端都完成）/ idle */
function segState(i: number): 'active' | 'done' | 'idle' {
  const a = views.value[i]?.status, b = views.value[i + 1]?.status
  if ((a === 'done' || a === 'skipped') && b === 'running') return 'active'
  if ((a === 'done' || a === 'skipped') && (b === 'done' || b === 'skipped')) return 'done'
  return 'idle'
}

function animate(): void {
  anims.forEach((x) => x.cancel())
  anims = []
  if (!fx.loops) return
  segs.value.forEach((s, i) => {
    const dot = dots.value[i]
    if (!dot || s.len <= 0) return
    let acc = 0
    const kf = s.pts.map((p, k) => {
      if (k) acc += Math.hypot(p[0] - s.pts[k - 1]![0], p[1] - s.pts[k - 1]![1])
      return { transform: `translate(${p[0]}px, ${p[1]}px)`, offset: acc / s.len }
    })
    const active = segState(i) === 'active'
    anims.push(dot.animate(kf as Keyframe[], { duration: Math.max(500, s.len * (active ? 14 : 30)), iterations: Infinity, easing: 'linear' }))
  })
}

onMounted(() => {
  measure()
  ro = new ResizeObserver(measure)
  if (grid.value) ro.observe(grid.value)
})
onBeforeUnmount(() => { ro?.disconnect(); anims.forEach((x) => x.cancel()) })
watch(() => [fx.loops, ...views.value.map((v) => v.status)], () => void nextTick(animate))
</script>

<template>
  <HudPanel title="Agent 编队" code="AGENT SQUAD · 8" :index="6">
    <template #actions>
      <span class="sum" :class="{ on: running }">
        <i class="fx-loop" />{{ running ? '作战中' : '待命' }}<b class="num">{{ doneCount }}/8</b>
      </span>
    </template>
    <div ref="grid" class="grid">
      <svg class="wires" :width="size.w" :height="size.h" :viewBox="`0 0 ${size.w} ${size.h}`" aria-hidden="true">
        <g v-for="(s, i) in segs" :key="i" :class="['seg', segState(i)]">
          <path :d="s.d" class="ln" />
          <path :d="s.d" class="glow" />
          <g :ref="(el) => { if (el) dots[i] = el as SVGGElement }" class="dot">
            <circle r="4" class="halo" /><circle r="1.8" class="core" />
          </g>
        </g>
      </svg>
      <div v-for="(a, i) in views" :key="a.code" :ref="(el) => { if (el) cards[i] = el as HTMLElement }"
        class="cell" :style="{ gridRow: CELL[i]![0] + 1, gridColumn: CELL[i]![1] + 1 }">
        <AgentCard :agent="a" :step="i + 1" />
      </div>
    </div>
    <span class="sr-only">{{ AGENTS.map((a) => a.name).join('、') }}</span>
  </HudPanel>
</template>

<style scoped>
.sum { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-2); }
.sum i { width: 6px; height: 6px; border-radius: 50%; background: var(--text-2); }
.sum.on { color: var(--cyan); }
.sum.on i { background: var(--cyan); box-shadow: 0 0 8px var(--cyan); animation: kf-blink 0.8s steps(1) infinite; }
.sum b { color: var(--text-0); margin-left: 4px; font-weight: 600; }
.grid { position: relative; display: grid; grid-template-columns: 1fr 1fr; grid-template-rows: repeat(4, 1fr); gap: 8px 16px; height: 100%; padding: 0 2px; }
.cell { position: relative; z-index: 1; display: flex; min-width: 0; min-height: 0; }
.cell > :deep(*) { flex: 1; }
.wires { position: absolute; left: 0; top: 0; z-index: 2; overflow: visible; pointer-events: none; }
.ln { fill: none; stroke: rgba(80, 200, 255, 0.22); stroke-width: 1; }
.glow { fill: none; stroke: var(--cyan); stroke-width: 2; opacity: 0; filter: drop-shadow(0 0 4px var(--cyan)); transition: opacity 0.4s; }
.seg.done .ln { stroke: rgba(43, 255, 154, 0.45); }
.seg.active .ln { stroke: var(--cyan); }
.seg.active .glow { opacity: 0.9; }
.dot { opacity: 0.35; }
.dot .halo { fill: rgba(34, 228, 255, 0.25); }
.dot .core { fill: #eaf6ff; }
.seg.idle .dot { opacity: 0.18; }
.seg.done .dot { opacity: 0.45; }
.seg.done .dot .halo { fill: rgba(43, 255, 154, 0.3); }
.seg.active .dot { opacity: 1; }
html[data-fx='off'] .dot { display: none; }
</style>
