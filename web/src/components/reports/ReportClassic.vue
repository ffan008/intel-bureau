<script setup lang="ts">
/** v1 报告阅读器：头条卡片 + full_md 正文 + 目录。v2 字段缺失的旧报告走这里 */
import { computed, nextTick, ref, watch } from 'vue'
import type { IntelItemDTO, ReportDTO } from '@/api/types'
import { renderMarkdown } from '@/utils/markdown'
import { TREND, categoryColor, categoryName, platformColor } from '@/utils/meta'

const props = defineProps<{ rep: ReportDTO }>()
const emit = defineEmits<{ open: [item: IntelItemDTO] }>()
const html = computed(() => renderMarkdown(props.rep.full_md))
const art = ref<HTMLElement | null>(null)
const toc = ref<{ text: string; el: HTMLElement }[]>([])
const heads = computed(() => props.rep.items.filter((i) => i.is_headline).sort((a, b) => a.rank - b.rank))

watch(html, async () => {
  await nextTick()
  toc.value = [...(art.value?.querySelectorAll('h2') ?? [])].map((el) => ({ text: el.textContent ?? '', el: el as HTMLElement }))
}, { immediate: true })
const goto = (el: HTMLElement) => el.scrollIntoView({ behavior: 'smooth', block: 'start' })
</script>

<template>
  <div class="classic">
    <div class="heads">
      <button v-for="h in heads" :key="h.id" class="hcard" :style="{ '--cc': categoryColor(h.category) }" @click="emit('open', h)">
        <div class="r1"><span class="rk num">#{{ h.rank }}</span><span class="cat">{{ categoryName(h.category) }}</span><span class="badge disp" :class="TREND[h.trend].cls">{{ TREND[h.trend].label }}</span><b class="sc num">{{ h.score.toFixed(1) }}</b></div>
        <div class="ttl">{{ h.title }}</div>
        <div class="src"><span v-for="s in h.sources.slice(0, 2)" :key="s.group_key"><i :style="{ background: platformColor(s.platform) }" />{{ s.group_name }}</span></div>
      </button>
    </div>

    <div class="body">
      <article ref="art" class="md" v-html="html" />
      <aside class="toc">
        <div class="sec-title">目录<span class="en">CONTENTS</span></div>
        <button v-for="t in toc" :key="t.text" class="ti ellipsis" @click="goto(t.el)">{{ t.text }}</button>
        <div class="sec-title mt">全部情报<span class="en">{{ rep.items.length }}</span></div>
        <button v-for="it in rep.items" :key="it.id" class="ii" :style="{ '--cc': categoryColor(it.category) }" @click="emit('open', it)">
          <i /><span class="ellipsis">{{ it.title }}</span><b class="num">{{ it.score.toFixed(1) }}</b>
        </button>
      </aside>
    </div>
  </div>
</template>

<style scoped>
.classic { display: flex; flex-direction: column; gap: 16px; }
.heads { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; }
.hcard { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; text-align: left; background: linear-gradient(160deg, color-mix(in srgb, var(--cc) 12%, transparent), rgba(10, 22, 46, 0.55) 60%); border: 1px solid var(--line); border-top: 2px solid var(--cc); min-width: 0; }
.hcard:hover { border-color: color-mix(in srgb, var(--cc) 60%, transparent); }
.r1 { display: flex; align-items: center; gap: 6px; font-size: 11.5px; }
.rk { color: var(--cc); font-weight: 600; }
.cat { color: var(--cc); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc { margin-left: auto; color: var(--text-0); font-size: 14px; }
.hcard .ttl { font-size: 13.5px; line-height: 1.5; color: var(--text-0); font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.src { display: flex; gap: 10px; font-size: 11px; color: var(--text-2); margin-top: auto; }
.src i { display: inline-block; width: 6px; height: 6px; border-radius: 50%; margin-right: 4px; }
.body { display: grid; grid-template-columns: minmax(0, 900px) 300px; gap: 28px; justify-content: space-between; }
.md { padding: 26px 32px 40px; background: rgba(6, 14, 32, 0.6); border: 1px solid var(--line); }
.toc { position: sticky; top: 0; align-self: start; display: flex; flex-direction: column; gap: 2px; max-height: calc(100vh - 140px); overflow-y: auto; }
.toc .mt { margin-top: 18px; }
.ti { display: block; text-align: left; padding: 5px 10px; font-size: 13px; color: var(--text-1); border-left: 1px solid var(--line); }
.ti:hover { color: var(--cyan); border-left-color: var(--cyan); }
.ii { display: grid; grid-template-columns: 6px 1fr auto; align-items: center; gap: 8px; padding: 5px 8px; font-size: 12.5px; color: var(--text-1); text-align: left; }
.ii:hover { background: rgba(34, 228, 255, 0.05); color: var(--text-0); }
.ii i { width: 6px; height: 6px; background: var(--cc); }
.ii b { font-size: 11.5px; color: var(--text-2); font-weight: 400; }
</style>
