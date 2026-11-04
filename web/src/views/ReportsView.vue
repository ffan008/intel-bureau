<script setup lang="ts">
/** 情报档案（UI_DESIGN §5 /reports）：左侧报告时间轴，右侧阅读器（v2 板块阅读器 / v1 单页） */
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { IntelItemDTO } from '@/api/types'
import HudPanel from '@/components/hud/HudPanel.vue'
import ReportList from '@/components/reports/ReportList.vue'
import ReportReader from '@/components/reports/ReportReader.vue'
import IntelDrawer from '@/components/intel/IntelDrawer.vue'

const route = useRoute()
const router = useRouter()
const selected = ref<string | null>(typeof route.query.id === 'string' ? route.query.id : null)
const drawer = ref<IntelItemDTO | null>(null)

watch(() => route.query.id, (id) => { if (typeof id === 'string' && id !== selected.value) selected.value = id })
function select(id: string): void {
  selected.value = id
  // 换报告时保留当前板块（tab），专题序号（a）只对原报告有意义
  void router.replace({ query: { ...route.query, id, a: undefined } })
}
function onLoaded(first: string | null): void {
  if (!selected.value && first) selected.value = first
}
</script>

<template>
  <div class="page fill">
    <div class="split grow">
      <HudPanel lite title="报告时间轴" code="TIMELINE">
        <ReportList :selected="selected" @select="select" @loaded="onLoaded" />
      </HudPanel>
      <div class="scroller">
        <ReportReader :id="selected" @open="drawer = $event" />
      </div>
    </div>
    <IntelDrawer :item="drawer" @close="drawer = null" />
  </div>
</template>

<style scoped>
.grow { flex: 1; min-height: 0; }
.split { grid-template-columns: 320px minmax(0, 1fr); }
.scroller { min-height: 0; overflow-y: auto; padding-right: 6px; }
</style>
