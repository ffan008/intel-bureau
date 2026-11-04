<script setup lang="ts">
import { computed } from 'vue'
import { ICONS, parseIcon, type IconName } from './icons'

const props = withDefaults(defineProps<{ name: IconName; size?: number; stroke?: number }>(), { size: 16, stroke: 1.7 })
const parts = computed(() => (ICONS[props.name] ?? []).map(parseIcon))
</script>

<template>
  <svg
    class="ico"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    :stroke-width="stroke"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
    focusable="false"
  >
    <template v-for="(p, i) in parts" :key="i">
      <circle v-if="p.t === 'c'" :cx="p.a[0]" :cy="p.a[1]" :r="p.a[2]" :fill="p.fill ? 'currentColor' : 'none'" :stroke="p.fill ? 'none' : undefined" />
      <rect v-else-if="p.t === 'r'" :x="p.a[0]" :y="p.a[1]" :width="p.a[2]" :height="p.a[3]" :rx="p.a[4] ?? 0" :fill="p.fill ? 'currentColor' : 'none'" :stroke="p.fill ? 'none' : undefined" />
      <path v-else :d="p.d" :fill="p.fill ? 'currentColor' : 'none'" :stroke="p.fill ? 'none' : undefined" />
    </template>
  </svg>
</template>

<style scoped>
.ico {
  display: inline-block;
  flex: none;
  vertical-align: middle;
}
</style>
