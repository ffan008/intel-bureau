<script setup lang="ts">
/** 情报源矩阵：三平台的适配器、健康、白名单群、24h 消息、最近采集；实时上报时整行闪一下 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { HEALTH, PLATFORM, REAL_PLATFORMS } from '@/utils/meta'
import { fmtAgo, fmtInt } from '@/utils/format'
import { useNow } from '@/composables/useTimers'
import HudPanel from '../hud/HudPanel.vue'
import PlatformIcon from '../ui/PlatformIcon.vue'

const now = useNow()
const rows = computed(() => REAL_PLATFORMS.map((p) => {
  const d = live.overview?.platforms.find((x) => x.platform === p)
  const health = d?.health ?? 'unconfigured'
  // 演示模式：数据是合成的，不显示「正常」，也不显示真实适配器名，免得误以为已经连上
  const demo = live.overview?.mode === 'demo' && (d?.groups_total ?? 0) > 0
  const adapter = demo ? '演示数据 · 未连接真实平台' : d?.adapters.find((a) => a.key === d.adapter)?.label ?? d?.adapter ?? '未配置'
  return { p, d, adapter, health, demo, label: demo ? '演示' : HEALTH[health].label, color: demo ? 'var(--demo)' : HEALTH[health].color }
}))
const pulse = (p: string) => now.value - (live.ingestPulse[p as 'qq'] ?? 0) < 1400
const total = computed(() => rows.value.reduce((a, r) => a + (r.d?.messages_24h ?? 0), 0))
</script>

<template>
  <HudPanel title="情报源矩阵" code="SOURCE MATRIX" :index="0">
    <template #actions><span class="sum num">{{ fmtInt(total) }}<em>条 / 24h</em></span></template>
    <div class="rows">
      <div v-for="r in rows" :key="r.p" class="row" :class="{ ping: pulse(r.p) }" :style="{ '--pc': PLATFORM[r.p].color }" :title="r.d?.hint ? `${r.d.detail}\n建议：${r.d.hint}` : r.d?.detail">
        <PlatformIcon :platform="r.p" :size="34" />
        <div class="id">
          <div class="nm">{{ PLATFORM[r.p].label }}<span class="hs" :style="{ color: r.color }"><i class="dot fx-loop" :class="{ 'lamp-ok': r.health === 'ok', 'lamp-down': r.health === 'down' && !r.demo }" />{{ r.label }}</span></div>
          <div class="ad ellipsis">{{ r.adapter }}</div>
        </div>
        <div class="m">
          <b class="num">{{ r.d?.groups_whitelisted ?? 0 }}<em>/{{ r.d?.groups_total ?? 0 }}</em></b>
          <span>白名单群</span>
        </div>
        <div class="m wide">
          <b class="num msg">{{ fmtInt(r.d?.messages_24h ?? 0) }}</b>
          <span>{{ r.d?.last_collect_at ? fmtAgo(r.d.last_collect_at, now) + '采集' : '未采集' }}</span>
        </div>
        <span class="flash" aria-hidden="true" />
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.sum { font-size: 13px; color: var(--cyan); }
.sum em { font-style: normal; font-family: var(--font-cn); font-size: 11px; color: var(--text-2); margin-left: 4px; }
.rows { display: flex; flex-direction: column; gap: 6px; height: 100%; }
.row {
  position: relative;
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 34px 1fr 66px 92px;
  align-items: center;
  gap: 10px;
  padding: 0 10px;
  background: linear-gradient(90deg, color-mix(in srgb, var(--pc) 10%, transparent), rgba(4, 12, 28, 0.35) 55%);
  border-left: 2px solid var(--pc);
  overflow: hidden;
}
.id { min-width: 0; }
.nm { display: flex; align-items: center; gap: 10px; font-size: 14px; color: var(--text-0); font-weight: 600; }
.hs { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 400; }
.hs .dot { width: 6px; height: 6px; }
.ad { font-size: 11px; color: var(--text-2); margin-top: 1px; }
.m { display: flex; flex-direction: column; align-items: flex-end; line-height: 1.2; }
.m b { font-size: 16px; color: var(--text-0); font-weight: 600; }
.m b em { font-style: normal; font-size: 11px; color: var(--text-2); font-weight: 400; }
.m b.msg { color: var(--pc); text-shadow: 0 0 10px color-mix(in srgb, var(--pc) 50%, transparent); }
.m span { font-size: 10.5px; color: var(--text-2); white-space: nowrap; }
.flash { position: absolute; inset: 0; background: linear-gradient(90deg, color-mix(in srgb, var(--pc) 30%, transparent), transparent 70%); opacity: 0; pointer-events: none; transition: opacity 0.9s ease-out; }
.row.ping .flash { opacity: 1; transition: opacity 0.08s; }
</style>
