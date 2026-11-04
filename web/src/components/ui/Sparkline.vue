<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  values: number[]; width?: number; height?: number; color?: string; fill?: boolean; dot?: boolean; bars?: boolean; strokeWidth?: number
}>(), { width: 120, height: 28, color: 'var(--cyan)', fill: true, dot: true, bars: false, strokeWidth: 1.4 })

const uid = `sp${Math.random().toString(36).slice(2, 8)}`
const geo = computed(() => {
  const v = props.values.filter((x) => Number.isFinite(x))
  const n = v.length
  const W = props.width, H = props.height, pad = props.dot ? 3 : 1
  if (!n) return null
  const max = Math.max(...v), min = props.bars ? 0 : Math.min(...v)
  const span = max - min || 1
  const x = (i: number) => (n === 1 ? W / 2 : pad + (i * (W - pad * 2)) / (n - 1))
  const y = (val: number) => H - pad - ((val - min) / span) * (H - pad * 2)
  const pts = v.map((val, i) => [x(i), y(val)] as const)
  const line = pts.map(([a, b], i) => `${i ? 'L' : 'M'}${a.toFixed(1)} ${b.toFixed(1)}`).join('')
  const area = `${line}L${pts[n - 1]![0].toFixed(1)} ${H}L${pts[0]![0].toFixed(1)} ${H}Z`
  const bw = Math.max(1.5, (W - pad * 2) / n - 1.5)
  const barsRects = v.map((val, i) => ({ x: pad + i * ((W - pad * 2) / n), y: y(val), w: bw, h: H - pad - y(val) }))
  return { line, area, last: pts[n - 1]!, barsRects }
})
</script>

<template>
  <svg class="spark" :width="width" :height="height" :viewBox="`0 0 ${width} ${height}`" aria-hidden="true">
    <defs>
      <linearGradient :id="uid" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0" :stop-color="color" stop-opacity="0.35" />
        <stop offset="1" :stop-color="color" stop-opacity="0" />
      </linearGradient>
    </defs>
    <template v-if="geo">
      <template v-if="bars">
        <rect v-for="(b, i) in geo.barsRects" :key="i" :x="b.x" :y="b.y" :width="b.w" :height="Math.max(1, b.h)" :fill="color" :opacity="0.35 + (0.65 * (i + 1)) / geo.barsRects.length" rx="0.5" />
      </template>
      <template v-else>
        <path v-if="fill" :d="geo.area" :fill="`url(#${uid})`" />
        <path :d="geo.line" fill="none" :stroke="color" :stroke-width="strokeWidth" stroke-linejoin="round" stroke-linecap="round" />
        <template v-if="dot">
          <circle :cx="geo.last[0]" :cy="geo.last[1]" r="4" :fill="color" opacity="0.25" />
          <circle :cx="geo.last[0]" :cy="geo.last[1]" r="2" :fill="color" />
        </template>
      </template>
    </template>
    <line v-else x1="0" :y1="height - 1" :x2="width" :y2="height - 1" stroke="rgba(108,134,163,.3)" stroke-dasharray="2 3" />
  </svg>
</template>

<style scoped>
.spark { display: block; overflow: visible; }
</style>
