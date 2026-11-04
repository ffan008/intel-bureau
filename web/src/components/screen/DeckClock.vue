<script setup lang="ts">
/** 时钟（冒号每秒闪一次）+ 下次出报倒计时 */
import { computed } from 'vue'
import { useNow } from '@/composables/useTimers'
import { WEEK_CN, fmtCountdown, zoned } from '@/utils/format'
import { live } from '@/stores/live'

const now = useNow()
const z = computed(() => zoned(now.value)!)
const p2 = (n: number) => String(n).padStart(2, '0')
const next = computed(() => live.overview?.kpis.next_run_at)
const countdown = computed(() => (next.value ? fmtCountdown(new Date(next.value).getTime() - now.value) : '--:--:--'))
</script>

<template>
  <div class="clock">
    <div class="t num">
      <span>{{ p2(z.h) }}</span><span class="colon fx-loop" :key="now">:</span><span>{{ p2(z.mi) }}</span><span class="sec">{{ p2(z.s) }}</span>
    </div>
    <div class="meta">
      <span class="num date">{{ z.y }}.{{ p2(z.mo) }}.{{ p2(z.d) }} {{ WEEK_CN[z.wd] }}</span>
      <span class="cd">下次出报 <b class="num">{{ countdown }}</b></span>
    </div>
  </div>
</template>

<style scoped>
.clock { display: flex; align-items: center; gap: 12px; }
.t { display: flex; align-items: baseline; font-size: 30px; font-weight: 600; color: var(--text-0); letter-spacing: 1px; text-shadow: 0 0 12px rgba(34, 228, 255, 0.35); line-height: 1; }
.colon { display: inline-block; margin: 0 1px; color: var(--cyan); animation: kf-colon 1s steps(1) 1 both; }
.sec { font-size: 14px; margin-left: 5px; color: var(--text-2); font-weight: 400; }
.meta { display: flex; flex-direction: column; gap: 3px; }
.date { font-size: 11px; color: var(--text-2); letter-spacing: 0.5px; }
.cd { font-size: 12px; color: var(--text-1); white-space: nowrap; }
.cd b { color: var(--amber); font-weight: 600; font-size: 13px; text-shadow: 0 0 8px rgba(255, 176, 32, 0.4); }
@keyframes kf-colon { 0% { opacity: 1; } 50% { opacity: 0.15; } }
</style>
