<script setup lang="ts">
/** 7×24 活跃热力（§4.8）：ECharts heatmap，深蓝 → 青 → 品红；悬停显示具体数量 */
import { computed, ref, watch } from 'vue'
import { live } from '@/stores/live'
import { fx } from '@/stores/fx'
import { tooltipBase, useChart, type ECharts } from '@/composables/useChart'
import { WEEK_CN, zoned } from '@/utils/format'
import { escapeHtml } from '@/utils/markdown'
import HudPanel from '../hud/HudPanel.vue'

const el = ref<HTMLElement | null>(null)
const heat = computed(() => live.overview?.stats.heat_7x24 ?? [])
const max = computed(() => Math.max(1, ...heat.value.map((x) => x[2])))
const peak = computed(() => heat.value.reduce<[number, number, number] | null>((a, b) => (!a || b[2] > a[2] ? b : a), null))

/** dayIndex 0 = 最旧，6 = 窗口结束那天 */
const days = computed(() => {
  const end = live.overview?.window.end ? new Date(live.overview.window.end).getTime() : Date.now()
  return Array.from({ length: 7 }, (_, i) => {
    const z = zoned(end - (6 - i) * 86400_000)!
    return { short: WEEK_CN[z.wd]!, full: `${WEEK_CN[z.wd]} ${String(z.mo).padStart(2, '0')}-${String(z.d).padStart(2, '0')}` }
  })
})

function build(c: ECharts): void {
  const d = days.value
  c.setOption({
    animation: fx.loops,
    grid: { left: 34, right: 6, top: 4, bottom: 20 },
    tooltip: {
      ...tooltipBase, position: 'top',
      formatter: (p: { value: [number, number, number] }) => {
        const [h, day, n] = p.value
        return `${escapeHtml(d[day]?.full)} · ${String(h).padStart(2, '0')}:00–${String((h + 1) % 24).padStart(2, '0')}:00<br><b style="color:#22e4ff;font-family:'JetBrains Mono'">${n.toLocaleString('en-US')}</b> 条消息`
      },
    },
    xAxis: {
      type: 'category', data: Array.from({ length: 24 }, (_, h) => String(h).padStart(2, '0')),
      axisLine: { show: false }, axisTick: { show: false }, splitArea: { show: false },
      axisLabel: { color: '#6c86a3', fontSize: 10, fontFamily: 'JetBrains Mono', interval: 2, margin: 6 },
    },
    yAxis: {
      type: 'category', data: d.map((x) => x.short), axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: '#8aa5c0', fontSize: 11, margin: 8 },
    },
    visualMap: { show: false, min: 0, max: max.value, inRange: { color: ['#071330', '#0b4a7a', '#0b8fb3', '#22e4ff', '#b45cff', '#ff3db8'] } },
    series: [{
      type: 'heatmap', data: heat.value.map(([day, h, n]) => [h, day, n]),
      itemStyle: { borderColor: '#040a18', borderWidth: 2, borderRadius: 2 },
      emphasis: { itemStyle: { borderColor: '#eaf6ff', borderWidth: 1, shadowBlur: 12, shadowColor: 'rgba(34,228,255,.8)' } },
      progressive: 0,
    }],
  }, { notMerge: true })
}

const chart = useChart(el, build)
watch([heat, () => fx.loops], () => chart.value && build(chart.value))
</script>

<template>
  <HudPanel title="活跃热力 7×24" code="ACTIVITY HEATMAP" :index="9">
    <template #actions>
      <span v-if="peak" class="peak">高峰 <b class="num">{{ days[peak[0]]?.short }} {{ String(peak[1]).padStart(2, '0') }}:00</b></span>
      <span class="scale"><em class="num">0</em><i /><em class="num">{{ max }}</em></span>
    </template>
    <div ref="el" class="chart" />
  </HudPanel>
</template>

<style scoped>
.chart { position: absolute; inset: 2px 8px 4px 4px; }
.peak { font-size: 11px; color: var(--text-2); }
.peak b { color: var(--magenta); font-weight: 600; margin-left: 2px; }
.scale { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--text-2); }
.scale i { width: 64px; height: 5px; border-radius: 1px; background: linear-gradient(90deg, #071330, #0b8fb3, #22e4ff, #b45cff, #ff3db8); }
.scale em { font-style: normal; }
</style>
