<script setup lang="ts">
/** 情报源（UI_DESIGN §5 /sources）：三个平台标签页 */
import { computed, onMounted, ref } from 'vue'
import type { Platform, PlatformDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { live } from '@/stores/live'
import { HEALTH, PLATFORM, REAL_PLATFORMS } from '@/utils/meta'
import PlatformConfig from '@/components/sources/PlatformConfig.vue'
import GroupTable from '@/components/sources/GroupTable.vue'
import ImportBox from '@/components/sources/ImportBox.vue'

const tab = ref<Platform>('wechat')
const dtos = ref<PlatformDTO[]>([])
const version = ref(0)
const dto = computed(() => dtos.value.find((d) => d.platform === tab.value) ?? null)

async function load(): Promise<void> {
  try { dtos.value = await api.platforms() } catch { /* toast */ }
  if (!live.settings) live.settings = await api.settings({ silent: true }).catch(() => null)
}
function onUpdated(d: PlatformDTO): void {
  const i = dtos.value.findIndex((x) => x.platform === d.platform)
  if (i >= 0) dtos.value.splice(i, 1, d)
  else dtos.value.push(d)
}
onMounted(load)
</script>

<template>
  <div class="page">
    <div class="tabs" role="tablist">
      <button v-for="p in REAL_PLATFORMS" :key="p" role="tab" :aria-selected="tab === p" :class="{ on: tab === p }" @click="tab = p">
        <i class="pd" :style="{ background: PLATFORM[p].color }" />{{ PLATFORM[p].label }}
        <span v-if="dtos.find((d) => d.platform === p)" class="hs" :style="{ color: HEALTH[dtos.find((d) => d.platform === p)!.health].color }">●</span>
      </button>
    </div>
    <div class="top">
      <PlatformConfig :platform="tab" :dto="dto" @updated="onUpdated" />
      <ImportBox :platform="tab" @imported="version++" />
    </div>
    <GroupTable :platform="tab" :version="version" />
  </div>
</template>

<style scoped>
.pd { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px currentColor; }
.hs { font-size: 9px; }
.top { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); gap: 18px; align-items: start; }
</style>
