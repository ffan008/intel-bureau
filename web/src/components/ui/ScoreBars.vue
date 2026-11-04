<script setup lang="ts">
/** 5 维评分小条（0~5）。宽度用 scaleX 过渡。 */
import type { IntelItemDTO } from '@/api/types'
import { SCORE_DIMS } from '@/utils/meta'

withDefaults(defineProps<{ scores: IntelItemDTO['scores']; color?: string; compact?: boolean }>(), { color: 'var(--cyan)', compact: false })
const pct = (v: number) => Math.max(0, Math.min(1, (Number(v) || 0) / 5))
</script>

<template>
  <div class="sb" :class="{ compact }">
    <div v-for="d in SCORE_DIMS" :key="d.key" class="r">
      <span class="k">{{ d.label }}</span>
      <span class="track"><i :style="{ transform: `scaleX(${pct(scores[d.key])})`, background: color }" /></span>
      <span class="v num">{{ (Number(scores[d.key]) || 0).toFixed(1) }}</span>
    </div>
  </div>
</template>

<style scoped>
.sb { display: flex; flex-direction: column; gap: 5px; }
.r { display: grid; grid-template-columns: 40px 1fr 26px; align-items: center; gap: 8px; }
.k { font-size: 11.5px; color: var(--text-2); }
.track { position: relative; height: 4px; background: rgba(80, 200, 255, 0.1); border-radius: 2px; overflow: hidden; }
.track i {
  position: absolute;
  inset: 0;
  transform-origin: left center;
  border-radius: 2px;
  box-shadow: 0 0 6px currentColor;
  transition: transform 0.8s var(--ease-out-expo);
}
.v { font-size: 11px; color: var(--text-1); text-align: right; }
.compact { gap: 3px; }
.compact .r { grid-template-columns: 34px 1fr 22px; gap: 6px; line-height: 12px; }
.compact .k { font-size: 11px; }
.compact .track { height: 3px; }
.compact .v { font-size: 10.5px; }
</style>
