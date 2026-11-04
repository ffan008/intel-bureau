<script setup lang="ts">
/** 知识库条目列表：标题、分类、更新时间、版本数、来源数、风险徽标 */
import type { KbSummaryDTO } from '@/api/types'
import { categoryColor, categoryName } from '@/utils/meta'
import { fmtAgo, fmtDate } from '@/utils/format'
import RiskBadge from '../ui/RiskBadge.vue'

defineProps<{ items: KbSummaryDTO[]; selected: string | null; loading: boolean; total: number; filtered: boolean; unavailable: string }>()
const emit = defineEmits<{ select: [id: string]; more: [] }>()
const today = fmtDate(Date.now())
const fresh = (k: KbSummaryDTO): string => {
  if (fmtDate(k.created_at) === today) return '今日新增'
  if (fmtDate(k.updated_at) === today) return '今日更新'
  return ''
}
</script>

<template>
  <div class="kl">
    <div v-if="unavailable" class="empty"><span class="code">UNAVAILABLE</span>{{ unavailable }}</div>
    <template v-else>
      <ul class="list-reset ls">
        <li v-for="k in items" :key="k.id">
          <button class="ki" :class="{ on: k.id === selected }" :style="{ '--cc': categoryColor(k.category) }" @click="emit('select', k.id)">
            <div class="r1">
              <span class="cat">{{ categoryName(k.category) }}</span>
              <span v-if="fresh(k)" class="fr" :class="{ nw: fresh(k) === '今日新增' }">{{ fresh(k) }}</span>
              <span class="spacer" />
              <span class="t">{{ fmtAgo(k.updated_at) }}</span>
            </div>
            <div class="tt">{{ k.title }}</div>
            <div class="r2">
              <span>版本 <b class="num">{{ k.versions }}</b></span>
              <span>来源 <b class="num">{{ k.sources }}</b></span>
              <span class="spacer" />
              <RiskBadge :flags="k.risk_flags" :max="2" sm />
            </div>
          </button>
        </li>
      </ul>
      <button v-if="items.length < total" class="btn sm more" :disabled="loading" @click="emit('more')">{{ loading ? '加载中…' : `加载更多（还有 ${total - items.length} 条）` }}</button>
      <div v-if="!items.length && !loading" class="empty"><span class="code">EMPTY</span>{{ filtered ? '没有匹配的条目' : '知识库还没有条目：每天的专题文章会自动写入这里' }}</div>
    </template>
  </div>
</template>

<style scoped>
.kl { display: flex; flex-direction: column; gap: 10px; height: 100%; min-height: 0; }
.ls { flex: 1; min-height: 0; overflow-y: auto; padding-right: 4px; display: flex; flex-direction: column; gap: 4px; }
.ki { display: flex; flex-direction: column; gap: 5px; width: 100%; padding: 10px 12px; text-align: left; border: 1px solid transparent; border-left: 2px solid transparent; border-radius: 2px; }
.ki:hover { background: rgba(34, 228, 255, 0.04); }
.ki.on { background: linear-gradient(90deg, rgba(34, 228, 255, 0.1), rgba(10, 22, 46, 0.4)); border-color: var(--line); border-left-color: var(--cc); }
.r1, .r2 { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.cat { color: var(--cc); }
.fr { font-size: 11px; padding: 0 5px; border: 1px solid rgba(34, 228, 255, 0.35); color: var(--cyan); border-radius: 2px; }
.fr.nw { border-color: rgba(43, 255, 154, 0.4); color: var(--green); }
.t { font-size: 11.5px; }
.tt { font-size: 14.5px; line-height: 1.5; color: var(--text-0); font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.r2 b { color: var(--text-1); }
.more { align-self: center; }
</style>
