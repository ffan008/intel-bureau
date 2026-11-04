<script setup lang="ts">
/**
 * 作战日志终端（§4.6）：黑底、等宽 12px；`[08:00:13] DECODER ▸ …`；
 * 新行逐字出现（每字 8ms），积压超过 20 行时整行显示；按级别着色；末尾闪烁光标；最多 200 行。
 */
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { live, type TermLine } from '@/stores/live'
import { fx } from '@/stores/fx'
import { fmtTime } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'

const MS_PER_CHAR = 8
const BACKLOG = 20
/** id ≤ doneId 的行已完整显示；curId 行显示前 curChars 个字；其后的行还没出现 */
const doneId = ref(0)
const curId = ref(0)
const curChars = ref(0)
const box = ref<HTMLElement | null>(null)
const stick = ref(true)
let raf = 0
let lastT = 0

const chars = (l: TermLine) => [...l.text]

function advance(t: number): void {
  raf = 0
  const queue = live.log.filter((l) => l.id > doneId.value)
  if (!queue.length) return
  // 历史行、特效关、积压超过 20 行：整行显示
  if (!fx.textFx || queue.length > BACKLOG || queue.every((l) => l.instant)) {
    doneId.value = queue[queue.length - 1]!.id
    curId.value = 0
    scroll()
    return
  }
  const head = queue[0]!
  if (head.instant || head.sep) { doneId.value = head.id; raf = requestAnimationFrame(advance); return }
  if (curId.value !== head.id) { curId.value = head.id; curChars.value = 0 }
  const dt = lastT ? Math.min(64, t - lastT) : 16
  lastT = t
  curChars.value += Math.max(1, Math.round(dt / MS_PER_CHAR))
  if (curChars.value >= chars(head).length) { doneId.value = head.id; curId.value = 0 }
  scroll()
  raf = requestAnimationFrame(advance)
}
function kick(): void {
  if (!raf) { lastT = 0; raf = requestAnimationFrame(advance) }
}

watch(() => live.log.length, () => kick(), { immediate: true })
onBeforeUnmount(() => cancelAnimationFrame(raf))

function scroll(): void {
  if (!stick.value) return
  void nextTick(() => { if (box.value) box.value.scrollTop = box.value.scrollHeight })
}
function onScroll(): void {
  const b = box.value
  if (b) stick.value = b.scrollHeight - b.scrollTop - b.clientHeight < 24
}
const lines = computed(() => live.log.filter((l) => l.id <= doneId.value || l.id === curId.value))
const text = (l: TermLine) => (l.id === curId.value ? chars(l).slice(0, curChars.value).join('') : l.text)
const typing = (l: TermLine) => l.id === curId.value
</script>

<template>
  <HudPanel title="作战日志" code="OPS TERMINAL" :index="7" flush>
    <template #actions>
      <span class="cnt num">{{ live.log.length }}<em>/200</em></span>
      <button v-if="!stick" class="btn sm ghost" @click="stick = true; scroll()">回到底部</button>
    </template>
    <div class="term">
      <div ref="box" class="scroll" role="log" aria-live="off" @scroll="onScroll">
        <div v-if="!live.log.length" class="ln dim">[{{ fmtTime(Date.now()) }}] SYSTEM ▸ 终端就绪，等待作战指令</div>
        <template v-for="l in lines" :key="l.id">
          <div v-if="l.sep" class="sep"><span>{{ l.text }}</span></div>
          <div v-else class="ln" :class="l.level">
            <span class="ts">[{{ fmtTime(l.ts) }}]</span>
            <span class="ag">{{ l.agent }}</span>
            <span class="pr">▸</span>
            <span class="tx">{{ text(l) }}</span><span v-if="typing(l)" class="type-caret">▍</span>
          </div>
        </template>
        <div class="ln cursor"><span class="ts">&gt;</span><span class="blink fx-loop">▍</span></div>
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.cnt { font-size: 11px; color: var(--text-1); }
.cnt em { font-style: normal; color: var(--text-2); }
.term { position: absolute; inset: 0; padding: 6px 4px 6px 10px; background: linear-gradient(180deg, rgba(0, 3, 9, 0.88), rgba(1, 5, 14, 0.94)); font-family: var(--font-num); font-size: 12px; }
.term::before { content: ''; position: absolute; inset: 0; pointer-events: none; background: repeating-linear-gradient(0deg, rgba(34, 228, 255, 0.025) 0 1px, transparent 1px 3px); }
.scroll { position: relative; height: 100%; overflow-y: auto; overflow-x: hidden; padding-right: 6px; }
.ln { display: flex; gap: 6px; line-height: 19px; white-space: nowrap; color: #9fe9ff; min-width: 0; }
.ln.warn { color: var(--amber); }
.ln.error { color: var(--red); }
.ln.debug { color: var(--text-2); }
.ln.dim { color: var(--text-2); }
.ts { flex: none; color: #3f6b86; }
.ag { flex: none; width: 76px; color: var(--violet); letter-spacing: 0.5px; font-weight: 600; overflow: hidden; }
.warn .ag, .error .ag { color: inherit; }
.pr { flex: none; color: #2f5a74; }
.tx { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.type-caret { color: var(--cyan); }
.sep { display: flex; align-items: center; gap: 8px; margin: 4px 0; color: var(--text-2); font-size: 11px; line-height: 17px; }
.sep::before, .sep::after { content: ''; flex: 1; height: 1px; background: linear-gradient(90deg, transparent, rgba(80, 200, 255, 0.25), transparent); }
.sep span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 88%; }
.cursor .blink { color: var(--cyan); animation: kf-blink 1s steps(1) infinite; }
</style>
