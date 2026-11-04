<script setup lang="ts">
/**
 * 知识库（V2_KNOWLEDGE §3.3）：左侧检索（搜索、分类、标签云），中间条目列表，右侧阅读。
 * 深链接 /kb?id=<条目 ID>；筛选条件只放在页面状态里。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { KbListDTO, KbSummaryDTO } from '@/api/types'
import { ApiError } from '@/api/client'
import { api } from '@/api/endpoints'
import HudPanel from '@/components/hud/HudPanel.vue'
import KbFilters from '@/components/kb/KbFilters.vue'
import KbList from '@/components/kb/KbList.vue'
import KbReader from '@/components/kb/KbReader.vue'

const PAGE = 30
const route = useRoute()
const router = useRouter()
const q = ref('')
const category = ref('')
const tag = ref('')
const items = ref<KbSummaryDTO[]>([])
const total = ref(0)
const categories = ref<KbListDTO['categories']>([])
const tags = ref<KbListDTO['tags']>([])
const loading = ref(false)
const unavailable = ref('')
const selected = ref<string | null>(typeof route.query.id === 'string' ? route.query.id : null)
const filtered = computed(() => !!(q.value.trim() || category.value || tag.value))
let seq = 0

async function load(reset = true): Promise<void> {
  const my = ++seq
  loading.value = true
  try {
    const res = await api.kb({ q: q.value.trim() || undefined, category: category.value || undefined, tag: tag.value || undefined,
      limit: PAGE, offset: reset ? 0 : items.value.length }, { silent: true })
    if (my !== seq) return
    items.value = reset ? res.items : [...items.value, ...res.items]
    total.value = res.total
    // 选了分类时后端可能只回该分类的计数，保留完整的分类列表方便切换
    if (!category.value || !categories.value.length) categories.value = res.categories ?? []
    tags.value = res.tags ?? []
    unavailable.value = ''
    if (reset && !selected.value && items.value[0]) selected.value = items.value[0].id
  } catch (e) {
    if (my !== seq) return
    unavailable.value = e instanceof ApiError && e.status === 404 ? '后端还没有知识库接口（需要 v2 后端）' : `读取知识库失败：${(e as Error).message}`
  } finally { if (my === seq) loading.value = false }
}

let tm: ReturnType<typeof setTimeout> | null = null
watch(q, () => { if (tm) clearTimeout(tm); tm = setTimeout(() => void load(), 300) })
watch([category, tag], () => void load())
watch(() => route.query.id, (id) => { if (typeof id === 'string' && id !== selected.value) selected.value = id })
onMounted(() => void load())

function select(id: string): void {
  selected.value = id
  void router.replace({ query: { ...route.query, id } })
}
</script>

<template>
  <div class="page fill">
    <div class="kb grow">
      <HudPanel lite title="检索" code="FILTER" class="col">
        <KbFilters v-model:q="q" v-model:category="category" v-model:tag="tag" :categories="categories" :tags="tags" />
      </HudPanel>
      <HudPanel lite title="条目" code="ENTRIES" class="col">
        <template #actions><span class="cnt">共 <b class="num">{{ total }}</b> 条</span></template>
        <KbList :items="items" :selected="selected" :loading="loading" :total="total" :filtered="filtered" :unavailable="unavailable"
          @select="select" @more="load(false)" />
      </HudPanel>
      <KbReader :id="selected" @select="select" @tag="tag = $event" />
    </div>
  </div>
</template>

<style scoped>
.grow { flex: 1; min-height: 0; }
.kb { display: grid; grid-template-columns: 248px 360px minmax(0, 1fr); gap: 16px; min-height: 0; }
.col { height: 100%; min-height: 0; }
.col :deep(.hud-body) { display: flex; flex-direction: column; min-height: 0; }
.cnt { font-size: 12px; color: var(--text-2); }
.cnt b { color: var(--text-0); }
</style>
