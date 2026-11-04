<script setup lang="ts">
/** 导入区：拖入导出文件或粘贴聊天文本 → POST /api/import（multipart） */
import { ref } from 'vue'
import type { ImportResult, Platform } from '@/api/types'
import { api } from '@/api/endpoints'
import { refreshOverview } from '@/stores/live'
import { notify } from '@/stores/toast'
import { PLATFORM } from '@/utils/meta'
import HudPanel from '../hud/HudPanel.vue'
import SegPicker from '../ui/SegPicker.vue'
import Icon from '../Icon.vue'

const props = defineProps<{ platform: Platform }>()
const emit = defineEmits<{ imported: [] }>()
const mode = ref<'file' | 'text'>('file')
const file = ref<File | null>(null)
const text = ref('')
const groupName = ref('')
const over = ref(false)
const busy = ref(false)
const result = ref<ImportResult | null>(null)
const MAX = 50 * 1024 * 1024
const SAMPLE = '🐯小象\n2026年10月25日 18:14\n以后每日风向标就发飞书了……'

function pick(f: File | null | undefined): void {
  if (!f) return
  if (f.size > MAX) { notify.error('文件超过 50 MB', { hint: '请按时间段分批导出' }); return }
  file.value = f
  result.value = null
  if (!groupName.value) groupName.value = f.name.replace(/\.[^.]+$/, '')
}
function onDrop(e: DragEvent): void {
  over.value = false
  pick(e.dataTransfer?.files?.[0])
}
async function submit(): Promise<void> {
  const fd = new FormData()
  if (mode.value === 'file') { if (!file.value) return; fd.append('file', file.value) } else { if (!text.value.trim()) return; fd.append('text', text.value) }
  fd.append('platform', props.platform)
  if (groupName.value.trim()) fd.append('group_name', groupName.value.trim())
  busy.value = true
  try {
    result.value = await api.importChat(fd)
    notify.ok(`已导入 ${result.value.imported} 条消息`, { detail: `群「${result.value.group.name}」· 格式 ${result.value.format}` })
    emit('imported')
    refreshOverview()
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="导入聊天记录" code="IMPORT">
    <template #actions><SegPicker v-model="mode" :options="[{ value: 'file', label: '文件' }, { value: 'text', label: '粘贴文本' }]" /></template>
    <div class="ib">
      <label v-if="mode === 'file'" class="drop" :class="{ over, has: file }" @dragover.prevent="over = true" @dragleave="over = false" @drop.prevent="onDrop">
        <input type="file" accept=".json,.csv,.txt,.html" class="sr-only" @change="pick(($event.target as HTMLInputElement).files?.[0])" />
        <Icon name="upload" :size="26" />
        <template v-if="file"><b>{{ file.name }}</b><span class="num">{{ (file.size / 1024).toFixed(1) }} KB · 点击更换</span></template>
        <template v-else><b>拖入导出文件，或点击选择</b><span>WeChatDataAnalysis / WeFlow / ChatLab JSON、通用 CSV、TXT</span></template>
      </label>
      <textarea v-else v-model="text" class="textarea mono" rows="7" :placeholder="`粘贴复制的聊天记录，例如：\n${SAMPLE}`" />
      <div class="row">
        <div class="field grow">
          <input v-model="groupName" class="input" :placeholder="`群名（导入到${PLATFORM[platform].label}）`" aria-label="群名" />
        </div>
        <button class="btn primary" :disabled="busy || (mode === 'file' ? !file : !text.trim())" @click="submit"><Icon name="upload" />{{ busy ? '导入中…' : '导入' }}</button>
      </div>
      <div v-if="result" class="res">
        <div class="r1"><Icon name="check" class="c-green" />群「{{ result.group.name }}」导入 <b class="num">{{ result.imported }}</b> 条，跳过 <b class="num">{{ result.skipped }}</b> 条 · 识别为 <code class="mono-inline">{{ result.format }}</code></div>
        <ul v-if="result.warnings.length" class="list-reset warn"><li v-for="w in result.warnings" :key="w">⚠ {{ w }}</li></ul>
      </div>
      <p class="hint-box">导入的群会自动加入白名单，可在下方表格里调整。导入只在本机解析，不会上传到云端。</p>
    </div>
  </HudPanel>
</template>

<style scoped>
.ib { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.drop { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; min-height: 150px; padding: 18px; border: 1px dashed var(--line-strong); border-radius: 3px; color: var(--text-2); font-size: 12px; text-align: center; cursor: pointer; background: rgba(4, 12, 28, 0.4); }
.drop b { font-size: 14px; color: var(--text-0); font-weight: 600; }
.drop :deep(svg) { color: var(--cyan); }
.drop.over, .drop:hover { border-color: var(--cyan); background: rgba(34, 228, 255, 0.05); }
.drop.has { border-style: solid; }
.grow { flex: 1; }
.res { padding: 10px 12px; border: 1px solid rgba(43, 255, 154, 0.3); background: rgba(43, 255, 154, 0.04); font-size: 13px; }
.r1 { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.r1 b { color: var(--text-0); }
.warn { margin-top: 6px; font-size: 12px; color: var(--amber); }
.hint-box { margin: 0; }
</style>
