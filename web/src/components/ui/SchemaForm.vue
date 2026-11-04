<script setup lang="ts">
/** 按 ConfigField[] 动态生成表单（API.md ConfigField；平台适配器、推送通道、模型提供方共用） */
import { ref } from 'vue'
import type { ConfigField } from '@/api/types'
import HudSwitch from './HudSwitch.vue'
import { validateForm } from './schemaForm'

const props = withDefaults(defineProps<{ fields: ConfigField[]; masks?: Record<string, string>; cols?: 1 | 2; disabled?: boolean }>(), {
  masks: () => ({}), cols: 2,
})
const values = defineModel<Record<string, unknown>>({ required: true })
const errors = ref<Record<string, string>>({})
const reveal = ref<Record<string, boolean>>({})

function validate(): boolean {
  errors.value = validateForm(props.fields, values.value, props.masks)
  return Object.keys(errors.value).length === 0
}
defineExpose({ validate })

function set(key: string, v: unknown): void {
  values.value = { ...values.value, [key]: v }
  if (errors.value[key]) { const e = { ...errors.value }; delete e[key]; errors.value = e }
}
const str = (v: unknown) => (v === null || v === undefined ? '' : String(v))
const uid = Math.random().toString(36).slice(2, 8)
</script>

<template>
  <div v-if="!fields.length" class="none">此项无需额外配置。</div>
  <div v-else class="sf" :class="cols === 2 ? 'grid-2' : 'one'">
    <div v-for="f in fields" :key="f.key" class="field" :class="{ wide: f.type === 'textarea' || cols === 1 }">
      <template v-if="f.type === 'bool'">
        <HudSwitch :model-value="!!values[f.key]" :disabled="disabled" @update:model-value="set(f.key, $event)">
          {{ f.label }}
        </HudSwitch>
      </template>
      <template v-else>
        <label class="lbl" :for="`${uid}-${f.key}`">
          {{ f.label }}<span v-if="f.required" class="req">*</span>
          <span v-if="f.type === 'secret'" class="badge grey">密钥</span>
        </label>
        <select v-if="f.type === 'select'" :id="`${uid}-${f.key}`" class="select" :disabled="disabled"
          :value="str(values[f.key])" @change="set(f.key, ($event.target as HTMLSelectElement).value)">
          <option v-for="o in f.options ?? []" :key="o.value" :value="o.value">{{ o.label }}</option>
        </select>
        <textarea v-else-if="f.type === 'textarea'" :id="`${uid}-${f.key}`" class="textarea" :class="{ invalid: errors[f.key] }"
          :disabled="disabled" :placeholder="f.placeholder" :value="str(values[f.key])"
          @input="set(f.key, ($event.target as HTMLTextAreaElement).value)" />
        <div v-else-if="f.type === 'secret'" class="secret">
          <input :id="`${uid}-${f.key}`" class="input mono" :class="{ invalid: errors[f.key] }" :disabled="disabled"
            :type="reveal[f.key] ? 'text' : 'password'" autocomplete="new-password" spellcheck="false"
            :placeholder="masks[f.key] ? `已设置 ${masks[f.key]}（留空不修改）` : f.placeholder ?? '未设置'"
            :value="str(values[f.key])" @input="set(f.key, ($event.target as HTMLInputElement).value)" />
          <button type="button" class="btn sm ghost" @click="reveal[f.key] = !reveal[f.key]">{{ reveal[f.key] ? '隐藏' : '显示' }}</button>
        </div>
        <input v-else :id="`${uid}-${f.key}`" class="input" :class="{ invalid: errors[f.key], mono: f.type === 'url' || f.type === 'number' }"
          :disabled="disabled" :type="f.type === 'number' ? 'number' : f.type === 'url' ? 'url' : 'text'"
          :placeholder="f.placeholder" :value="str(values[f.key])" spellcheck="false"
          @input="set(f.key, f.type === 'number' ? (($event.target as HTMLInputElement).value === '' ? '' : Number(($event.target as HTMLInputElement).value)) : ($event.target as HTMLInputElement).value)" />
      </template>
      <div v-if="errors[f.key]" class="err">{{ errors[f.key] }}</div>
      <div v-else-if="f.help" class="help">{{ f.help }}</div>
    </div>
  </div>
</template>

<style scoped>
.sf.one { display: flex; flex-direction: column; gap: 14px; }
.field.wide { grid-column: 1 / -1; }
.secret { display: flex; gap: 6px; }
.none { font-size: 13px; color: var(--text-2); padding: 6px 0; }
</style>
