<script setup lang="ts">
/** 推送回执与算力（§4.7）：每个通道一行（图标/名称/✓✗/时间）；Token 输入·输出·费用滚动数字 + 预算环；模型名与云端同意 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { SP, readFirst } from '@/api/settingsPaths'
import { channelColor } from '@/utils/meta'
import { fmtTime } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import RollNum from '../ui/RollNum.vue'
import Icon from '../Icon.vue'
import type { IconName } from '../icons'

const ICON = (kind: string): IconName =>
  kind.startsWith('feishu') ? 'feishu' : kind.startsWith('qq') ? 'qq' : kind.startsWith('email') ? 'mail' : kind === 'local_archive' ? 'archive' : 'wechat'

const rows = computed(() => {
  const ids = new Set(Object.keys(live.receipts))
  return live.channels
    .filter((c) => c.enabled || ids.has(c.id))
    .map((c) => {
      const r = live.receipts[c.id]
      const res = r ? { ok: r.ok, at: r.at, detail: r.detail } : c.last_result ? { ok: c.last_result.ok, at: c.last_result.at, detail: c.last_result.detail } : null
      return { id: c.id, name: c.name, kind: c.kind, res, fresh: !!r }
    })
    .slice(0, 4)
})
const more = computed(() => Math.max(0, live.channels.filter((c) => c.enabled).length - 4))

const run = computed(() => live.run)
const metric = (k: string) => {
  let v = 0
  for (const s of run.value?.stages ?? []) { const x = Number(s.metrics?.[k]); if (Number.isFinite(x)) v = Math.max(v, x) }
  return v
}
const tokensIn = computed(() => Math.max(run.value?.totals.tokens_in ?? 0, metric('tokens_in')))
const tokensOut = computed(() => Math.max(run.value?.totals.tokens_out ?? 0, metric('tokens_out')))
const cost = computed(() => run.value?.totals.cost_cny ?? 0)
const maxChunks = computed(() => Number(readFirst(live.settings, SP.llmMaxChunks, 40)) || 40)
const chunks = computed(() => Math.max(metric('chunks_done'), run.value?.totals.chunks ?? 0))
const ratio = computed(() => Math.min(1, chunks.value / maxChunks.value))
const R = 30
/** 预算环：直接画弧线（不对 stroke-dashoffset 做过渡，动画只用 transform/opacity） */
const arc = computed(() => {
  const r = Math.min(0.9999, ratio.value)
  const a = r * 2 * Math.PI - Math.PI / 2
  const x = 36 + R * Math.cos(a), y = 36 + R * Math.sin(a)
  return `M36 ${36 - R} A${R} ${R} 0 ${r > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)}`
})
const llm = computed(() => live.overview?.llm)
</script>

