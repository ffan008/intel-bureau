<script setup lang="ts">
/**
 * 专题阅读视图：结构化头部（序号、分类、风险、来源）+ body_md 正文 + 右侧本篇目录；
 * 扩展研究的 [n] 可点，跳到参考链接；有风险标签但正文没写免责声明时补上；上一篇 / 下一篇（也可用 ← →）。
 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { ArticleDTO, MediaDTO, ReportDTO } from '@/api/types'
import { resolveAssetUrl } from '@/api/endpoints'
import { enhanceMarkdown } from '@/utils/mdEnhance'
import { RISK_DISCLAIMER, hasDisclaimer } from '@/utils/risk'
import { categoryColor, categoryName, platformColor } from '@/utils/meta'
import { useTocSpy } from '@/composables/useTocSpy'
import Icon from '../Icon.vue'
import MdView from '../ui/MdView.vue'
import RiskBadge from '../ui/RiskBadge.vue'
import MediaLightbox from './MediaLightbox.vue'
import { fmtAt, normSources, pad2 } from './sections'

const props = defineProps<{ rep: ReportDTO; article: ArticleDTO; articles: ArticleDTO[] }>()
const emit = defineEmits<{ nav: [seq: number]; back: [] }>()
const view = ref<InstanceType<typeof MdView> | null>(null)

const idx = computed(() => props.articles.findIndex((a) => a.id === props.article.id))
const prev = computed(() => (idx.value > 0 ? props.articles[idx.value - 1] : undefined))
const next = computed(() => (idx.value >= 0 && idx.value < props.articles.length - 1 ? props.articles[idx.value + 1] : undefined))
const sources = computed(() => normSources(props.article.sources))
const content = computed(() => enhanceMarkdown(props.article.body_md, {
  dropTitle: true, dropMeta: true, fold: true, refs: props.article.research_refs,
  appendDisclaimer: props.article.risk_flags.length && !hasDisclaimer(props.article.body_md) ? RISK_DISCLAIMER : undefined,
}))

/** 本篇配图：ArticleDTO.images 与 MediaDTO 按名字对上，取 OCR 要点与出处；对不上的直接按资源名取图 */
/** images[] 是 assets 里的文件名；MediaDTO.name 可能是原始文件名，所以同时按 url 末段匹配 */
const sameAsset = (m: MediaDTO, name: string) => m.name === name || m.url === name || (!!m.url && decodeURIComponent(m.url.split('?')[0]!.split('/').pop() ?? '') === name)
const images = computed<MediaDTO[]>(() => props.article.images.map((name) => {
  const m = props.rep.media?.find((x) => x.kind === 'image' && sameAsset(x, name))
  return m ?? { kind: 'image', name, article_seq: props.article.seq }
}))
const thumbs = computed(() => images.value.map((m) => resolveAssetUrl(props.rep.id, m.url, m.name)))
const lightbox = ref<number | null>(null)

const { active, start } = useTocSpy(() => view.value?.el)
onMounted(() => void nextTick(start))
watch(content, () => void nextTick(start))

