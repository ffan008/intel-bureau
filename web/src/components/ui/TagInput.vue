<script setup lang="ts">
import { ref } from 'vue'

const model = defineModel<string[]>({ default: () => [] })
const props = withDefaults(defineProps<{ placeholder?: string; max?: number; color?: string }>(), { placeholder: '输入后回车', max: 200 })
const draft = ref('')

function add(): void {
  const parts = draft.value.split(/[,，、\n]/).map((s) => s.trim()).filter(Boolean)
  if (!parts.length) return
  const next = [...model.value]
  for (const p of parts) if (!next.includes(p) && next.length < props.max) next.push(p.slice(0, 40))
  model.value = next
  draft.value = ''
}
function remove(i: number): void {
  model.value = model.value.filter((_, j) => j !== i)
}
function onKey(e: KeyboardEvent): void {
  if (e.key === 'Enter' || e.key === ',' || e.key === '，') { e.preventDefault(); add() }
  else if (e.key === 'Backspace' && !draft.value && model.value.length) remove(model.value.length - 1)
}
</script>

<template>
  <div class="tags" @click="($el as HTMLElement).querySelector('input')?.focus()">
    <span v-for="(t, i) in model" :key="t" class="chip" :style="color ? { borderColor: color + '55', color } : undefined">
      {{ t }}<button type="button" class="x" :aria-label="`移除 ${t}`" @click.stop="remove(i)">×</button>
    </span>
    <input v-model="draft" class="in" :placeholder="model.length ? '' : placeholder" @keydown="onKey" @blur="add" />
  </div>
</template>

<style scoped>
.tags {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  min-height: 34px;
  padding: 5px 8px;
  background: rgba(3, 8, 20, 0.62);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  cursor: text;
}
.tags:focus-within { border-color: var(--cyan); box-shadow: 0 0 0 3px rgba(34, 228, 255, 0.1); }
.in { flex: 1; min-width: 100px; height: 22px; border: 0; outline: none; background: transparent; font-size: 13px; }
.in::placeholder { color: var(--text-2); }
.chip { height: 22px; }
</style>
