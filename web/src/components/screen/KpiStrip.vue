<script setup lang="ts">
/** KPI 条（§4.2）：今日消息、今日情报、活跃群（x/白名单数）、信噪比、上升信号 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { toPercent } from '@/utils/format'
import KpiTile from './KpiTile.vue'

const ov = computed(() => live.overview)
const k = computed(() => ov.value?.kpis)
const hourly = computed(() => (ov.value?.stats.hourly ?? []).map((h) => h.wechat + h.qq + h.feishu + h.demo))
const groupBars = computed(() => (ov.value?.stats.top_groups ?? []).map((g) => g.messages))
const risingSum = computed(() => {
  const r = ov.value?.stats.rising ?? []
  return r.length ? Array.from({ length: 7 }, (_, i) => r.reduce((a, x) => a + (x.spark[i] ?? 0), 0)) : []
})
const topZ = computed(() => ov.value?.stats.rising[0])
</script>

<template>
  <div class="kpis">
    <KpiTile :index="0" label="今日消息" code="MESSAGES · 24H" :value="k?.messages_24h ?? 0" unit="条" :delta="k?.messages_delta" :spark="hourly" color="#22e4ff" />
    <KpiTile :index="1" label="今日情报" code="INTEL" :value="k?.intel_today ?? 0" unit="条" :delta="k?.intel_delta" :spark="live.intelTrend" color="#8b5cff" />
    <KpiTile :index="2" label="活跃群" code="ACTIVE GROUPS" :value="k?.groups_active ?? 0" :suffix="`/ ${k?.groups_whitelisted ?? 0}`" :note="`白名单 ${k?.groups_whitelisted ?? 0} 群 · 各群消息量`" :spark="groupBars" spark-bars color="#2bd96b" />
    <KpiTile :index="3" label="信噪比" code="SIGNAL / NOISE" :value="toPercent(k?.snr ?? 0)" :decimals="1" unit="%" :note="`有效 ${(ov?.stats.messages_clean ?? 0).toLocaleString('en-US')} / ${(ov?.stats.messages_raw ?? 0).toLocaleString('en-US')}`" :gauge="toPercent(k?.snr ?? 0) / 100" color="#ffb020" />
    <KpiTile :index="4" label="上升信号" code="RISING · z≥2" :value="k?.signals_rising ?? 0" unit="个" :note="topZ ? `最高「${topZ.word}」z=${topZ.z.toFixed(1)}` : '暂无上升信号'" :spark="risingSum" color="#ff3db8" />
  </div>
</template>

<style scoped>
.kpis { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; height: 100%; }
</style>
