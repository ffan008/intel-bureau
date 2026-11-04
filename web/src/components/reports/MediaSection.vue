<script setup lang="ts">
/** 图片与文档：图片网格（缩略图 + 用途 + 出处，点开看大图和 OCR 要点）；文档卡片（文件名、类型、提炼要点、出处） */
import { computed, ref } from 'vue'
import type { ArticleDTO, MediaDTO, ReportDTO } from '@/api/types'
import { resolveAssetUrl } from '@/api/endpoints'
import { renderMarkdown } from '@/utils/markdown'
import MediaLightbox from './MediaLightbox.vue'
import { fmtAt, pad2 } from './sections'

const props = defineProps<{ rep: ReportDTO; articles: ArticleDTO[] }>()
const emit = defineEmits<{ openArticle: [seq: number] }>()
const images = computed(() => (props.rep.media ?? []).filter((m) => m.kind === 'image'))
const files = computed(() => (props.rep.media ?? []).filter((m) => m.kind === 'file'))
const thumb = (m: MediaDTO) => resolveAssetUrl(props.rep.id, m.url, m.name)
const lightbox = ref<number | null>(null)
const ext = (name: string) => (/\.([a-z0-9]{1,5})$/i.exec(name)?.[1] ?? 'file').toUpperCase()
const EXT_COLOR: Record<string, string> = { PDF: '#ff6b78', DOCX: '#4f9dff', DOC: '#4f9dff', XLSX: '#2bd96b', XLS: '#2bd96b', CSV: '#2bd96b', PPTX: '#ff8a4c', MD: '#a98bff', TXT: '#a9c4dd', HTML: '#22e4ff' }
const artTitle = (seq?: number) => props.articles.find((a) => a.seq === seq)?.title
/** 文档要点可能是 Markdown 列表，按 Markdown 安全渲染 */
const sum = (m: MediaDTO) => renderMarkdown(m.summary || m.ocr_text || '')
/** 文档原件：只有后端给了同源地址（assets 接口）时才提供下载链接 */
const fileHref = (m: MediaDTO) => (m.url?.startsWith('/api/') ? resolveAssetUrl(props.rep.id, m.url) : null)
</script>

<template>
  <div class="ms">
    <section v-if="images.length">
      <h4>图片<span class="num">{{ images.length }}</span></h4>
      <div class="ig">
        <button v-for="(m, i) in images" :key="m.name" class="it" @click="lightbox = i">
          <span class="th">
            <img v-if="thumb(m)" :src="thumb(m)!" :alt="m.why ?? m.name" loading="lazy" />
            <span v-else class="none">{{ m.name }}</span>
          </span>
          <span class="why">{{ m.why || m.summary || m.name }}</span>
          <span class="src">{{ m.group_name }}<template v-if="m.sender"> · {{ m.sender }}</template><template v-if="m.sent_at"> · {{ fmtAt(m.sent_at) }}</template></span>
          <span v-if="m.article_seq" class="art">专题 {{ pad2(m.article_seq) }}</span>
        </button>
      </div>
    </section>

    <section v-if="files.length">
      <h4>文档<span class="num">{{ files.length }}</span></h4>
      <div class="fg">
        <article v-for="m in files" :key="m.name" class="fc">
          <div class="fh">
            <span class="ext num" :style="{ '--ec': EXT_COLOR[ext(m.name)] ?? '#a9c4dd' }">{{ ext(m.name) }}</span>
            <div class="fn">
              <a v-if="fileHref(m)" :href="fileHref(m)!" target="_blank" rel="noopener noreferrer" class="nm">{{ m.name }}</a>
              <b v-else class="nm">{{ m.name }}</b>
              <span class="src">{{ m.group_name }}<template v-if="m.sender"> · {{ m.sender }}</template><template v-if="m.sent_at"> · {{ fmtAt(m.sent_at) }}</template></span>
            </div>
          </div>
          <p v-if="m.why" class="why">{{ m.why }}</p>
          <div v-if="m.summary || m.ocr_text" class="md sum" v-html="sum(m)" />
          <button v-if="m.article_seq" class="btn sm ghost art" @click="emit('openArticle', m.article_seq)">专题 {{ pad2(m.article_seq) }}：{{ artTitle(m.article_seq) }}</button>
        </article>
      </div>
    </section>

    <MediaLightbox :items="images" :index="lightbox" :report-id="rep.id" :articles="articles"
      @close="lightbox = null" @index="lightbox = $event" @open-article="(s) => { lightbox = null; emit('openArticle', s) }" />
  </div>
</template>

<style scoped>
.ms { display: flex; flex-direction: column; gap: 28px; max-width: 1180px; }
h4 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 10px; font-size: 16px; color: var(--text-0); }
h4 .num { font-size: 13px; color: var(--text-2); font-weight: 400; }
.ig { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 14px; }
.it { display: flex; flex-direction: column; gap: 6px; padding: 8px; text-align: left; border: 1px solid var(--line); background: rgba(10, 22, 46, 0.5); min-width: 0; }
.it:hover { border-color: var(--line-strong); }
.it:hover img { transform: scale(1.03); }
.th { display: block; aspect-ratio: 16 / 10; overflow: hidden; background: #02050c; border: 1px solid rgba(80, 200, 255, 0.08); }
.th img { width: 100%; height: 100%; object-fit: cover; display: block; transition: transform var(--t-mid) var(--ease-out); }
.th .none { display: flex; align-items: center; justify-content: center; height: 100%; font-size: 12px; color: var(--text-2); }
.it .why { font-size: 13.5px; line-height: 1.55; color: var(--text-0); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.it .src, .fc .src { font-size: 12px; color: var(--text-2); }
.it .art { align-self: flex-start; font-size: 11.5px; color: var(--cyan); border: 1px solid rgba(34, 228, 255, 0.3); padding: 0 6px; border-radius: 2px; }
.fg { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; }
.fc { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line); background: rgba(10, 22, 46, 0.5); min-width: 0; }
.fh { display: flex; gap: 12px; align-items: flex-start; }
.ext { flex: none; width: 46px; height: 54px; display: flex; align-items: flex-end; justify-content: center; padding-bottom: 8px; font-size: 11px; font-weight: 600; color: var(--ec); border: 1px solid color-mix(in srgb, var(--ec) 55%, transparent); background: color-mix(in srgb, var(--ec) 8%, transparent); clip-path: polygon(0 0, 72% 0, 100% 22%, 100% 100%, 0 100%); }
.fn { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
.fn .nm { font-size: 14.5px; color: var(--text-0); font-weight: 600; word-break: break-all; }
.fn a.nm:hover { color: var(--cyan); }
.fc .why { margin: 0; font-size: 13px; color: var(--text-2); }
.sum { font-size: 14px; line-height: 1.75; }
.sum :deep(ul), .sum :deep(ol) { margin: 0; padding-left: 20px; }
.sum :deep(p) { margin: 0 0 6px; }
.art { align-self: flex-start; height: auto; min-height: 26px; padding: 3px 8px; white-space: normal; text-align: left; line-height: 1.5; color: var(--cyan); }
</style>
