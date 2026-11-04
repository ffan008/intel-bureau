<script setup lang="ts">
/**
 * 报告阅读器：头部信息 + 导出 md/html/json + 重新投递；
 * 正文：有 v2 字段（板块 / 专题）时用板块阅读器 ReportBoard，否则退回 v1 的 full_md 阅读器 ReportClassic。
 */
import { computed, nextTick, ref, watch } from 'vue'
import type { ExportFormat, IntelItemDTO, ReportDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { saveBlob } from '@/utils/download'
import { channelColor } from '@/utils/meta'
import { fmtDateTime, fmtInt, fmtPct } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import Icon from '../Icon.vue'
import DeliverModal from './DeliverModal.vue'
import ReportClassic from './ReportClassic.vue'
import ReportBoard from './ReportBoard.vue'
import { isV2Report } from './sections'

const props = defineProps<{ id: string | null }>()
const emit = defineEmits<{ open: [item: IntelItemDTO] }>()
const rep = ref<ReportDTO | null>(null)
const loading = ref(false)
const root = ref<HTMLElement | null>(null)
const deliverOpen = ref(false)
const exporting = ref<ExportFormat | null>(null)
const v2 = computed(() => isV2Report(rep.value))

watch(() => props.id, async (id) => {
  if (!id) { rep.value = null; return }
  loading.value = true
  try { rep.value = await api.report(id) } catch { rep.value = null } finally { loading.value = false }
  await nextTick()
  root.value?.closest('.scroller')?.scrollTo({ top: 0 })
}, { immediate: true })

async function exportAs(f: ExportFormat): Promise<void> {
  if (!rep.value) return
  exporting.value = f
  try { const { blob, filename } = await api.exportReport(rep.value.id, f); saveBlob(blob, filename) } catch { /* toast */ } finally { exporting.value = null }
}
</script>

<template>
  <div ref="root" class="rr">
    <div v-if="!rep" class="empty big"><span class="code">{{ loading ? 'LOADING' : 'NO REPORT' }}</span>{{ loading ? '正在载入报告…' : '在左侧选择一份报告' }}</div>
    <template v-else>
      <HudPanel lite class="head">
        <div class="h1">
          <div class="tt">
            <div class="date">{{ rep.date_label }} · <span class="num">{{ fmtDateTime(rep.created_at) }}</span> 生成
              <span v-if="!v2" class="badge grey" title="这份报告由 v1 生成，没有板块数据，按单页正文显示">v1 单页报告</span>
            </div>
            <h2>{{ rep.title }}</h2>
            <div class="stat-line">
              <span>窗口<b>{{ rep.window_label }}</b></span>
              <span>情报<b>{{ rep.items_total }}</b></span>
              <span v-if="v2">专题<b>{{ rep.articles?.length ?? 0 }}</b></span>
              <span v-if="v2">资源<b>{{ rep.resources?.length ?? 0 }}</b></span>
              <span>有效消息<b>{{ fmtInt(rep.stats.messages_clean) }} / {{ fmtInt(rep.stats.messages_raw) }}</b></span>
              <span>信噪比<b>{{ fmtPct(rep.stats.snr) }}</b></span>
            </div>
          </div>
          <div class="acts">
            <div class="seg" role="group" aria-label="导出">
              <button v-for="f in (['md', 'html', 'json'] as ExportFormat[])" :key="f" :disabled="!!exporting" @click="exportAs(f)">
                <Icon name="download" :size="13" /> {{ exporting === f ? '…' : f.toUpperCase() }}
              </button>
            </div>
            <button class="btn primary" @click="deliverOpen = true"><Icon name="channels" />重新投递</button>
          </div>
        </div>
        <div class="dlv">
          <span class="lbl">投递</span>
          <span v-for="d in rep.deliveries" :key="d.channel_id" class="chip" :class="{ bad: !d.ok }"><i class="pdot" :style="{ background: channelColor(d.kind) }" />{{ d.channel_name }}<b :class="d.ok ? 'c-green' : 'c-red'">{{ d.ok ? '✓' : '✗' }}</b></span>
          <span v-if="!rep.deliveries.length" class="dim">未投递（仅预览）</span>
        </div>
      </HudPanel>

      <ReportBoard v-if="v2" :rep="rep" />
      <ReportClassic v-else :rep="rep" @open="emit('open', $event)" />
    </template>
    <DeliverModal :open="deliverOpen" :report-id="rep?.id ?? null" :title="rep?.title" @close="deliverOpen = false" />
  </div>
</template>

<style scoped>
.rr { display: flex; flex-direction: column; gap: 16px; }
.big { min-height: 60vh; }
.head :deep(.hud-body) { padding: 16px 20px; }
.h1 { display: flex; gap: 20px; align-items: flex-start; }
.tt { flex: 1; min-width: 0; }
.date { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.tt h2 { margin: 4px 0 10px; font-size: 21px; font-weight: 700; line-height: 1.4; }
.acts { display: flex; gap: 10px; align-items: center; flex: none; }
.acts .seg button { display: inline-flex; align-items: center; gap: 5px; font-family: var(--font-num); font-size: 12px; }
.dlv { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--line); }
.dlv .lbl { font-size: 12px; color: var(--text-2); }
.dlv .chip b { margin-left: 6px; }
.dlv .chip.bad { border-color: rgba(255, 77, 94, 0.4); }
</style>
