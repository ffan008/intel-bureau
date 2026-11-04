<script setup lang="ts">
/** 上升信号（§4.8）：最多 6 行，关键词 / 今日次数 / z 值 / 7 日迷你折线 / 来源群，按 z 降序 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import HudPanel from '../hud/HudPanel.vue'
import Sparkline from '../ui/Sparkline.vue'

const rows = computed(() => [...(live.overview?.stats.rising ?? [])].sort((a, b) => b.z - a.z).slice(0, 6))
const zColor = (z: number) => (z >= 3 ? '#ff3db8' : z >= 2 ? '#ffb020' : '#22e4ff')
</script>

<template>
  <HudPanel title="上升信号" code="RISING SIGNALS · z" :index="11">
    <template #actions><span class="hint">对比 7 日基线</span></template>
    <div class="tbl-r">
      <div class="hd">
        <span>#</span><span>关键词</span><span class="r">今日</span><span class="r">7日均</span><span class="c">z 值</span><span>7 日走势</span><span>主要来源</span>
      </div>
      <div v-for="(r, i) in rows" :key="r.word" class="rw" :style="{ '--z': zColor(r.z) }">
        <span class="rk num">{{ i + 1 }}</span>
        <span class="w ellipsis" :title="r.word">{{ r.word }}</span>
        <span class="r num td">{{ r.today }}</span>
        <span class="r num av">{{ r.avg7.toFixed(1) }}</span>
        <span class="c"><b class="zb num">{{ r.z >= 0 ? '+' : '' }}{{ r.z.toFixed(1) }}σ</b></span>
        <span class="sp"><Sparkline :values="r.spark" :width="104" :height="18" :color="zColor(r.z)" /></span>
        <span class="g ellipsis" :title="r.groups.join('、')">{{ r.groups.join(' · ') }}</span>
      </div>
      <div v-if="!rows.length" class="empty"><span class="code">FLAT</span>今天没有明显上升的关键词</div>
    </div>
  </HudPanel>
</template>

<style scoped>
.hint { font-size: 10.5px; color: var(--text-2); }
.tbl-r { display: flex; flex-direction: column; height: 100%; }
.hd, .rw { display: grid; grid-template-columns: 16px minmax(0, 1.1fr) 38px 42px 58px 108px minmax(0, 1.3fr); align-items: center; gap: 8px; }
.hd { height: 20px; font-size: 10.5px; color: var(--text-2); border-bottom: 1px solid rgba(80, 200, 255, 0.1); }
.rw { flex: 1; min-height: 0; font-size: 12.5px; border-bottom: 1px dashed rgba(80, 200, 255, 0.06); }
.r { text-align: right; }
.c { text-align: center; }
.rk { font-size: 11px; color: var(--text-2); }
.w { color: var(--text-0); font-weight: 600; }
.td { color: var(--z); font-weight: 600; font-size: 13px; }
.av { color: var(--text-2); font-size: 11.5px; }
.zb { display: inline-block; min-width: 50px; padding: 1px 5px; font-size: 11px; font-weight: 600; color: var(--z); border: 1px solid color-mix(in srgb, var(--z) 55%, transparent); background: color-mix(in srgb, var(--z) 12%, transparent); border-radius: 2px; text-shadow: 0 0 6px var(--z); }
.sp { display: flex; align-items: center; }
.g { font-size: 11.5px; color: var(--text-2); }
</style>
