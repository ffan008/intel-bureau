<script setup lang="ts">
/** 头条情报轮播（§4.4）：每 6 秒切换；解码标题；点击打开右侧抽屉。悬停暂停。 */
import { computed, ref, watch } from 'vue'
import type { IntelItemDTO } from '@/api/types'
import { live } from '@/stores/live'
import { fx } from '@/stores/fx'
import { useInterval } from '@/composables/useTimers'
import { categoryColor } from '@/utils/meta'
import HudPanel from '../hud/HudPanel.vue'
import HeadlineCard from './HeadlineCard.vue'

const emit = defineEmits<{ open: [item: IntelItemDTO] }>()
const items = computed(() => (live.overview?.headlines ?? []).slice(0, 5))
const idx = ref(0)
const paused = ref(false)
const cur = computed(() => items.value[idx.value] ?? null)
watch(items, (xs) => { if (idx.value >= xs.length) idx.value = 0 })

const go = (i: number) => { if (items.value.length) idx.value = (i + items.value.length) % items.value.length }
// 特效「关」时不自动轮播（停止所有循环），仍可点击右侧列表切换
const timer = useInterval(() => { if (!paused.value && fx.loops) go(idx.value + 1) }, () => 6000)
function pick(i: number): void { go(i); timer.restart() }
</script>

<template>
  <HudPanel title="头条情报" code="HEADLINES · TOP 5" :index="5">
    <template #actions>
      <span v-if="live.overview?.latest_report" class="rep">{{ live.overview.latest_report.date_label }}</span>
      <span class="pager num">{{ items.length ? idx + 1 : 0 }}<em>/{{ items.length }}</em></span>
    </template>
    <div v-if="cur" class="wrap" @mouseenter="paused = true" @mouseleave="paused = false">
      <div class="card">
        <Transition name="slide" mode="out-in">
          <HeadlineCard :key="cur.id" :item="cur" @open="emit('open', cur)" />
        </Transition>
      </div>
      <ol class="queue">
        <li v-for="(h, i) in items" :key="h.id" :class="{ on: i === idx }">
          <button class="q" :style="{ '--cc': categoryColor(h.category) }" @click="pick(i)">
            <span class="n num">{{ i + 1 }}</span>
            <span class="t ellipsis">{{ h.title }}</span>
            <span class="s num">{{ h.score.toFixed(1) }}</span>
            <span v-if="i === idx" :key="`p${idx}`" class="prog" :class="{ run: fx.loops && !paused }" aria-hidden="true" />
          </button>
        </li>
      </ol>
    </div>
    <div v-else class="empty"><span class="code">NO HEADLINES</span>最近一份报告还没有头条情报</div>
  </HudPanel>
</template>

<style scoped>
.rep { font-size: 11px; color: var(--text-2); }
.pager { font-size: 13px; color: var(--cyan); }
.pager em { font-style: normal; color: var(--text-2); font-size: 11px; }
.wrap { display: grid; grid-template-columns: 1fr 268px; gap: 12px; height: 100%; }
.card { position: relative; min-width: 0; overflow: hidden; }
.queue { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; justify-content: space-between; }
.q { position: relative; display: grid; grid-template-columns: 14px 1fr 28px; align-items: center; gap: 8px; width: 100%; height: 22px; padding: 0 8px; font-size: 12px; text-align: left; color: var(--text-2); border-left: 2px solid transparent; overflow: hidden; }
.q:hover { color: var(--text-0); background: rgba(34, 228, 255, 0.04); }
.on .q { color: var(--text-0); border-left-color: var(--cc); background: linear-gradient(90deg, color-mix(in srgb, var(--cc) 14%, transparent), transparent); }
.n { font-size: 11px; }
.on .n { color: var(--cc); }
.s { text-align: right; font-size: 11px; }
.prog { position: absolute; left: 0; right: 0; bottom: 0; height: 1px; background: var(--cc); transform-origin: left; transform: scaleX(0); box-shadow: 0 0 6px var(--cc); }
.prog.run { animation: kf-prog 6s linear forwards; }
@keyframes kf-prog { from { transform: scaleX(0); } to { transform: scaleX(1); } }
.slide-enter-active, .slide-leave-active { transition: opacity 0.32s, transform 0.42s var(--ease-out-expo); }
.slide-enter-from { opacity: 0; transform: translateX(36px); }
.slide-leave-to { opacity: 0; transform: translateX(-36px); }
</style>
