/** ECharts 按需注册 + 组件生命周期封装：resize 防抖、卸载 dispose。 */
import * as echarts from 'echarts/core'
import { GraphChart, HeatmapChart, LinesChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, VisualMapComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import 'echarts-wordcloud'
import { onBeforeUnmount, onMounted, shallowRef, type Ref } from 'vue'
import { screenScale } from './useScreenScale'

echarts.use([GraphChart, LinesChart, HeatmapChart, GridComponent, TooltipComponent, VisualMapComponent, CanvasRenderer])

export { echarts }
export type ECharts = echarts.ECharts
export type EOption = echarts.EChartsCoreOption

/** 统一的 HUD tooltip 外观（内容由各图 formatter 生成，必须转义） */
export const tooltipBase = {
  backgroundColor: 'rgba(6, 14, 32, 0.92)',
  borderColor: 'rgba(80, 220, 255, 0.45)',
  borderWidth: 1,
  padding: [8, 10],
  textStyle: { color: '#eaf6ff', fontSize: 12, fontFamily: "'Microsoft YaHei UI', 'PingFang SC', sans-serif" },
  extraCssText: 'border-radius:4px;box-shadow:0 0 18px rgba(34,228,255,.18);backdrop-filter:blur(6px);',
}

export function useChart(el: Ref<HTMLElement | null>, onReady?: (c: ECharts) => void, onResize?: (c: ECharts) => void) {
  const chart = shallowRef<ECharts | null>(null)
  let ro: ResizeObserver | null = null
  let timer: ReturnType<typeof setTimeout> | null = null

  onMounted(() => {
    if (!el.value) return
    const dpr = Math.min(2.5, Math.max(1, (window.devicePixelRatio || 1) * Math.max(1, screenScale.value)))
    const c = echarts.init(el.value, undefined, { renderer: 'canvas', devicePixelRatio: dpr })
    chart.value = c
    ro = new ResizeObserver(() => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => {
        if (!chart.value || chart.value.isDisposed()) return
        chart.value.resize()
        onResize?.(chart.value)
      }, 150)
    })
    ro.observe(el.value)
    onReady?.(c)
  })

  onBeforeUnmount(() => {
    if (timer) clearTimeout(timer)
    ro?.disconnect()
    chart.value?.dispose()
    chart.value = null
  })

  return chart
}