<template>
  <HudPanel title="推送回执与算力" code="DELIVERY · COMPUTE" :index="8">
    <div class="wrap">
      <ul class="chs">
        <li v-for="r in rows" :key="r.id" :class="{ fresh: r.fresh }" :title="r.res?.detail">
          <span class="ic" :style="{ color: channelColor(r.kind) }"><Icon :name="ICON(r.kind)" :size="14" /></span>
          <span class="nm ellipsis">{{ r.name }}</span>
          <span v-if="r.res" class="res" :class="r.res.ok ? 'ok' : 'bad'">{{ r.res.ok ? '✓' : '✗' }}</span>
          <span v-else class="res none">—</span>
          <span class="t num">{{ r.res ? fmtTime(r.res.at, false) : '--:--' }}</span>
        </li>
        <li v-if="!rows.length" class="empty-row">尚未配置推送通道</li>
        <li v-if="more" class="more">还有 {{ more }} 个通道</li>
      </ul>
      <div class="cmp">
        <div class="ring" :title="`本次已用 ${chunks} / ${maxChunks} 块预算`">
          <svg viewBox="0 0 72 72" aria-hidden="true">
            <circle cx="36" cy="36" :r="R" class="track" />
            <path v-if="ratio > 0" :d="arc" class="val" />
            <circle cx="36" cy="36" r="24" class="inner" />
          </svg>
          <div class="pct"><b class="num">{{ Math.round(ratio * 100) }}</b><em>%</em><span>预算</span></div>
        </div>
        <dl class="tok">
          <div><dt>输入</dt><dd><RollNum :value="tokensIn" /></dd></div>
          <div><dt>输出</dt><dd><RollNum :value="tokensOut" /></dd></div>
          <div><dt>费用</dt><dd class="cny"><RollNum :value="cost" :decimals="2" prefix="¥" /></dd></div>
        </dl>
      </div>
    </div>
    <div class="foot">
      <span class="model"><Icon name="agents" :size="13" />{{ llm?.model || llm?.provider || '未配置模型' }}</span>
      <span v-if="llm?.cloud_consent" class="badge green">云端已同意</span>
      <span v-else class="badge amber disp offline">离线模式</span>
      <span class="spacer" />
      <span class="today">今日 <b class="num">{{ ((llm?.tokens_today ?? 0) / 1000).toFixed(1) }}k</b> tokens · <b class="num">¥{{ (llm?.cost_today_cny ?? 0).toFixed(2) }}</b></span>
    </div>
  </HudPanel>
</template>

<style scoped>
.wrap { display: grid; grid-template-columns: 1fr 196px; gap: 12px; height: calc(100% - 26px); }
.chs { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.chs li { display: grid; grid-template-columns: 16px 1fr 14px 38px; align-items: center; gap: 7px; height: 20px; font-size: 12px; }
.chs li.fresh { background: linear-gradient(90deg, rgba(43, 255, 154, 0.08), transparent); }
.ic { display: flex; }
.nm { color: var(--text-1); }
.res { font-weight: 700; text-align: center; }
.res.ok { color: var(--green); text-shadow: 0 0 6px var(--green); }
.res.bad { color: var(--red); text-shadow: 0 0 6px var(--red); }
.res.none { color: var(--text-2); }
.t { font-size: 11px; color: var(--text-2); text-align: right; }
.empty-row, .more { font-size: 11.5px; color: var(--text-2); display: block !important; }
.cmp { display: flex; align-items: center; gap: 10px; padding-left: 12px; border-left: 1px solid rgba(80, 200, 255, 0.1); }
.ring { position: relative; width: 70px; height: 70px; flex: none; }
.ring svg { width: 100%; height: 100%; }
.track { fill: none; stroke: rgba(80, 200, 255, 0.1); stroke-width: 5; }
.val { fill: none; stroke: var(--cyan); stroke-width: 5; stroke-linecap: round; filter: drop-shadow(0 0 4px var(--cyan)); }
.inner { fill: none; stroke: rgba(34, 228, 255, 0.2); stroke-dasharray: 1 3; }
.pct { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; line-height: 1; }
.pct b { font-size: 16px; color: var(--text-0); }
.pct em { position: absolute; top: 22px; right: 14px; font-style: normal; font-size: 9px; color: var(--text-2); }
.pct span { font-size: 9.5px; color: var(--text-2); margin-top: 3px; }
.tok { margin: 0; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.tok div { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
.tok dt { font-size: 11px; color: var(--text-2); }
.tok dd { margin: 0; font-size: 13px; color: var(--text-0); }
.tok dd.cny { color: var(--amber); font-weight: 600; }
.foot { display: flex; align-items: center; gap: 8px; height: 26px; padding-top: 6px; border-top: 1px solid rgba(80, 200, 255, 0.08); font-size: 11.5px; }
.model { display: inline-flex; align-items: center; gap: 5px; color: var(--text-1); }
.offline { font-size: 9.5px; }
.spacer { flex: 1; }
.today { color: var(--text-2); }
.today b { color: var(--text-1); font-weight: 600; }
</style>
