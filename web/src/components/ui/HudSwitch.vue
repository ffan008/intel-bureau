<script setup lang="ts">
const model = defineModel<boolean>({ default: false })
/** label 默认显示在开关右侧；srOnly 时只作为无障碍名称（表格里用） */
defineProps<{ disabled?: boolean; label?: string; srOnly?: boolean }>()
</script>

<template>
  <label class="sw-wrap" :class="{ disabled }">
    <button
      type="button"
      role="switch"
      class="switch"
      :class="{ on: model }"
      :aria-checked="model"
      :aria-label="label"
      :disabled="disabled"
      @click="model = !model"
    ><span class="knob" /></button>
    <span v-if="(label || $slots.default) && !srOnly" class="sw-label"><slot>{{ label }}</slot></span>
  </label>
</template>

<style scoped>
.sw-wrap { display: inline-flex; align-items: center; gap: 8px; cursor: pointer; font-size: 13px; color: var(--text-1); }
.sw-wrap.disabled { cursor: not-allowed; }
</style>
