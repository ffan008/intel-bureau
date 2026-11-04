<script setup lang="ts">
/** 情报档案左侧时间轴：日期、头条数、投递状态；搜索与分页 */
import { onMounted, ref, watch } from 'vue'
import type { ReportSummaryDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { live } from '@/stores/live'
import { fmtShort } from '@/utils/format'
import { channelColor } from '@/utils/meta'
import Icon from '../Icon.vue'

defineProps<{ selected: string | null }>()
const emit = defineEmits<{ select: [id: string]; loaded: [first: string | null] }>()
const items = ref<ReportSummaryDTO[]>([])
const total = ref(0)
const q = ref('')
const loading = ref(false)
const PAGE = 20

async function load(reset = true): Promise<void> {
  loading.value = true
  try {
    const res = await api.reports({ limit: PAGE, offset: reset ? 0 : items.value.length, q: q.value.trim() || undefined })
    items.value = reset ? res.items : [...items.value, ...res.items]
    total.value = res.total
    if (reset) emit('loaded', items.value[0]?.id ?? null)
  } catch { /* toast 已弹出 */ } finally { loading.value = false }
}
let t: ReturnType<typeof setTimeout> | null = null
watch(q, () => { if (t) clearTimeout(t); t = setTimeout(() => void load(), 300) })
watch(() => live.reportsVersion, () => void load())
onMounted(() => void load())
const okCount = (r: ReportSummaryDTO) => r.deliveries.filter((d) => d.ok).length
</script>

<template>
  <div class="rl">
    <div class="search">
      <Icon name="search" :size="14" class="si" />
      <input v-model="q" class="input" placeholder="搜索标题、情报、标签" aria-label="搜索报告" />
    </div>
    <div class="meta">共 <b class="num">{{ total }}</b> 份报告</div>
    <ol class="tl">
      <li v-for="r in items" :key="r.id" :class="{ on: r.id === selected }">
        <button class="it" @click="emit('select', r.id)">
          <span class="node" aria-hidden="true" />
          <div class="d">
            <span class="date">{{ r.date_label }}</span>
            <span v-if="r.title.includes('加刊')" class="badge violet">加刊</span>
            <span class="t num">{{ fmtShort(r.created_at) }}</span>
          </div>
          <div class="hl ellipsis">{{ r.headlines[0]?.title ?? '（无头条）' }}</div>
          <div class="st">
            <span>情报 <b class="num">{{ r.items_total }}</b></span>
            <span>头条 <b class="num">{{ r.headlines.length }}</b></span>
            <span class="dv" :title="r.deliveries.map((d) => `${d.channel_name}：${d.ok ? '成功' : '失败'}`).join('\n')">
              <i v-for="d in r.deliveries" :key="d.channel_id" :class="{ bad: !d.ok }" :style="{ '--c': channelColor(d.kind) }" />
              <em :class="okCount(r) < r.deliveries.length ? 'c-red' : 'c-green'">{{ r.deliveries.length ? `${okCount(r)}/${r.deliveries.length}` : '未投递' }}</em>
            </span>
          </div>
        </button>
      </li>
    </ol>
    <button v-if="items.length < total" class="btn sm more" :disabled="loading" @click="load(false)">{{ loading ? '加载中…' : '加载更多' }}</button>
    <div v-if="!items.length && !loading" class="empty"><span class="code">EMPTY</span>{{ q ? '没有匹配的报告' : '还没有报告，去大屏点「立即出报」' }}</div>
  </div>
</template>

<style scoped>
.rl { display: flex; flex-direction: column; gap: 10px; min-height: 0; height: 100%; }
.search { position: relative; }
.search .input { padding-left: 30px; }
.si { position: absolute; left: 10px; top: 9px; color: var(--text-2); }
.meta { font-size: 12px; color: var(--text-2); }
.meta b { color: var(--text-0); }
.tl { list-style: none; margin: 0; padding: 0 4px 0 0; overflow-y: auto; flex: 1; min-height: 0; position: relative; }
.tl::before { content: ''; position: absolute; left: 9px; top: 6px; bottom: 6px; width: 1px; background: linear-gradient(180deg, var(--line-strong), var(--line) 60%, transparent); }
.it { position: relative; display: block; width: 100%; text-align: left; padding: 10px 12px 10px 28px; border: 1px solid transparent; border-radius: 2px; }
.it:hover { background: rgba(34, 228, 255, 0.04); }
.on .it { background: linear-gradient(90deg, rgba(34, 228, 255, 0.1), rgba(10, 22, 46, 0.4)); border-color: var(--line); }
.node { position: absolute; left: 5px; top: 15px; width: 9px; height: 9px; border-radius: 50%; border: 1px solid var(--cyan-dim); background: var(--bg-0); }
.on .node { background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 10px var(--cyan); }
.d { display: flex; align-items: center; gap: 8px; }
.date { font-size: 14px; font-weight: 600; color: var(--text-0); }
.t { margin-left: auto; font-size: 11px; color: var(--text-2); }
.hl { margin-top: 4px; font-size: 12.5px; color: var(--text-1); }
.st { display: flex; align-items: center; gap: 14px; margin-top: 6px; font-size: 11.5px; color: var(--text-2); }
.st b { color: var(--text-1); }
.dv { display: inline-flex; align-items: center; gap: 3px; margin-left: auto; }
.dv i { width: 6px; height: 6px; border-radius: 50%; background: var(--c); opacity: 0.85; }
.dv i.bad { background: transparent; border: 1px solid var(--red); }
.dv em { font-style: normal; margin-left: 4px; font-family: var(--font-num); }
.more { align-self: center; }
</style>
