<script setup lang="ts">
/** 消息构成：类型环形图（SVG）+ 图例 + 平台占比条 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { MSG_KIND_LABEL, PLATFORM, platformColor } from '@/utils/meta'
import { fmtCompact, fmtInt, toPercent } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'

const KIND_COLOR: Record<string, string> = { text: '#22e4ff', image: '#8b5cff', reply: '#4f9dff', link: '#2bff9a', sticker: '#ff3db8', card: '#ffb020', file: '#a9c4dd', video: '#ff8a4c', voice: '#6c86a3' }
const R = 46, C = 2 * Math.PI * R

const stats = computed(() => live.overview?.stats)
const segs = computed(() => {
  const xs = [...(stats.value?.msg_types ?? [])].sort((a, b) => b.count - a.count)
  const total = xs.reduce((a, x) => a + x.count, 0) || 1
  const main = xs.slice(0, 5)
  const rest = xs.slice(5).reduce((a, x) => a + x.count, 0)
  const list = rest ? [...main, { kind: 'other', count: rest }] : main
  let acc = 0
  return list.map((x) => {
    const len = (x.count / total) * C
    const s = { kind: x.kind, count: x.count, pct: x.count / total, dash: `${Math.max(0, len - 2)} ${C}`, offset: -acc, color: KIND_COLOR[x.kind] ?? '#6c86a3' }
    acc += len
    return s
  })
})
const plats = computed(() => {
  const xs = (stats.value?.by_platform ?? []).filter((p) => p.messages > 0)
  const t = xs.reduce((a, x) => a + x.messages, 0) || 1
  return xs.map((x) => ({ ...x, pct: x.messages / t }))
})
</script>

<template>
  <HudPanel title="消息构成" code="COMPOSITION" :index="2">
    <div class="wrap">
      <div class="donut">
        <svg viewBox="0 0 120 120" aria-hidden="true">
          <circle cx="60" cy="60" :r="R" fill="none" stroke="rgba(80,200,255,.08)" stroke-width="12" />
          <circle v-for="s in segs" :key="s.kind" cx="60" cy="60" :r="R" fill="none" :stroke="s.color" stroke-width="12"
            :stroke-dasharray="s.dash" :stroke-dashoffset="s.offset" transform="rotate(-90 60 60)" class="seg" />
          <circle cx="60" cy="60" r="35" fill="none" stroke="rgba(34,228,255,.25)" stroke-dasharray="1 3" />
        </svg>
        <div class="center">
          <b class="num">{{ fmtCompact(stats?.messages_raw ?? 0) }}</b>
          <span>原始消息</span>
          <em class="num">{{ toPercent(stats?.snr ?? 0).toFixed(1) }}% 有效</em>
        </div>
      </div>
      <ul class="legend">
        <li v-for="s in segs" :key="s.kind">
          <i :style="{ background: s.color, boxShadow: `0 0 6px ${s.color}` }" />
          <span class="k">{{ MSG_KIND_LABEL[s.kind] ?? s.kind }}</span>
          <span class="v num">{{ fmtInt(s.count) }}</span>
          <span class="p num">{{ (s.pct * 100).toFixed(1) }}%</span>
        </li>
      </ul>
    </div>
    <div class="plat">
      <div class="pbar">
        <i v-for="p in plats" :key="p.platform" :style="{ flexGrow: p.pct, background: platformColor(p.platform) }" />
      </div>
      <div class="plg">
        <span v-for="p in plats" :key="p.platform"><i :style="{ background: platformColor(p.platform) }" />{{ PLATFORM[p.platform].label }} <b class="num">{{ (p.pct * 100).toFixed(0) }}%</b></span>
        <span class="spk">发言人 <b class="num">{{ fmtInt(stats?.speakers ?? 0) }}</b></span>
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 132px 1fr; gap: 16px; align-items: center; height: calc(100% - 40px); }
.donut { position: relative; width: 132px; height: 132px; }
.donut svg { width: 100%; height: 100%; filter: drop-shadow(0 0 6px rgba(34, 228, 255, 0.2)); }
.seg { animation: kf-fade-in 0.8s ease-out both; }
.center { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1.2; }
.center b { font-size: 20px; color: var(--text-0); font-weight: 600; }
.center span { font-size: 10.5px; color: var(--text-2); }
.center em { font-style: normal; font-size: 10.5px; color: var(--amber); margin-top: 2px; }
.legend { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.legend li { display: grid; grid-template-columns: 8px 1fr auto 46px; align-items: center; gap: 8px; font-size: 12px; }
.legend i { width: 8px; height: 8px; border-radius: 1px; }
.k { color: var(--text-1); }
.v { color: var(--text-0); font-size: 11.5px; }
.p { color: var(--text-2); font-size: 11px; text-align: right; }
.plat { height: 40px; display: flex; flex-direction: column; justify-content: flex-end; gap: 6px; }
.pbar { display: flex; gap: 2px; height: 6px; }
.pbar i { display: block; height: 100%; flex-basis: 0; border-radius: 1px; opacity: 0.85; box-shadow: 0 0 6px currentColor; }
.plg { display: flex; gap: 14px; font-size: 11.5px; color: var(--text-2); }
.plg i { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 5px; vertical-align: 1px; }
.plg b { color: var(--text-0); font-weight: 600; margin-left: 2px; }
.plg .spk { margin-left: auto; }
</style>
