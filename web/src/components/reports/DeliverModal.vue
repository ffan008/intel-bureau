<script setup lang="ts">
/** 重新投递：选择通道 → POST /api/reports/{id}/deliver → 显示逐通道结果 */
import { computed, ref, watch } from 'vue'
import type { DeliverResult } from '@/api/types'
import { api } from '@/api/endpoints'
import { live } from '@/stores/live'
import { notify } from '@/stores/toast'
import { channelColor } from '@/utils/meta'
import Modal from '../ui/Modal.vue'

const props = defineProps<{ open: boolean; reportId: string | null; title?: string }>()
const emit = defineEmits<{ close: [] }>()
const chosen = ref<string[]>([])
const busy = ref(false)
const result = ref<DeliverResult | null>(null)
const channels = computed(() => live.channels)

watch(() => props.open, async (v) => {
  if (!v) return
  result.value = null
  if (!live.channels.length) { try { live.channels = await api.channels() } catch { /* toast */ } }
  chosen.value = live.channels.filter((c) => c.enabled).map((c) => c.id)
})

function toggle(id: string): void {
  chosen.value = chosen.value.includes(id) ? chosen.value.filter((x) => x !== id) : [...chosen.value, id]
}
async function submit(): Promise<void> {
  if (!props.reportId || !chosen.value.length) return
  busy.value = true
  try {
    result.value = await api.deliverReport(props.reportId, chosen.value)
    const ok = result.value.results.filter((r) => r.ok).length
    if (ok === result.value.results.length) notify.ok(`已重新投递到 ${ok} 个通道`)
    else notify.warn(`投递完成：${ok} 成功，${result.value.results.length - ok} 失败`)
    live.channels = await api.channels({ silent: true }).catch(() => live.channels)
  } catch { /* toast */ } finally { busy.value = false }
}
const nameOf = (id: string) => channels.value.find((c) => c.id === id)?.name ?? id
</script>

<template>
  <Modal :open="open" title="重新投递" code="REDELIVER" :width="520" @close="emit('close')">
    <p class="sub">{{ title }}</p>
    <div v-if="!result" class="chs">
      <label v-for="c in channels" :key="c.id" class="ch" :class="{ on: chosen.includes(c.id), off: !c.enabled }">
        <input type="checkbox" :checked="chosen.includes(c.id)" @change="toggle(c.id)" />
        <i :style="{ background: channelColor(c.kind) }" />
        <span class="nm">{{ c.name }}</span>
        <span class="k">{{ c.kind }}</span>
        <span v-if="!c.enabled" class="badge grey">已停用</span>
      </label>
      <div v-if="!channels.length" class="empty">还没有推送通道，去「推送通道」页添加</div>
    </div>
    <ul v-else class="res list-reset">
      <li v-for="r in result.results" :key="r.channel_id" :class="r.ok ? 'ok' : 'bad'">
        <b>{{ r.ok ? '✓' : '✗' }}</b><span class="nm">{{ nameOf(r.channel_id) }}</span><span class="dt">{{ r.detail }}</span>
      </li>
    </ul>
    <template #foot>
      <button class="btn" @click="emit('close')">{{ result ? '关闭' : '取消' }}</button>
      <button v-if="!result" class="btn primary" :disabled="busy || !chosen.length" @click="submit">{{ busy ? '投递中…' : `投递到 ${chosen.length} 个通道` }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.sub { margin: 0 0 12px; font-size: 13px; color: var(--text-2); }
.chs { display: flex; flex-direction: column; gap: 6px; }
.ch { display: flex; align-items: center; gap: 10px; padding: 9px 12px; border: 1px solid var(--line); border-radius: 3px; cursor: pointer; font-size: 13.5px; }
.ch.on { border-color: var(--line-strong); background: rgba(34, 228, 255, 0.05); }
.ch.off { opacity: 0.6; }
.ch input { accent-color: var(--cyan); }
.ch i { width: 8px; height: 8px; border-radius: 50%; }
.nm { color: var(--text-0); }
.k { margin-left: auto; font-family: var(--font-num); font-size: 11.5px; color: var(--text-2); }
.res li { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px solid rgba(80, 200, 255, 0.08); font-size: 13px; }
.res .ok b { color: var(--green); }
.res .bad b { color: var(--red); }
.res .dt { margin-left: auto; color: var(--text-2); }
</style>
