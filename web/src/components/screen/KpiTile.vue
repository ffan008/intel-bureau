<script setup lang="ts">
/** KPI 翻牌（§4.2）：0 → 目标值 1.2s easeOutExpo；变化时数字闪亮；环比徽标；迷你 sparkline */
import { computed } from 'vue'
import { useCountUp } from '@/composables/useTextFx'
import { fmtDelta, fmtInt } from '@/utils/format'
import Sparkline from '../ui/Sparkline.vue'

const props = withDefaults(defineProps<{
  label: string; code: string; value: number; decimals?: number; unit?: string; suffix?: string
  delta?: number | null; deltaLabel?: string; note?: string; spark?: number[]; sparkBars?: boolean; color?: string; index?: number
  /** 0~1：比例类指标用刻度条代替 sparkline */
  gauge?: number
}>(), { decimals: 0, color: 'var(--cyan)', index: 0 })

const { display, flash } = useCountUp(() => props.value)
const shown = computed(() => (props.decimals ? display.value.toFixed(props.decimals) : fmtInt(display.value)))
const d = computed(() => fmtDelta(props.delta))
</script>

<template>
  <div class="kpi hud-enter" :style="{ '--k': color, animationDelay: 120 + index * 60 + 'ms' }">
    <span class="accent" aria-hidden="true" />
    <div class="head">
      <span class="lbl">{{ label }}</span>
      <span class="code disp">{{ code }}</span>
    </div>
    <div class="val">
      <span class="n num" :class="{ big: !suffix }">{{ shown }}</span>
      <span v-if="suffix" class="suffix num">{{ suffix }}</span>
      <span v-if="unit" class="unit">{{ unit }}</span>
      <span :key="flash" class="flash" :class="{ go: flash > 0 }" aria-hidden="true" />
    </div>
    <div class="foot">
      <span v-if="d" class="delta" :class="d.dir">{{ d.dir === 'up' ? '▲' : d.dir === 'down' ? '▼' : '■' }} {{ d.text }}<em>{{ deltaLabel ?? '较上期' }}</em></span>
      <span v-else-if="note" class="note">{{ note }}</span>
    </div>
    <div class="spark">
      <div v-if="gauge !== undefined" class="gauge" aria-hidden="true">
        <i :style="{ transform: `scaleX(${Math.max(0, Math.min(1, gauge))})` }" />
        <em v-for="t in 9" :key="t" :style="{ left: t * 10 + '%' }" />
      </div>
      <Sparkline v-else-if="spark?.length" :values="spark" :width="156" :height="20" :color="color" :bars="sparkBars" :dot="!sparkBars" />
    </div>
  </div>
</template>

<style scoped>
.kpi {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  padding: 9px 14px 7px;
  background: linear-gradient(180deg, color-mix(in srgb, var(--k) 8%, transparent), rgba(10, 22, 46, 0.5) 60%);
  border: 1px solid var(--line);
  border-radius: 2px;
  backdrop-filter: blur(10px);
  overflow: hidden;
}
.accent { position: absolute; left: 0; top: 0; width: 34px; height: 2px; background: var(--k); box-shadow: 0 0 10px var(--k); }
.accent::after { content: ''; position: absolute; right: -2px; top: 0; width: 2px; height: 8px; background: var(--k); }
.head { display: flex; align-items: baseline; justify-content: space-between; gap: 6px; }
.lbl { font-size: 13px; color: var(--text-1); white-space: nowrap; }
.code { font-size: 8.5px; letter-spacing: 1.5px; color: var(--text-2); white-space: nowrap; }
.val { position: relative; display: flex; align-items: baseline; gap: 4px; margin-top: 1px; height: 36px; }
.n { font-size: 30px; font-weight: 600; color: var(--text-0); letter-spacing: -0.5px; line-height: 36px; text-shadow: 0 0 14px color-mix(in srgb, var(--k) 55%, transparent); }
.suffix { font-size: 16px; color: var(--text-2); }
.unit { font-size: 12px; color: var(--text-2); margin-left: 2px; }
.flash { position: absolute; left: -6px; right: 30%; top: 4px; bottom: 2px; background: radial-gradient(ellipse at 30% 50%, color-mix(in srgb, var(--k) 45%, transparent), transparent 70%); opacity: 0; pointer-events: none; }
.flash.go { animation: kf-flash 0.9s ease-out 1; }
.foot { height: 16px; display: flex; align-items: center; }
.delta { font-size: 11.5px; font-family: var(--font-num); white-space: nowrap; }
.delta em { font-style: normal; font-family: var(--font-cn); color: var(--text-2); margin-left: 5px; font-size: 11px; }
.delta.up { color: var(--green); }
.delta.down { color: var(--red); }
.delta.flat { color: var(--text-2); }
.note { font-size: 11px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.spark { margin-top: auto; height: 20px; opacity: 0.9; display: flex; align-items: flex-end; }
.gauge { position: relative; width: 100%; height: 6px; margin-bottom: 4px; background: rgba(255, 176, 32, 0.12); border-radius: 1px; overflow: hidden; }
.gauge i { position: absolute; inset: 0; transform-origin: left; background: linear-gradient(90deg, rgba(255, 176, 32, 0.5), var(--k)); box-shadow: 0 0 8px var(--k); transition: transform 1.2s var(--ease-out-expo); }
.gauge em { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(3, 6, 15, 0.85); }
</style>
