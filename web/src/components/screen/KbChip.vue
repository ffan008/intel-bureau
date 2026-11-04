<script setup lang="ts">
/** 大屏知识库计数（overview.kb）：放在情报星图标题栏里，不占额外高度；v1 后端没有 kb 时不显示 */
import { computed } from 'vue'
import { live } from '@/stores/live'
import { fmtInt } from '@/utils/format'

const kb = computed(() => live.overview?.kb)
</script>

<template>
  <RouterLink v-if="kb" to="/kb" class="kbc" :title="`知识库共 ${kb.total} 条；今日新增 ${kb.new_today}、更新 ${kb.updated_today}`">
    <span class="l">知识库</span>
    <b class="num">{{ fmtInt(kb.total) }}</b>
    <span class="d">今日 <i class="num">+{{ kb.new_today }}</i> 新增 · <i class="num">{{ kb.updated_today }}</i> 更新</span>
  </RouterLink>
</template>

<style scoped>
.kbc { display: inline-flex; align-items: center; gap: 7px; height: 22px; margin-left: 10px; padding: 0 10px; font-size: 11.5px; color: var(--text-1); white-space: nowrap;
  border: 1px solid rgba(139, 92, 255, 0.45); background: rgba(139, 92, 255, 0.1); border-radius: 11px; }
.kbc:hover { text-decoration: none; border-color: #a98bff; color: var(--text-0); }
.l { color: #c4b2ff; }
b { font-size: 13px; color: var(--text-0); }
.d { color: var(--text-2); }
.d i { font-style: normal; color: var(--text-0); }
</style>
