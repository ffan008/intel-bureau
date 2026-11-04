<script setup lang="ts">
/** 风险徽标（V2_KNOWLEDGE §2）：违法高危红色；其它类别柔和琥珀色，只作提示 */
import { computed } from 'vue'
import { isSevereRisk, sortRisks } from '@/utils/risk'

const props = withDefaults(defineProps<{ flags?: readonly string[] | null; max?: number; sm?: boolean }>(), { flags: () => [], max: 99 })
const list = computed(() => sortRisks(props.flags ?? []))
const shown = computed(() => list.value.slice(0, props.max))
const rest = computed(() => list.value.slice(props.max))
const tip = (f: string) => (isSevereRisk(f) ? '违法高危：只记录和总结，不做联网扩展、不写成教程' : `${f}：照常收录，是否采用请自行判断`)
</script>

<template>
  <span v-if="list.length" class="rb" :class="{ sm }">
    <span v-for="f in shown" :key="f" class="risk-chip" :class="{ severe: isSevereRisk(f) }" :title="tip(f)">{{ f }}</span>
    <span v-if="rest.length" class="risk-chip" :title="rest.join('、')">+{{ rest.length }}</span>
  </span>
</template>

<style scoped>
.rb { display: inline-flex; flex-wrap: wrap; gap: 4px; align-items: center; }
.rb .risk-chip { margin: 0; }
.rb.sm .risk-chip { height: 18px; padding: 0 6px; font-size: 11px; }
</style>
