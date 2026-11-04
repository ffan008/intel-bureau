<script setup lang="ts">
/**
 * v2 板块阅读器（V2_KNOWLEDGE §3.1）：左侧竖向 12 个板块标签（名称 + 条目数，空板块灰显），右侧内容区。
 * 当前板块和专题写进地址栏（?tab=articles&a=3），可以分享、刷新后保持。
 */
import { computed, nextTick, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { SECTION_KEYS, type ReportDTO, type SectionKey } from '@/api/types'
import { enhanceMarkdown } from '@/utils/mdEnhance'
import MdView from '../ui/MdView.vue'
import OverviewSection from './OverviewSection.vue'
import ArticleGrid from './ArticleGrid.vue'
import ArticleReader from './ArticleReader.vue'
import ResourceTable from './ResourceTable.vue'
import MediaSection from './MediaSection.vue'
import GroupCards from './GroupCards.vue'
import { SECTION_META, hasContent, sectionCounts, stripLeadHeading } from './sections'

const props = defineProps<{ rep: ReportDTO }>()
const route = useRoute()
const router = useRouter()
const root = ref<HTMLElement | null>(null)
const tabsEl = ref<HTMLElement | null>(null)

const counts = computed(() => sectionCounts(props.rep))
const tab = computed<SectionKey>(() => {
  const t = route.query.tab
  return typeof t === 'string' && (SECTION_KEYS as string[]).includes(t) ? (t as SectionKey) : 'overview'
})
const articles = computed(() => [...(props.rep.articles ?? [])].sort((a, b) => a.seq - b.seq))
const current = computed(() => {
  const a = Number(route.query.a)
  return tab.value === 'articles' && Number.isFinite(a) ? articles.value.find((x) => x.seq === a) ?? null : null
})

function scrollTop(): void {
  const sc = root.value?.closest<HTMLElement>('.scroller')
  const top = root.value ? root.value.getBoundingClientRect().top - (sc?.getBoundingClientRect().top ?? 0) + (sc?.scrollTop ?? 0) - 8 : 0
  if (sc && sc.scrollTop > top) sc.scrollTo({ top })
}
function go(t: SectionKey, a?: number): void {
  void router.replace({ query: { ...route.query, tab: t === 'overview' ? undefined : t, a: a === undefined ? undefined : String(a) } })
  void nextTick(scrollTop)
}
const openArticle = (seq: number) => go('articles', seq)

/** 板块正文里的站内锚点：#article-3、#a-3、#articles、#resources 等 */
function onAnchor(hash: string): void {
  const m = /^(?:article|a)-?(\d+)$/.exec(hash)
  if (m) return openArticle(Number(m[1]))
  if ((SECTION_KEYS as string[]).includes(hash)) go(hash as SectionKey)
}

/** 上下方向键在标签之间移动（role=tablist 的常规键盘操作） */
function onTabKey(e: KeyboardEvent): void {
  if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
  e.preventDefault()
  const i = SECTION_KEYS.indexOf(tab.value)
  const next = SECTION_KEYS[(i + (e.key === 'ArrowDown' ? 1 : SECTION_KEYS.length - 1)) % SECTION_KEYS.length]!
  go(next)
  void nextTick(() => tabsEl.value?.querySelector<HTMLElement>(`[data-k="${next}"]`)?.focus())
}

const md = computed(() => {
  const raw = props.rep.sections?.[tab.value] ?? ''
  return raw.trim() ? enhanceMarkdown(stripLeadHeading(raw, SECTION_META[tab.value].title), { fold: true }).html : ''
})
/** 有结构化数据的板块用专门的组件；数组为空但有 Markdown 时退回 Markdown */
const structured = computed(() => ({
  articles: articles.value.length > 0,
  resources: (props.rep.resources?.length ?? 0) > 0,
  media: (props.rep.media?.length ?? 0) > 0,
  groups: (props.rep.groups?.length ?? 0) > 0,
}))
const showMd = computed(() => {
  const t = tab.value
  if (t === 'overview') return false
  if (t === 'articles' || t === 'resources' || t === 'media' || t === 'groups') return !structured.value[t] && !!md.value
  return !!md.value
})
const isEmpty = computed(() => tab.value !== 'overview' && !showMd.value
  && !(tab.value in structured.value && structured.value[tab.value as keyof typeof structured.value]))
</script>

<template>
  <div ref="root" class="board">
    <nav ref="tabsEl" class="tabs-v" role="tablist" aria-label="报告板块" aria-orientation="vertical" @keydown="onTabKey">
      <button v-for="k in SECTION_KEYS" :key="k" :data-k="k" role="tab" class="tv" :aria-selected="tab === k" :tabindex="tab === k ? 0 : -1"
        :class="{ on: tab === k, none: !hasContent(rep, k, counts[k]) }" @click="go(k)">
        <span class="t">{{ SECTION_META[k].title }}</span>
        <b v-if="k !== 'overview' && counts[k] !== null" class="n num">{{ counts[k] }}</b>
      </button>
    </nav>

    <section class="pane" role="tabpanel" :aria-label="SECTION_META[tab].title">
      <ArticleReader v-if="tab === 'articles' && current" :key="current.id" :rep="rep" :article="current" :articles="articles"
        @nav="openArticle" @back="go('articles')" />
      <template v-else>
        <header class="ph">
          <h3>{{ SECTION_META[tab].title }}</h3>
          <span class="code disp">{{ SECTION_META[tab].code }}</span>
          <span v-if="SECTION_META[tab].note" class="note">{{ SECTION_META[tab].note }}</span>
        </header>
        <div v-if="tab === 'risks' && !isEmpty" class="policy">
          风险内容照常收录、照常扩展，只加标注和免责声明，是否采用由你判断。<span class="risk-chip severe">违法高危</span>只记录群里在讨论什么，不做联网扩展、不写成教程。涉及个人隐私的已剔除或脱敏。
        </div>

        <OverviewSection v-if="tab === 'overview'" :rep="rep" :articles="articles" @open="openArticle" @go="go" @anchor="onAnchor" />
        <ArticleGrid v-else-if="tab === 'articles' && structured.articles" :articles="articles" @open="openArticle" />
        <ResourceTable v-else-if="tab === 'resources' && structured.resources" :resources="rep.resources ?? []" />
        <MediaSection v-else-if="tab === 'media' && structured.media" :rep="rep" :articles="articles" @open-article="openArticle" />
        <GroupCards v-else-if="tab === 'groups' && structured.groups" :groups="rep.groups ?? []" />
        <MdView v-else-if="showMd" :key="tab" :html="md" @anchor="onAnchor" />
        <div v-if="isEmpty" class="empty"><span class="code">EMPTY</span>{{ SECTION_META[tab].empty }}</div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.board { display: grid; grid-template-columns: 176px minmax(0, 1fr); gap: 20px; align-items: start; }
.tabs-v { position: sticky; top: 0; display: flex; flex-direction: column; gap: 2px; padding: 6px; background: rgba(6, 14, 32, 0.6); border: 1px solid var(--line); }
.tv { position: relative; display: flex; align-items: center; gap: 8px; height: 38px; padding: 0 12px; font-size: 14px; color: var(--text-1); text-align: left; border-radius: 2px; }
.tv:hover { color: var(--text-0); background: rgba(34, 228, 255, 0.05); }
.tv .t { flex: 1; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tv .n { font-size: 12px; font-weight: 600; color: var(--text-2); }
.tv.on { color: var(--text-0); background: linear-gradient(90deg, rgba(34, 228, 255, 0.14), rgba(34, 228, 255, 0.03)); }
.tv.on::before { content: ''; position: absolute; left: 0; top: 8px; bottom: 8px; width: 2px; background: var(--cyan); box-shadow: 0 0 8px var(--cyan); }
.tv.on .n { color: var(--cyan); }
.tv.none { color: rgba(108, 134, 163, 0.55); }
.tv.none .n { color: rgba(108, 134, 163, 0.45); font-weight: 400; }
.pane { container-type: inline-size; min-width: 0; min-height: 60vh; padding: 20px 28px 36px; background: rgba(6, 14, 32, 0.6); border: 1px solid var(--line); }
.ph { display: flex; align-items: baseline; gap: 10px; margin-bottom: 18px; padding-bottom: 12px; border-bottom: 1px solid var(--line); }
.ph h3 { margin: 0; font-size: 20px; font-weight: 700; color: var(--text-0); }
.ph .code { font-size: 10px; letter-spacing: 2px; color: var(--text-2); }
.ph .note { margin-left: auto; font-size: 13px; color: var(--text-2); }
.policy { max-width: 760px; margin-bottom: 18px; padding: 10px 14px; font-size: 13.5px; line-height: 1.8; color: #d9c49a; border-left: 2px solid rgba(255, 176, 32, 0.6); background: rgba(255, 176, 32, 0.045); }
.policy .risk-chip { margin: 0 4px; }
.empty { min-height: 260px; font-size: 14px; }
</style>
