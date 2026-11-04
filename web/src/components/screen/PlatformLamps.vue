<script setup lang="ts">
/** 三平台连接灯（§4.1）：ok 绿色呼吸、degraded 黄、down 红闪、disabled/unconfigured 灰；悬停显示 detail + hint */
import { computed } from 'vue'
import type { PlatformDTO } from '@/api/types'
import { HEALTH, PLATFORM, REAL_PLATFORMS } from '@/utils/meta'
import { fmtAgo } from '@/utils/format'
import { useNow } from '@/composables/useTimers'
import { live } from '@/stores/live'

const now = useNow()
/** 演示模式下显示「演示」而不是「正常」：数据是合成的，真实平台并没有连上 */
const items = computed(() => REAL_PLATFORMS.map((p) => {
  const d = live.overview?.platforms.find((x) => x.platform === p)
  const health = (d?.health ?? 'unconfigured') as PlatformDTO['health']
  const demo = live.overview?.mode === 'demo' && (d?.groups_total ?? 0) > 0
  return { p, d, health, demo, cls: demo ? 'h-demo' : `h-${health}`,
    label: demo ? '演示' : HEALTH[health].label, color: demo ? 'var(--demo)' : HEALTH[health].color }
}))
const pulse = (p: string) => now.value - (live.ingestPulse[p as 'qq'] ?? 0) < 1600
</script>

<template>
  <div class="lamps">
    <div v-for="it in items" :key="it.p" class="lamp" :class="it.cls" tabindex="0" :aria-label="`${PLATFORM[it.p].label}：${it.label}`">
      <span class="bar" :style="{ background: PLATFORM[it.p].color }" />
      <span class="name">{{ PLATFORM[it.p].label }}</span>
      <span class="led fx-loop" :class="{ 'lamp-ok': it.health === 'ok', 'lamp-down': it.health === 'down' && !it.demo }" />
      <span class="st">{{ it.label }}</span>
      <span class="ping" :class="{ on: pulse(it.p) }" aria-hidden="true" />
      <div class="tip" role="tooltip">
        <div class="t1"><b>{{ PLATFORM[it.p].label }}</b><span :style="{ color: it.color }">{{ it.label }}</span></div>
        <div class="t2">{{ it.d?.detail ?? '未配置采集适配器' }}</div>
        <div v-if="it.d?.hint" class="t3">建议：{{ it.d.hint }}</div>
        <div class="t4 num">{{ it.d?.adapter }} · 检查于 {{ fmtAgo(it.d?.checked_at, now) }}</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.lamps { display: flex; gap: 8px; }
.lamp {
  position: relative;
  display: flex;
  align-items: center;
  gap: 7px;
  height: 28px;
  padding: 0 10px 0 0;
  border: 1px solid rgba(80, 200, 255, 0.16);
  background: rgba(4, 12, 28, 0.6);
  border-radius: 14px;
  overflow: visible;
  cursor: default;
  outline: none;
}
.lamp:hover, .lamp:focus-visible { border-color: var(--line-strong); }
.bar { width: 3px; height: 14px; border-radius: 2px; margin-left: 10px; box-shadow: 0 0 6px currentColor; }
.name { font-size: 12.5px; color: var(--text-0); }
.led { width: 8px; height: 8px; border-radius: 50%; background: currentColor; box-shadow: 0 0 8px currentColor, 0 0 2px #fff inset; }
.st { font-size: 11.5px; color: currentColor; }
.h-disabled .st, .h-unconfigured .st { color: var(--text-2); }
.h-demo { color: var(--demo); }
.ping { position: absolute; right: -2px; top: -2px; width: 6px; height: 6px; border-radius: 50%; background: var(--cyan); opacity: 0; transition: opacity 0.2s; }
.ping.on { opacity: 1; box-shadow: 0 0 8px var(--cyan); }
.tip {
  position: absolute;
  top: calc(100% + 10px);
  left: 50%;
  z-index: 50;
  width: 300px;
  padding: 10px 12px;
  background: rgba(6, 14, 32, 0.97);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  box-shadow: var(--shadow-pop);
  opacity: 0;
  pointer-events: none;
  transform: translate(-50%, -4px);
  transition: opacity var(--t-fast), transform var(--t-fast);
  color: var(--text-1);
}
.lamp:hover .tip, .lamp:focus-visible .tip { opacity: 1; transform: translate(-50%, 0); }
.t1 { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 4px; }
.t1 b { color: var(--text-0); }
.t2 { font-size: 12px; line-height: 1.6; }
.t3 { margin-top: 6px; font-size: 12px; line-height: 1.6; color: var(--amber); }
.t4 { margin-top: 6px; font-size: 10.5px; color: var(--text-2); }
</style>
