<script setup lang="ts">
/** 知识库阅读视图：正文（body_md）+ 本篇目录、历史版本时间线、来源列表、相关条目 */
import { computed, nextTick, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import type { KbArticleDTO } from '@/api/types'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import { enhanceMarkdown } from '@/utils/mdEnhance'
import { RISK_DISCLAIMER, hasDisclaimer } from '@/utils/risk'
import { categoryColor, categoryName } from '@/utils/meta'
import { fmtAgo, fmtDate, fmtDateTime } from '@/utils/format'
import { useTocSpy } from '@/composables/useTocSpy'
import MdView from '../ui/MdView.vue'
import RiskBadge from '../ui/RiskBadge.vue'
import { fmtAt } from '../reports/sections'

const props = defineProps<{ id: string | null }>()
const emit = defineEmits<{ select: [id: string]; tag: [t: string] }>()
const art = ref<KbArticleDTO | null>(null)
const loading = ref(false)
const error = ref('')
const view = ref<InstanceType<typeof MdView> | null>(null)
const root = ref<HTMLElement | null>(null)
const showAllSrc = ref(false)
const { active, start } = useTocSpy(() => view.value?.el)

watch(() => props.id, async (id) => {
  art.value = null
  error.value = ''
  showAllSrc.value = false
  if (!id) return
  loading.value = true
  try {
    const a = await api.kbArticle(id, { silent: true })
    if (props.id === id) art.value = a
  } catch (e) {
    if (props.id === id) error.value = e instanceof ApiError && e.status === 404 ? '条目不存在或已被删除' : `读取失败：${(e as Error).message}`
  } finally { loading.value = false }
  await nextTick()
  root.value?.scrollTo({ top: 0 })
  start()
}, { immediate: true })

const content = computed(() => (art.value ? enhanceMarkdown(art.value.body_md, {
  dropTitle: true, dropMeta: true, fold: true,
  appendDisclaimer: art.value.risk_flags.length && !hasDisclaimer(art.value.body_md) ? RISK_DISCLAIMER : undefined,
}) : { html: '', toc: [] }))
/** 正文里已经有「**一句话**」段落时，头部不再重复显示 hook */
const bodyHasHook = computed(() => /\*\*一句话\*\*/.test(art.value?.body_md ?? ''))
const versions = computed(() => [...(art.value?.versions ?? [])].sort((a, b) => b.at.localeCompare(a.at)))
const srcGroups = computed(() => {
  const m = new Map<string, { sender: string; at: string }[]>()
  for (const s of art.value?.sources ?? []) m.set(s.group_name, [...(m.get(s.group_name) ?? []), { sender: s.sender, at: s.sent_at }])
  return [...m.entries()].map(([g, xs]) => ({ g, xs: xs.sort((a, b) => b.at.localeCompare(a.at)) }))
})
const srcShown = computed(() => (showAllSrc.value ? srcGroups.value : srcGroups.value.slice(0, 4)))
</script>

<template>
  <div ref="root" class="kr scroller">
    <div v-if="!id" class="empty big"><span class="code">NO ENTRY</span>在左侧选择一个条目</div>
    <div v-else-if="loading && !art" class="empty big"><span class="code">LOADING</span>正在读取条目…</div>
    <div v-else-if="error" class="empty big"><span class="code">ERROR</span>{{ error }}</div>
    <template v-else-if="art">
      <header class="hd" :style="{ '--cc': categoryColor(art.category) }">
        <div class="r1">
          <span class="cat">{{ categoryName(art.category) }}</span>
          <RiskBadge :flags="art.risk_flags" />
          <span class="spacer" />
          <span class="upd">{{ fmtAgo(art.updated_at) }}更新</span>
        </div>
        <h1>{{ art.title }}</h1>
        <p v-if="art.hook && !bodyHasHook" class="hook">{{ art.hook }}</p>
        <div class="meta">
          <span>创建 <b class="num">{{ fmtDate(art.created_at) }}</b></span>
          <span>版本 <b class="num">{{ art.versions.length }}</b></span>
          <span>来源 <b class="num">{{ art.sources.length }}</b></span>
          <span v-if="art.tags.length" class="tags">
            <button v-for="t in art.tags" :key="t" class="chip" @click="emit('tag', t)">#{{ t }}</button>
          </span>
        </div>
      </header>

      <div class="layout">
        <MdView ref="view" :html="content.html" class="body" />
        <aside class="side">
          <section v-if="content.toc.length" class="blk">
            <div class="sec-title">目录<span class="en">CONTENTS</span></div>
            <button v-for="t in content.toc" :key="t.i" class="ti" :class="{ on: active === t.i, sub: t.level === 3 }" @click="view?.scrollToHeading(t.i)">{{ t.text }}</button>
          </section>
          <section class="blk">
            <div class="sec-title">历史版本<span class="en">{{ versions.length }}</span></div>
            <ol class="list-reset tl">
              <li v-for="(v, i) in versions" :key="v.at + i" :class="{ cur: i === 0 }">
                <span class="dot" />
                <div class="vt num">{{ fmtDateTime(v.at) }}<em v-if="i === 0">当前</em></div>
                <div class="vn">{{ v.note || '更新' }}</div>
                <RouterLink v-if="v.report_id" class="vr" :to="{ path: '/reports', query: { id: v.report_id } }">来自报告 {{ v.report_id.replace(/^rpt-/, '') }}</RouterLink>
              </li>
            </ol>
          </section>
          <section class="blk">
            <div class="sec-title">来源<span class="en">{{ art.sources.length }}</span></div>
            <div v-for="s in srcShown" :key="s.g" class="sg">
              <b>{{ s.g }}</b>
              <span v-for="(x, j) in s.xs.slice(0, 6)" :key="j" class="sx">{{ x.sender }} · <span class="num">{{ fmtAt(x.at) }}</span></span>
              <span v-if="s.xs.length > 6" class="sx dim">另有 {{ s.xs.length - 6 }} 条</span>
            </div>
            <button v-if="srcGroups.length > 4" class="btn sm ghost" @click="showAllSrc = !showAllSrc">{{ showAllSrc ? '收起' : `展开全部 ${srcGroups.length} 个群` }}</button>
          </section>
          <section v-if="art.related.length" class="blk">
            <div class="sec-title">相关条目<span class="en">RELATED</span></div>
            <button v-for="r in art.related" :key="r.id" class="rel" @click="emit('select', r.id)">{{ r.title }}</button>
          </section>
        </aside>
      </div>
    </template>
  </div>
</template>

<style scoped>
.kr { container-type: inline-size; height: 100%; overflow-y: auto; padding: 20px 28px 40px; background: rgba(6, 14, 32, 0.6); border: 1px solid var(--line); }
.big { min-height: 50vh; }
.hd { margin-bottom: 20px; padding-bottom: 16px; border-bottom: 1px solid var(--line); max-width: 1100px; }
.r1 { display: flex; align-items: center; gap: 10px; }
.cat { font-size: 13px; color: var(--cc); }
.upd { font-size: 12px; color: var(--text-2); }
.hd h1 { margin: 10px 0 8px; font-size: 26px; line-height: 1.45; color: var(--text-0); }
.hook { margin: 0 0 12px; font-size: 16px; line-height: 1.7; color: var(--text-1); }
.meta { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; font-size: 12.5px; color: var(--text-2); }
.meta b { color: var(--text-0); margin-left: 3px; }
.tags { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.tags .chip:hover { color: var(--cyan); border-color: var(--line-strong); }
.layout { display: grid; grid-template-columns: minmax(0, 760px) minmax(240px, 300px); gap: 36px; justify-content: space-between; max-width: 1100px; }
.side { position: sticky; top: 0; align-self: start; display: flex; flex-direction: column; gap: 22px; max-height: calc(100vh - 150px); overflow-y: auto; padding-right: 4px; }
.blk .sec-title { margin-bottom: 8px; }
.ti { display: block; width: 100%; text-align: left; padding: 5px 10px; font-size: 13px; line-height: 1.5; color: var(--text-2); border-left: 2px solid var(--line); }
.ti.sub { padding-left: 22px; font-size: 12.5px; }
.ti:hover { color: var(--text-0); }
.ti.on { color: var(--cyan); border-left-color: var(--cyan); background: rgba(34, 228, 255, 0.05); }
.tl { position: relative; padding-left: 16px; }
.tl::before { content: ''; position: absolute; left: 4px; top: 6px; bottom: 6px; width: 1px; background: var(--line-strong); }
.tl li { position: relative; padding: 0 0 12px; }
.tl .dot { position: absolute; left: -16px; top: 6px; width: 9px; height: 9px; border-radius: 50%; border: 1px solid var(--cyan-dim); background: var(--bg-0); }
.tl li.cur .dot { background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 8px var(--cyan); }
.vt { font-size: 12px; color: var(--text-1); }
.vt em { font-style: normal; margin-left: 6px; font-size: 11px; color: var(--cyan); font-family: var(--font-cn); }
.vn { font-size: 13px; line-height: 1.55; color: var(--text-0); }
.vr { font-size: 12px; }
.sg { display: flex; flex-direction: column; gap: 2px; padding: 6px 0; border-bottom: 1px solid rgba(80, 200, 255, 0.07); font-size: 12.5px; }
.sg b { font-size: 13px; color: var(--text-0); font-weight: 600; }
.sx { color: var(--text-1); }
.rel { display: block; width: 100%; text-align: left; padding: 6px 10px; font-size: 13px; line-height: 1.5; color: var(--text-1); border-left: 2px solid var(--line); }
.rel:hover { color: var(--cyan); border-left-color: var(--cyan); }
@container (max-width: 1040px) {
  .layout { grid-template-columns: minmax(0, 1fr); }
  .side { position: static; }
}
</style>
