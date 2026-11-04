<script setup lang="ts">
/** 滚动数字（数值变化时从旧值滚到新值，1.2s easeOutExpo） */
import { computed } from 'vue'
import { useCountUp } from '@/composables/useTextFx'
import { fmtInt } from '@/utils/format'

const props = withDefaults(defineProps<{ value: number; decimals?: number; prefix?: string }>(), { decimals: 0, prefix: '' })
const { display, flash } = useCountUp(() => props.value)
const text = computed(() => props.prefix + (props.decimals ? display.value.toFixed(props.decimals) : fmtInt(display.value)))
</script>

<template>
  <span class="rn num" :class="{ hot: flash > 0 }"><span :key="flash" class="hl" />{{ text }}</span>
</template>

<style scoped>
.rn { position: relative; display: inline-block; }
.hl { position: absolute; inset: -2px -4px; background: radial-gradient(ellipse, rgba(34, 228, 255, 0.35), transparent 70%); opacity: 0; pointer-events: none; }
.hot .hl { animation: kf-flash 0.8s ease-out 1; }
</style>
