<script setup lang="ts">
/** 风向词云（§4.8）：上升词品红带光晕、新词青色、其余灰蓝；每 10 秒重新排布（淡出 → 重排 → 淡入） */
import { computed, ref, watch } from 'vue'
import { live } from '@/stores/live'
import { fx } from '@/stores/fx'
import { tooltipBase, useChart, type ECharts } from '@/composables/useChart'
import { useInterval } from '@/composables/useTimers'
import { escapeHtml } from '@/utils/markdown'
import HudPanel from '../hud/HudPanel.vue'

const el = ref<HTMLElement | null>(null)
const fading = ref(false)
const words = computed(() => (live.overview?.stats.keywords ?? []).slice(0, 80))
const counts = computed(() => ({ up: words.value.filter((w) => w.trend === 'up').length, nw: words.value.filter((w) => w.trend === 'new').length }))
const TREND_LABEL = { up: '上升', new: '新词', flat: '平稳' } as const

function data(shuffle: boolean) {
  const ws = words.value
  const max = Math.max(1, ...ws.map((w) => w.weight))
  const list = ws.map((w) => {
    const t = w.weight / max
    const textStyle = w.trend === 'up'
      ? { color: '#ff3db8', textShadowBlur: 14, textShadowColor: 'rgba(255,61,184,.85)', fontWeight: 700 }
      : w.trend === 'new'
        ? { color: '#22e4ff', textShadowBlur: 8, textShadowColor: 'rgba(34,228,255,.6)', fontWeight: 600 }
        : { color: `rgba(${Math.round(108 + t * 61)},${Math.round(134 + t * 62)},${Math.round(163 + t * 58)},${(0.55 + t * 0.4).toFixed(2)})`, fontWeight: 500 }
    return { name: w.word, value: shuffle ? Math.round(w.weight * (0.92 + Math.random() * 0.16)) : w.weight, trend: w.trend, textStyle }
  })
  if (shuffle) list.sort(() => Math.random() - 0.5)
  return list
}

function build(c: ECharts, shuffle = false): void {
  c.setOption({
    tooltip: { ...tooltipBase, formatter: (p: { name: string; value: number; data: { trend: keyof typeof TREND_LABEL } }) =>
      `<b>${escapeHtml(p.name)}</b><br><span style="color:#a9c4dd">${TREND_LABEL[p.data.trend] ?? ''} · 权重 ${p.value}</span>` },
    series: [{
      type: 'wordCloud', shape: 'circle', keepAspect: false, left: 'center', top: 'center', width: '98%', height: '96%',
      sizeRange: [12, 28], rotationRange: [0, 0], gridSize: 8, drawOutOfBound: false, shrinkToFit: true,
      layoutAnimation: fx.loops,
      textStyle: { fontFamily: "'Microsoft YaHei UI','PingFang SC','Rajdhani',sans-serif" },
      emphasis: { focus: 'self', textStyle: { textShadowBlur: 16, textShadowColor: 'rgba(234,246,255,.9)' } },
      data: data(shuffle),
    }],
  }, { notMerge: true })
}

const chart = useChart(el, (c) => build(c), (c) => build(c))
watch([words, () => fx.loops], () => chart.value && build(chart.value))

useInterval(() => {
  const c = chart.value
  if (!c || !fx.loops || !words.value.length) return
  fading.value = true
  setTimeout(() => {
    if (!chart.value) return
    build(chart.value, true)
    fading.value = false
  }, 320)
}, () => 10000)
</script>

<template>
  <HudPanel title="风向词云" code="KEYWORD DRIFT" :index="10">
    <template #actions>
      <span class="lg"><i class="up" />上升 <b class="num">{{ counts.up }}</b></span>
      <span class="lg"><i class="nw" />新词 <b class="num">{{ counts.nw }}</b></span>
      <span class="lg"><i class="fl" />其他</span>
    </template>
    <div ref="el" class="chart" :class="{ fading }" />
    <div v-if="!words.length" class="empty abs"><span class="code">NO KEYWORDS</span>还没有关键词</div>
  </HudPanel>
</template>

<style scoped>
.chart { position: absolute; inset: 0 6px 4px; transition: opacity 0.3s ease; }
.chart.fading { opacity: 0.08; }
.lg { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--text-2); }
.lg b { color: var(--text-1); font-weight: 600; }
.lg i { width: 7px; height: 7px; border-radius: 50%; }
.lg i.up { background: var(--magenta); box-shadow: 0 0 6px var(--magenta); }
.lg i.nw { background: var(--cyan); box-shadow: 0 0 6px var(--cyan); }
.lg i.fl { background: #6c86a3; }
.abs { position: absolute; inset: 0; }
</style>
