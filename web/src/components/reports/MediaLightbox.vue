<script setup lang="ts">
/** 看大图：左侧原图，右侧用途、OCR 要点、出处、所属专题；← → 切换，Esc 关闭 */
import { computed, onBeforeUnmount, watch } from 'vue'
import type { ArticleDTO, MediaDTO } from '@/api/types'
import { resolveAssetUrl } from '@/api/endpoints'
import Icon from '../Icon.vue'
import { fmtAt, pad2 } from './sections'

const props = defineProps<{ items: MediaDTO[]; index: number | null; reportId: string; articles: ArticleDTO[]; currentSeq?: number }>()
const emit = defineEmits<{ close: []; index: [i: number]; openArticle: [seq: number] }>()
const cur = computed(() => (props.index === null ? null : props.items[props.index] ?? null))
const src = computed(() => (cur.value ? resolveAssetUrl(props.reportId, cur.value.url, cur.value.name) : null))
const art = computed(() => (cur.value?.article_seq ? props.articles.find((a) => a.seq === cur.value!.article_seq) : undefined))
const ocrLines = computed(() => (cur.value?.ocr_text ?? '').split(/\n+/).map((s) => s.replace(/^\s*[-*•·]\s*/, '').trim()).filter(Boolean))

function step(d: number): void {
  if (props.index === null || !props.items.length) return
  emit('index', (props.index + d + props.items.length) % props.items.length)
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1) }
}
watch(() => props.index !== null, (open) => {
  if (open) document.addEventListener('keydown', onKey)
  else document.removeEventListener('keydown', onKey)
}, { immediate: true })
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <div v-if="cur" class="lb" role="dialog" aria-modal="true" :aria-label="`图片：${cur.name}`" @mousedown.self="emit('close')">
      <div class="box">
        <div class="view">
          <img v-if="src" :src="src" :alt="cur.why ?? cur.name" />
          <div v-else class="none">图片暂时取不到（{{ cur.name }}）</div>
          <template v-if="items.length > 1">
            <button class="nv l" aria-label="上一张" @click="step(-1)"><Icon name="chevronLeft" :size="22" /></button>
            <button class="nv r" aria-label="下一张" @click="step(1)"><Icon name="chevronRight" :size="22" /></button>
          </template>
        </div>
        <aside class="side">
          <div class="top">
            <span class="cnt num">{{ (index ?? 0) + 1 }} / {{ items.length }}</span>
            <span class="spacer" />
            <button class="btn ghost sm icon" aria-label="关闭" @click="emit('close')"><Icon name="close" /></button>
          </div>
          <h4 class="nm">{{ cur.name }}</h4>
          <p v-if="cur.why" class="why">{{ cur.why }}</p>
          <div v-if="ocrLines.length" class="blk">
            <div class="lbl">OCR 要点</div>
            <ul class="list-reset ocr"><li v-for="(l, i) in ocrLines" :key="i">{{ l }}</li></ul>
          </div>
          <div v-if="cur.summary" class="blk"><div class="lbl">说明</div><p class="sum">{{ cur.summary }}</p></div>
          <div class="blk">
            <div class="lbl">出处</div>
            <p class="src">{{ cur.group_name || '未知群' }}<template v-if="cur.sender"> · {{ cur.sender }}</template><template v-if="cur.sent_at"> · <span class="num">{{ fmtAt(cur.sent_at) }}</span></template></p>
          </div>
          <button v-if="art && art.seq !== currentSeq" class="btn sm art" @click="emit('openArticle', art.seq)">
            所属专题 {{ pad2(art.seq) }}：{{ art.title }}
          </button>
        </aside>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.lb { position: fixed; inset: 0; z-index: 950; display: flex; align-items: center; justify-content: center; background: rgba(2, 5, 12, 0.82); backdrop-filter: blur(4px); }
.box { display: grid; grid-template-columns: minmax(0, 1fr) 340px; width: min(1400px, calc(100vw - 64px)); height: min(860px, calc(100vh - 64px)); border: 1px solid var(--line-strong); background: rgba(6, 14, 32, 0.97); box-shadow: var(--shadow-pop); }
.view { position: relative; display: flex; align-items: center; justify-content: center; min-width: 0; min-height: 0; padding: 16px; background: #02050c; }
.view img { max-width: 100%; max-height: 100%; object-fit: contain; display: block; }
.none { color: var(--text-2); font-size: 13px; }
.nv { position: absolute; top: 50%; width: 40px; height: 64px; margin-top: -32px; display: flex; align-items: center; justify-content: center; color: var(--text-0); background: rgba(6, 14, 32, 0.7); border: 1px solid var(--line); }
.nv:hover { color: var(--cyan); border-color: var(--line-strong); }
.nv.l { left: 12px; }
.nv.r { right: 12px; }
.side { display: flex; flex-direction: column; gap: 14px; min-height: 0; overflow-y: auto; padding: 12px 18px 18px; border-left: 1px solid var(--line); }
.top { display: flex; align-items: center; }
.cnt { font-size: 12px; color: var(--text-2); }
.nm { margin: 0; font-size: 15px; color: var(--text-0); word-break: break-all; }
.why { margin: 0; font-size: 14px; line-height: 1.7; color: var(--text-1); }
.lbl { font-size: 12px; color: var(--text-2); margin-bottom: 6px; }
.ocr { display: flex; flex-direction: column; gap: 6px; font-size: 13.5px; line-height: 1.65; color: var(--text-0); }
.ocr li { padding-left: 12px; position: relative; }
.ocr li::before { content: ''; position: absolute; left: 0; top: 10px; width: 4px; height: 4px; background: var(--cyan); }
.sum, .src { margin: 0; font-size: 13.5px; line-height: 1.7; color: var(--text-1); }
.art { height: auto; min-height: 30px; padding: 6px 10px; white-space: normal; text-align: left; justify-content: flex-start; line-height: 1.5; }
</style>
