<script setup lang="ts">
/** 图片与文档（V2_KNOWLEDGE §6 media.*）：下载被引用的图片和文件，图片 OCR，文档读取正文后提炼 */
import { computed, ref, watch } from 'vue'
import type { ConfigField, SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { MEDIA_DEFAULTS, SP, getAt, mediaPath, patchAt, readFirst } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import HudPanel from '../hud/HudPanel.vue'
import SchemaForm from '../ui/SchemaForm.vue'
import Icon from '../Icon.vue'
import { initForm, serializeForm } from '../ui/schemaForm'

const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
const D = MEDIA_DEFAULTS
const FIELDS: ConfigField[] = [
  { key: 'enabled', label: '提取群里的图片和文档', type: 'bool', default: D.enabled },
  { key: 'ocr', label: '图片文字识别（OCR）', type: 'select', default: D.ocr, options: [
    { value: 'windows', label: '本机 OCR（离线，默认；Windows 用系统 OCR，Mac 用 Vision）' }, { value: 'llm', label: '视觉模型（发给云端，需云端同意）' }, { value: 'off', label: '关闭' }] },
  { key: 'max_images', label: '每次最多图片', type: 'number', default: D.max_images, help: '只处理被情报引用的图片，默认 40' },
  { key: 'max_files', label: '每次最多文档', type: 'number', default: D.max_files, help: '默认 15' },
  { key: 'max_file_mb', label: '单个文件上限（MB）', type: 'number', default: D.max_file_mb, help: '超过的只记文件名，不下载，默认 20' },
]
const RANGE: Record<string, [number, number]> = { max_images: [0, 500], max_files: [0, 200], max_file_mb: [1, 500] }
const values = ref<Record<string, unknown>>({})
const form = ref<InstanceType<typeof SchemaForm> | null>(null)
const busy = ref(false)
const consent = computed(() => readFirst<boolean>(props.settings, SP.cloudConsent, false) === true)

watch(() => props.settings, (s) => {
  values.value = initForm(FIELDS, { ...D, ...((getAt(s, mediaPath) ?? {}) as Record<string, unknown>) }).values
}, { immediate: true })

async function save(): Promise<void> {
  if (form.value && !form.value.validate()) return
  const out = serializeForm(FIELDS, values.value)
  for (const [k, [lo, hi]] of Object.entries(RANGE)) {
    const v = out[k]
    out[k] = typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, Math.round(v))) : (D as Record<string, unknown>)[k]
  }
  busy.value = true
  try {
    const s = await api.updateSettings(patchAt(mediaPath, out))
    emit('saved', s)
    notify.ok('图片与文档设置已保存', { detail: '下一次运行开始生效' })
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="图片与文档" code="MEDIA" :accent="values.enabled ? 'var(--cyan)' : 'var(--text-2)'">
    <div class="mp">
      <div v-if="values.ocr === 'llm' && !consent" class="callout warn">选择了视觉模型 OCR，但尚未开启「云端同意」：运行时会跳过图片识别并在日志里说明。</div>
      <SchemaForm ref="form" v-model="values" :fields="FIELDS" />
      <ul class="list-reset pts">
        <li><Icon name="image" :size="14" />有用的图片做 OCR，要点写进专题和「图片与文档」板块；表情包照旧丢弃</li>
        <li><Icon name="reports" :size="14" />文档读取正文后提炼要点：PDF、Word、Excel、PPT、TXT、Markdown、CSV、HTML</li>
        <li><Icon name="lock" :size="14" />本机 OCR 不联网；只有选「视觉模型」时图片才会发给云端</li>
      </ul>
      <div class="row"><span class="spacer" /><button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button></div>
    </div>
  </HudPanel>
</template>

<style scoped>
.mp { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.pts { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--text-1); line-height: 1.6; }
.pts li { display: flex; gap: 8px; align-items: flex-start; }
.pts li :deep(svg) { color: var(--cyan); margin-top: 3px; flex: none; }
</style>
