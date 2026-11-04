<script setup lang="ts">
/** 今日总览（§3.1）：数据卡 → 一句话总结与今日风向 → 今日 N 篇专题（点击直达）→ 资源计数 */
import { computed } from 'vue'
import type { ArticleDTO, ReportDTO, SectionKey } from '@/api/types'
import { enhanceMarkdown } from '@/utils/mdEnhance'
import { categoryColor, categoryName } from '@/utils/meta'
import { fmtInt } from '@/utils/format'
import MdView from '../ui/MdView.vue'
import RiskBadge from '../ui/RiskBadge.vue'
import { RESOURCE_GROUPS, pad2, stripLeadHeading } from './sections'

const props = defineProps<{ rep: ReportDTO; articles: ArticleDTO[] }>()
const emit = defineEmits<{ open: [seq: number]; go: [tab: SectionKey]; anchor: [hash: string] }>()

const risky = computed(() => {
  const n = props.rep.section_counts?.risks
  return typeof n === 'number' ? n : props.articles.filter((a) => a.risk_flags.length).length
})
const cards = computed(() => {
  const s = props.rep.stats
  const groups = s.by_platform.reduce((a, p) => a + p.groups, 0)
  return [
    { k: '消息', v: fmtInt(s.messages_raw), sub: `有效 ${fmtInt(s.messages_clean)}` },
    { k: '群', v: fmtInt(groups), sub: `发言 ${fmtInt(s.speakers)} 人` },
    { k: '情报', v: fmtInt(props.rep.items_total), sub: `头条 ${props.rep.headlines.length}` },
    { k: '专题文章', v: fmtInt(props.articles.length), sub: '点下方标题直达', tab: 'articles' as SectionKey },
    { k: '资源', v: fmtInt(props.rep.resources?.length ?? 0), sub: `风险标注 ${risky.value} 条`, tab: 'resources' as SectionKey },
  ]
})
const md = computed(() => {
  const raw = props.rep.sections?.overview ?? ''
  return raw.trim() ? enhanceMarkdown(stripLeadHeading(raw, '今日总览'), { fold: false, overview: props.articles.length > 0 }).html : ''
})
const resCounts = computed(() => RESOURCE_GROUPS.map((g) => ({ ...g, n: (props.rep.resources ?? []).filter((r) => g.kinds.includes(r.kind)).length }))
  .filter((g) => g.n > 0))
</script>

<template>
  <div class="ov">
    <div class="cards">
      <component :is="c.tab ? 'button' : 'div'" v-for="c in cards" :key="c.k" class="card" :class="{ link: !!c.tab }" @click="c.tab && emit('go', c.tab)">
        <span class="k">{{ c.k }}</span>
        <b class="v num">{{ c.v }}</b>
        <span class="sub">{{ c.sub }}</span>
      </component>
    </div>

    <MdView v-if="md" :html="md" @anchor="emit('anchor', $event)" />
    <div v-else-if="rep.judgments.length" class="md read">
      <h2>今日风向</h2>
      <ol><li v-for="(j, i) in rep.judgments" :key="i"><strong>{{ j.text }}</strong><br /><span class="dim">依据：{{ j.basis }}</span></li></ol>
    </div>

    <section v-if="articles.length" class="feat">
      <div class="fh">
        <h4>今日 {{ articles.length }} 篇专题</h4>
        <button class="btn sm ghost" @click="emit('go', 'articles')">卡片视图</button>
      </div>
      <ol class="list-reset fl">
        <li v-for="a in articles" :key="a.id">
          <button class="fi" :style="{ '--cc': categoryColor(a.category) }" @click="emit('open', a.seq)">
            <span class="sq num">{{ pad2(a.seq) }}</span>
            <span class="ft">{{ a.title }}</span>
            <span class="fc">{{ categoryName(a.category) }}</span>
            <RiskBadge :flags="a.risk_flags" :max="2" sm />
          </button>
        </li>
      </ol>
    </section>

    <section v-if="resCounts.length" class="res">
      <h4>外部精选资源</h4>
      <div class="rc">
        <button v-for="g in resCounts" :key="g.key" class="chip" @click="emit('go', 'resources')">{{ g.title }} <b class="num">{{ g.n }}</b></button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.ov { display: flex; flex-direction: column; gap: 24px; max-width: 920px; }
.cards { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.card { display: flex; flex-direction: column; gap: 2px; padding: 12px 14px; text-align: left; border: 1px solid var(--line); background: rgba(10, 22, 46, 0.5); min-width: 0; }
.card.link:hover { border-color: var(--line-strong); background: rgba(34, 228, 255, 0.05); }
.card .k { font-size: 12.5px; color: var(--text-2); }
.card .v { font-size: 26px; font-weight: 600; color: var(--text-0); line-height: 1.3; }
.card .sub { font-size: 12px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.feat h4, .res h4 { margin: 0; font-size: 17px; color: var(--text-0); }
.fh { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.fl { display: flex; flex-direction: column; border-top: 1px solid var(--line); }
.fi { display: grid; grid-template-columns: 34px minmax(0, 1fr) auto auto; align-items: center; gap: 12px; width: 100%; padding: 10px 8px; text-align: left; border-bottom: 1px solid rgba(80, 200, 255, 0.08); }
.fi:hover { background: rgba(34, 228, 255, 0.04); }
.fi:hover .ft { color: var(--cyan); }
.fi .sq { font-size: 14px; font-weight: 600; color: var(--cc); }
.fi .ft { font-size: 15.5px; color: var(--text-0); line-height: 1.5; }
.fi .fc { font-size: 12px; color: var(--cc); white-space: nowrap; }
.res h4 { margin-bottom: 10px; }
.rc { display: flex; flex-wrap: wrap; gap: 8px; }
.rc .chip { height: 26px; padding: 0 12px; font-size: 13px; border-radius: 13px; }
.rc .chip b { color: var(--cyan); margin-left: 4px; }
.rc .chip:hover { border-color: var(--line-strong); color: var(--text-0); }
</style>
