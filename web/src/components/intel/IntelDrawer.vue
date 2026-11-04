<script setup lang="ts">
import { computed } from 'vue'
import type { IntelItemDTO } from '@/api/types'
import { categoryColor } from '@/utils/meta'
import Drawer from '../ui/Drawer.vue'
import IntelDetail from './IntelDetail.vue'

const props = defineProps<{ item: IntelItemDTO | null }>()
defineEmits<{ close: [] }>()
const accent = computed(() => categoryColor(props.item?.category))
</script>

<template>
  <Drawer :open="!!item" title="情报详情" code="INTEL DOSSIER" :width="600" :accent="accent" @close="$emit('close')">
    <IntelDetail v-if="item" :item="item" />
  </Drawer>
</template>
