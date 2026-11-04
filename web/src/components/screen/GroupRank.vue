<script setup lang="ts">
/** 群热度排行：前 9 名，热度条用 scaleX */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { platformColor, platformLabel } from '@/utils/meta'
import { fmtInt } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'

const rows = computed(() => {
  const g = [...(live.overview?.stats.top_groups ?? [])].sort((a, b) => b.heat - a.heat).slice(0, 9)
  const max = Math.max(1, ...g.map((x) => x.heat))
  return g.map((x) => ({ ...x, pct: x.heat / max }))
})
</script>

<template>
  <HudPanel title="群热度排行" code="GROUP HEAT" :index="1">
    <template #actions><span class="hint">消息 · 发言人 · 热度</span></template>
    <ol v-if="rows.length" class="list">
      <li v-for="(g, i) in rows" :key="g.group_key" class="it" :class="{ top: i < 3 }" :style="{ '--pc': platformColor(g.platform) }">
        <span class="rk num">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="pd" :title="platformLabel(g.platform)" />
        <span class="nm ellipsis" :title="g.name">{{ g.name }}</span>
        <span class="ms num">{{ fmtInt(g.messages) }}</span>
        <span class="sp num">{{ g.speakers }}<em>人</em></span>
        <span class="bar"><i :style="{ transform: `scaleX(${g.pct})` }" /></span>
        <span class="ht num">{{ g.heat }}</span>
      </li>
    </ol>
    <div v-else class="empty"><span class="code">NO DATA</span>还没有群消息</div>
  </HudPanel>
</template>

<style scoped>
.hint { font-size: 10.5px; color: var(--text-2); }
.list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; height: 100%; justify-content: space-between; }
.it { display: grid; grid-template-columns: 22px 6px minmax(0, 1fr) 46px 40px 74px 26px; align-items: center; gap: 8px; height: 24px; font-size: 12.5px; }
.rk { font-size: 11px; color: var(--text-2); }
.it.top .rk { color: var(--cyan); text-shadow: 0 0 8px rgba(34, 228, 255, 0.6); font-weight: 600; }
.pd { width: 6px; height: 6px; border-radius: 50%; background: var(--pc); box-shadow: 0 0 6px var(--pc); }
.nm { color: var(--text-0); }
.ms { text-align: right; color: var(--text-1); font-size: 12px; }
.sp { text-align: right; color: var(--text-2); font-size: 11.5px; }
.sp em { font-style: normal; font-size: 10px; margin-left: 1px; font-family: var(--font-cn); }
.bar { position: relative; height: 4px; background: rgba(80, 200, 255, 0.08); border-radius: 2px; overflow: hidden; }
.bar i { position: absolute; inset: 0; transform-origin: left; background: linear-gradient(90deg, color-mix(in srgb, var(--pc) 35%, transparent), var(--pc)); box-shadow: 0 0 6px var(--pc); transition: transform 1s var(--ease-out-expo); }
.ht { text-align: right; font-size: 11.5px; color: var(--text-0); }
</style>
