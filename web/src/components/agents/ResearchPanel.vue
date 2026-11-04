<script setup lang="ts">
/** 专题与联网研究（V2_KNOWLEDGE §6）：每天专题篇数、research.*，密钥 research.deepseek_api_key / github_token 走 secrets */
import { computed, ref, watch } from 'vue'
import type { ConfigField, SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { MAX_FEATURES, RESEARCH_DEFAULTS, RESEARCH_SECRET_KEYS, SP, getAt, mergePatch, patchAt, readFirst, researchPath } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import HudPanel from '../hud/HudPanel.vue'
import SchemaForm from '../ui/SchemaForm.vue'
import Icon from '../Icon.vue'
import { initForm, serializeForm } from '../ui/schemaForm'

const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
const D = RESEARCH_DEFAULTS
const FIELDS: ConfigField[] = [
  { key: 'max_features', label: '每天专题篇数', type: 'number', default: MAX_FEATURES.def, help: `跨群合并后的话题取前 N 篇写成专题，${MAX_FEATURES.min}~${MAX_FEATURES.max}，默认 ${MAX_FEATURES.def}` },
  { key: 'provider', label: '联网搜索提供方', type: 'select', default: D.provider, options: [
    { value: 'deepseek', label: 'DeepSeek（联网搜索 + 读网页）' }, { value: 'none', label: '不联网（专题不写「扩展研究」）' }] },
  { key: 'enabled', label: '启用联网研究', type: 'bool', default: D.enabled },
  { key: 'per_article_queries', label: '每篇检索词数', type: 'number', default: D.per_article_queries, help: '模型为每篇专题生成的检索词个数，默认 2' },
  { key: 'max_searches', label: '每次运行最多搜索', type: 'number', default: D.max_searches, help: '达到后其余专题不再联网，默认 30' },
  { key: 'max_fetches', label: '每次运行最多读网页', type: 'number', default: D.max_fetches, help: '读取搜索结果正文的次数上限，默认 30' },
  { key: 'github_enrich', label: 'GitHub 链接补全星数、语言、简介', type: 'bool', default: D.github_enrich },
  { key: 'x_enrich', label: 'X 链接补全作者、点赞、转发', type: 'bool', default: D.x_enrich },
  { key: 'deepseek_api_key', label: 'DeepSeek API Key', type: 'secret', help: '留空则复用「模型提供方」里 OpenAI 兼容接口的 API Key' },
  { key: 'github_token', label: 'GitHub Token（可选）', type: 'secret', help: '不填也能用，只是匿名接口每小时限 60 次' },
]
const NUM_RANGE: Record<string, [number, number]> = {
  max_features: [MAX_FEATURES.min, MAX_FEATURES.max], per_article_queries: [1, 5], max_searches: [0, 200], max_fetches: [0, 200],
}
const values = ref<Record<string, unknown>>({})
const masks = ref<Record<string, string>>({})
const form = ref<InstanceType<typeof SchemaForm> | null>(null)
const busy = ref(false)
const consent = computed(() => readFirst<boolean>(props.settings, SP.cloudConsent, false) === true)
const on = computed(() => values.value.enabled !== false && values.value.provider !== 'none')

watch(() => props.settings, (s) => {
  const cur = { ...D, ...((getAt(s, researchPath) ?? {}) as Record<string, unknown>), max_features: readFirst(s, SP.maxFeatures, MAX_FEATURES.def) }
  const f = initForm(FIELDS, cur)
  values.value = f.values; masks.value = f.masks
}, { immediate: true })

async function save(): Promise<void> {
  if (form.value && !form.value.validate()) return
  const out = serializeForm(FIELDS, values.value)
  for (const [k, [lo, hi]] of Object.entries(NUM_RANGE)) {
    const v = out[k]
    const def = k === 'max_features' ? MAX_FEATURES.def : (D as Record<string, unknown>)[k]
    out[k] = typeof v === 'number' && Number.isFinite(v) ? Math.min(hi, Math.max(lo, Math.round(v))) : def
  }
  const { max_features: mf, ...research } = out
  // 密钥留空 = 不修改：不放进补丁（后端约定空串或掩码也表示不修改）
  for (const k of RESEARCH_SECRET_KEYS) if (!research[k]) delete research[k]
  busy.value = true
  try {
    const s = await api.updateSettings(mergePatch(patchAt(researchPath, research), patchAt(SP.maxFeatures[0], mf)))
    emit('saved', s)
    notify.ok('联网研究设置已保存', { detail: '下一次运行开始生效' })
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="专题与联网研究" code="RESEARCH" :accent="on ? 'var(--cyan)' : 'var(--text-2)'">
    <div class="rp">
      <div v-if="on && !consent" class="callout warn">尚未开启「云端同意」：联网研究会自动跳过（日志里会说明），专题照常生成，只是没有「扩展研究」一节。</div>
      <SchemaForm ref="form" v-model="values" :fields="FIELDS" :masks="masks" />
      <ul class="list-reset pts">
        <li><Icon name="shield" :size="14" />检索词只用话题、工具名、项目名，<b>不会</b>带群名、发言人昵称和手机号</li>
        <li><Icon name="link" :size="14" />提示词原文、提取码、链接由程序从群消息原文复制，不交给模型改写</li>
      </ul>
      <div class="row"><span class="spacer" /><button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button></div>
    </div>
  </HudPanel>
</template>

<style scoped>
.rp { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.pts { display: flex; flex-direction: column; gap: 6px; font-size: 12.5px; color: var(--text-1); line-height: 1.6; }
.pts li { display: flex; gap: 8px; align-items: flex-start; }
.pts li :deep(svg) { color: var(--cyan); margin-top: 3px; flex: none; }
.pts b { color: var(--text-0); }
</style>
