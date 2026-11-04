<script setup lang="ts" generic="T extends string">
const model = defineModel<T>({ required: true })
defineProps<{ options: { value: T; label: string; title?: string }[]; disabled?: boolean }>()
</script>

<template>
  <div class="seg" role="radiogroup">
    <button
      v-for="o in options"
      :key="o.value"
      type="button"
      role="radio"
      :aria-checked="model === o.value"
      :class="{ on: model === o.value }"
      :title="o.title"
      :disabled="disabled"
      @click="model = o.value"
    >{{ o.label }}</button>
  </div>
</template>
