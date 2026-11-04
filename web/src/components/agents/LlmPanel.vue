<script setup lang="ts">
/** 模型提供方：选择与配置、测试调用、并发与预算 */
import { computed, ref, watch } from 'vue'
import type { LlmTestResult, SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { SP, mergePatch, patchAt, providerConfigPaths, readFirst } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import HudPanel from '../hud/HudPanel.vue'
import SchemaForm from '../ui/SchemaForm.vue'
import Icon from '../Icon.vue'
import { initForm, serializeForm } from '../ui/schemaForm'

const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
const provider = ref('')
const values = ref<Record<string, unknown>>({})
const masks = ref<Record<string, string>>({})
const concurrency = ref(3)
const maxChunks = ref(40)
const budget = ref(2)
const form = ref<InstanceType<typeof SchemaForm> | null>(null)
const busy = ref(false)
const testing = ref(false)
const result = ref<LlmTestResult | null>(null)

const providers = computed(() => props.settings.llm_providers ?? [])
const schema = computed(() => providers.value.find((p) => p.key === provider.value)?.config_schema ?? [])
const consent = computed(() => readFirst(props.settings, SP.cloudConsent, false))
const isCloud = computed(() => provider.value !== 'offline')
const DESC: Record<string, string> = {
  auto: '优先已配置密钥的 API，其次本机 Claude Code，最后离线规则',
  openai_compat: 'DeepSeek、通义、Kimi、智谱、硅基流动、OpenRouter、本地 Ollama',
  anthropic: 'Anthropic Messages API（base_url 可改）',
  claude_code: '调用本机 claude CLI，提示词经 stdin 传入，禁用工具',
  offline: '不调用任何模型：按关键词、线索词和链接打分，只摘录原文',
}

function initProvider(key: string): void {
  const cfg = readFirst<Record<string, unknown>>(props.settings, providerConfigPaths(key), {})
  const f = initForm(providers.value.find((p) => p.key === key)?.config_schema ?? [], cfg)
  values.value = f.values; masks.value = f.masks
}
watch(() => props.settings, (s) => {
  provider.value = readFirst(s, SP.llmProvider, 'auto')
  concurrency.value = Number(readFirst(s, SP.llmConcurrency, 3))
  maxChunks.value = Number(readFirst(s, SP.llmMaxChunks, 40))
  budget.value = Number(readFirst(s, SP.llmBudgetCny, 5))
  initProvider(provider.value)
}, { immediate: true })
watch(provider, (k, old) => { if (old !== undefined && k !== old) initProvider(k) })

async function save(): Promise<void> {
  if (form.value && !form.value.validate()) return
  busy.value = true
  try {
    const cfg = serializeForm(schema.value, values.value)
    const parts = [patchAt(SP.llmProvider[0], provider.value), patchAt(SP.llmConcurrency[0], concurrency.value),
      patchAt(SP.llmMaxChunks[0], maxChunks.value), patchAt(SP.llmBudgetCny[0], budget.value)]
    if (schema.value.length) parts.push(patchAt(providerConfigPaths(provider.value)[0]!, cfg))
    const s = await api.updateSettings(mergePatch(...parts))
    emit('saved', s)
    notify.ok('模型设置已保存')
  } catch { /* toast */ } finally { busy.value = false }
}
async function test(): Promise<void> {
  testing.value = true
  result.value = null
  try { result.value = await api.testLlm() } catch { /* toast */ } finally { testing.value = false }
}
</script>

<template>
  <HudPanel lite title="模型提供方" code="LLM PROVIDER">
    <div class="lp">
      <div class="provs">
        <label v-for="p in providers" :key="p.key" class="pv" :class="{ on: provider === p.key }">
          <input v-model="provider" type="radio" :value="p.key" name="llm-provider" />
          <b>{{ p.label }}</b><span>{{ DESC[p.key] ?? p.key }}</span>
        </label>
      </div>
      <div v-if="isCloud && !consent" class="callout warn">尚未开启「云端同意」：运行时会自动退回离线规则，不会把群聊内容发给云端模型（本机 Claude Code 也会把内容发给 Anthropic，同样需要同意）。</div>
      <SchemaForm v-if="schema.length" ref="form" v-model="values" :fields="schema" :masks="masks" />
      <div class="grid-3">
        <div class="field"><span class="lbl">并发数</span><input v-model.number="concurrency" class="input num" type="number" min="1" max="8" /><span class="help">同时处理的对话块数，默认 3</span></div>
        <div class="field"><span class="lbl">每次最多块数</span><input v-model.number="maxChunks" class="input num" type="number" min="1" max="200" /><span class="help">超出的块改用离线规则，默认 40</span></div>
        <div class="field"><span class="lbl">单次费用上限（元）</span><input v-model.number="budget" class="input num" type="number" min="0" step="0.5" /><span class="help">按 token 估算；达到后剩余部分改用离线规则，0 表示不限</span></div>
      </div>
      <div v-if="result" class="res" :class="result.ok ? 'ok' : 'bad'">
        <b>{{ result.ok ? '✓ 调用成功' : '✗ 调用失败' }}</b>
        <span class="num">{{ result.provider }}{{ result.model ? ' · ' + result.model : '' }}{{ result.ok ? ` · ${result.latency_ms} ms` : '' }}</span>
        <span class="dt">{{ result.detail }}</span>
      </div>
      <div class="row">
        <button class="btn" :disabled="testing" @click="test"><Icon name="beaker" />{{ testing ? '调用中…' : '测试调用' }}</button>
        <span class="dim">测试用当前已保存的设置做一次最小调用</span>
        <span class="spacer" />
        <button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button>
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.lp { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.provs { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }
.pv { display: flex; flex-direction: column; gap: 3px; padding: 10px 12px; border: 1px solid var(--line); border-radius: 3px; cursor: pointer; position: relative; }
.pv input { position: absolute; opacity: 0; pointer-events: none; }
.pv b { font-size: 13.5px; color: var(--text-0); }
.pv span { font-size: 11.5px; color: var(--text-2); line-height: 1.5; }
.pv.on { border-color: var(--cyan); background: rgba(34, 228, 255, 0.07); box-shadow: inset 0 0 0 1px rgba(34, 228, 255, 0.2); }
.pv:focus-within { outline: 1px solid var(--cyan); }
.res { display: flex; flex-wrap: wrap; gap: 10px; align-items: baseline; padding: 10px 12px; font-size: 13px; border: 1px solid var(--line); background: rgba(4, 12, 28, 0.5); }
.res.ok { border-color: rgba(43, 255, 154, 0.35); }
.res.ok b { color: var(--green); }
.res.bad { border-color: rgba(255, 77, 94, 0.4); }
.res.bad b { color: var(--red); }
.res .dt { flex-basis: 100%; color: var(--text-1); font-size: 12.5px; }
</style>
