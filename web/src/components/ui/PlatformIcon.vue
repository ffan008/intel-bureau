<script setup lang="ts">
import { computed } from 'vue'
import type { Platform } from '@/api/types'
import { platformColor } from '@/utils/meta'
import Icon from '../Icon.vue'
import type { IconName } from '../icons'

const props = withDefaults(defineProps<{ platform: Platform | string; size?: number }>(), { size: 28 })
const icon = computed<IconName>(() => (['wechat', 'qq', 'feishu'].includes(props.platform) ? (props.platform as IconName) : 'demo'))
</script>

<template>
  <span class="pi" :style="{ width: size + 'px', height: size + 'px', '--c': platformColor(platform) }">
    <svg class="hex" viewBox="0 0 40 40" aria-hidden="true">
      <path d="M20 2 35.6 11v18L20 38 4.4 29V11z" fill="currentColor" fill-opacity="0.1" stroke="currentColor" stroke-opacity="0.6" stroke-width="1.4" />
    </svg>
    <Icon :name="icon" :size="Math.round(size * 0.5)" :stroke="1.6" />
  </span>
</template>

<style scoped>
.pi {
  position: relative;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  color: var(--c);
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--c) 40%, transparent));
}
.hex { position: absolute; inset: 0; width: 100%; height: 100%; }
</style>