function onKey(e: KeyboardEvent): void {
  if (lightbox.value !== null || e.altKey || e.ctrlKey || e.metaKey) return
  const t = e.target
  if (t instanceof Element && t.closest('input,textarea,select,[contenteditable="true"],[role="tablist"],[role="dialog"]')) return
  if (e.key === 'ArrowLeft' && prev.value) emit('nav', prev.value.seq)
  else if (e.key === 'ArrowRight' && next.value) emit('nav', next.value.seq)
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <div class="ar" :style="{ '--cc': categoryColor(article.category) }">
    <div class="bar">
      <button class="btn sm ghost" @click="emit('back')"><Icon name="chevronLeft" />全部专题</button>
      <span class="pos num">{{ pad2(article.seq) }} / {{ pad2(articles.length) }}</span>
      <span class="spacer" />
      <button class="btn sm" :disabled="!prev" title="上一篇（←）" @click="prev && emit('nav', prev.seq)"><Icon name="chevronLeft" />上一篇</button>
      <button class="btn sm" :disabled="!next" title="下一篇（→）" @click="next && emit('nav', next.seq)">下一篇<Icon name="chevronRight" /></button>
    </div>

    <div class="layout">
      <article class="main">
        <header class="hd">
          <div class="r1">
            <span class="sq num">{{ pad2(article.seq) }}</span>
            <span class="cat">{{ categoryName(article.category) }}</span>
            <RiskBadge :flags="article.risk_flags" />
            <span class="spacer" />
            <RouterLink v-if="article.kb_id" class="kb" :to="{ path: '/kb', query: { id: article.kb_id } }"><Icon name="database" :size="13" />知识库条目</RouterLink>
          </div>
          <h1>{{ article.title }}</h1>
          <div v-if="sources.length" class="srcs">
            <span class="lbl">来源</span>
            <span v-for="(s, i) in sources" :key="i" class="chip"><i class="pdot" :style="{ background: platformColor(s.platform) }" />{{ s.group }}<template v-if="s.sender"> · {{ s.sender }}</template><template v-if="s.at"> · <span class="num">{{ fmtAt(s.at) }}</span></template></span>
          </div>
          <p v-if="article.risk_note" class="rn">{{ article.risk_note }}</p>
        </header>

        <div v-if="images.length" class="pics">
          <button v-for="(m, i) in images" :key="m.name" class="pic" :title="m.why ?? m.name" @click="lightbox = i">
            <img v-if="thumbs[i]" :src="thumbs[i]!" :alt="m.why ?? m.name" loading="lazy" />
            <span v-else class="noimg">{{ m.name }}</span>
          </button>
          <span class="pics-hint">本篇配图 {{ images.length }} 张，点开看大图和 OCR 要点</span>
        </div>

        <MdView ref="view" :html="content.html" />

        <nav class="pn" aria-label="翻篇">
          <button v-if="prev" class="pcard" @click="emit('nav', prev.seq)"><span class="d"><Icon name="chevronLeft" :size="13" />上一篇 · {{ pad2(prev.seq) }}</span><b>{{ prev.title }}</b></button>
          <span v-else />
          <button v-if="next" class="pcard r" @click="emit('nav', next.seq)"><span class="d">下一篇 · {{ pad2(next.seq) }}<Icon name="chevronRight" :size="13" /></span><b>{{ next.title }}</b></button>
        </nav>
      </article>

      <aside v-if="content.toc.length" class="toc">
        <div class="sec-title">本篇目录<span class="en">CONTENTS</span></div>
        <button v-for="t in content.toc" :key="t.i" class="ti" :class="{ on: active === t.i, sub: t.level === 3 }" @click="view?.scrollToHeading(t.i)">{{ t.text }}</button>
      </aside>
    </div>

    <MediaLightbox :items="images" :index="lightbox" :report-id="rep.id" :articles="articles" :current-seq="article.seq"
      @close="lightbox = null" @index="lightbox = $event" @open-article="(s) => { lightbox = null; if (s !== article.seq) emit('nav', s) }" />
  </div>
</template>

<style scoped>
.ar { display: flex; flex-direction: column; gap: 16px; }
.bar { position: sticky; top: 0; z-index: 4; display: flex; align-items: center; gap: 8px; margin: -20px -28px 0; padding: 10px 20px; background: rgba(6, 14, 32, 0.94); border-bottom: 1px solid var(--line); backdrop-filter: blur(6px); }
.pos { font-size: 12.5px; color: var(--text-2); }
.layout { display: grid; grid-template-columns: minmax(0, 760px) minmax(180px, 240px); gap: 36px; justify-content: space-between; }
.main { min-width: 0; }
.hd { margin-bottom: 18px; padding-bottom: 16px; border-bottom: 1px solid var(--line); }
.r1 { display: flex; align-items: center; gap: 10px; }
.sq { font-size: 26px; font-weight: 600; line-height: 1; color: var(--cc); }
.cat { font-size: 13px; color: var(--cc); }
.kb { display: inline-flex; align-items: center; gap: 5px; font-size: 12.5px; color: var(--text-1); border: 1px solid var(--line); padding: 2px 8px; border-radius: 3px; }
.kb:hover { color: var(--cyan); border-color: var(--line-strong); text-decoration: none; }
.hd h1 { margin: 10px 0 12px; font-size: 26px; line-height: 1.45; color: var(--text-0); font-weight: 700; }
.srcs { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.srcs .lbl { font-size: 12px; color: var(--text-2); margin-right: 2px; }
.srcs .chip { height: 22px; font-size: 12px; }
.rn { margin: 10px 0 0; font-size: 13.5px; line-height: 1.7; color: #d9c49a; }
.pics { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 18px; }
.pic { width: 112px; height: 76px; border: 1px solid var(--line); background: rgba(0, 3, 9, 0.7); overflow: hidden; }
.pic:hover { border-color: var(--cyan); }
.pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
.noimg { display: flex; align-items: center; justify-content: center; height: 100%; padding: 4px; font-size: 11px; color: var(--text-2); word-break: break-all; }
.pics-hint { font-size: 12.5px; color: var(--text-2); }
.pn { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 36px; padding-top: 18px; border-top: 1px solid var(--line); }
.pcard { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px; text-align: left; border: 1px solid var(--line); background: rgba(10, 22, 46, 0.5); min-width: 0; }
.pcard.r { text-align: right; align-items: flex-end; }
.pcard:hover { border-color: var(--line-strong); }
.pcard .d { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--text-2); }
.pcard b { font-size: 14.5px; color: var(--text-0); font-weight: 600; line-height: 1.5; }
.toc { position: sticky; top: 64px; align-self: start; display: flex; flex-direction: column; gap: 1px; max-height: calc(100vh - 220px); overflow-y: auto; }
.ti { display: block; text-align: left; padding: 6px 10px; font-size: 13px; line-height: 1.5; color: var(--text-2); border-left: 2px solid var(--line); }
.ti.sub { padding-left: 22px; font-size: 12.5px; }
.ti:hover { color: var(--text-0); }
.ti.on { color: var(--cyan); border-left-color: var(--cyan); background: rgba(34, 228, 255, 0.05); }
@container (max-width: 980px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .toc { display: none; }
}
</style>
