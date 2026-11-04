<script setup lang="ts">
/**
 * 右侧抽屉。position: fixed —— 放在大屏 stage（带 transform）里时相对 1920×1080 画布定位，
 * 放在普通页面里时相对视口定位。
 */
import { onBeforeUnmount, watch } from 'vue'
import Icon from '../Icon.vue'

const props = withDefaults(defineProps<{ open: boolean; title?: string; code?: string; width?: number; accent?: string }>(), {
  width: 560, accent: 'var(--cyan)',
})
const emit = defineEmits<{ close: [] }>()
const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') emit('close') }
watch(() => props.open, (v) => (v ? document.addEventListener('keydown', onKey) : document.removeEventListener('keydown', onKey)), { immediate: true })
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Transition name="drawer">
    <div v-if="open" class="d-mask" @mousedown.self="emit('close')">
      <aside class="drawer" role="dialog" aria-modal="true" :aria-label="title" :style="{ width: width + 'px', '--accent': accent }">
        <span class="edge" aria-hidden="true" />
        <header class="head">
          <span class="sq" />
          <h3 class="ellipsis">{{ title }}</h3>
          <span v-if="code" class="code">{{ code }}</span>
          <span class="spacer" />
          <slot name="actions" />
          <button class="btn ghost sm icon" aria-label="关闭" @click="emit('close')"><Icon name="close" /></button>
        </header>
        <div class="content"><slot /></div>
      </aside>
    </div>
  </Transition>
</template>

<style scoped>
.d-mask { position: fixed; inset: 0; z-index: 800; background: rgba(2, 5, 12, 0.5); }
.drawer {
  position: absolute;
  top: 0;
  right: 0;
  bottom: 0;
  max-width: 100%;
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(12, 26, 54, 0.97), rgba(6, 14, 32, 0.98));
  border-left: 1px solid var(--line-strong);
  box-shadow: -24px 0 60px rgba(0, 0, 0, 0.55), -1px 0 24px rgba(34, 228, 255, 0.12);
}
.edge { position: absolute; left: -1px; top: 0; bottom: 0; width: 2px; background: linear-gradient(180deg, transparent, var(--accent) 30%, var(--accent) 70%, transparent); opacity: 0.8; }
.head { display: flex; align-items: center; gap: 8px; height: 52px; padding: 0 12px 0 20px; border-bottom: 1px solid var(--line); flex: none; }
.head h3 { margin: 0; font-size: 15px; font-weight: 600; min-width: 0; }
.sq { width: 6px; height: 6px; flex: none; background: var(--accent); box-shadow: 0 0 10px var(--accent); }
.code { font-family: var(--font-display); font-size: 10px; letter-spacing: 2px; color: var(--text-2); white-space: nowrap; }
.spacer { flex: 1; }
.content { flex: 1; min-height: 0; overflow-y: auto; padding: 18px 20px 28px; }
.drawer-enter-active, .drawer-leave-active { transition: opacity 0.25s; }
.drawer-enter-active .drawer, .drawer-leave-active .drawer { transition: transform 0.38s var(--ease-out-expo); }
.drawer-enter-from, .drawer-leave-to { opacity: 0; }
.drawer-enter-from .drawer, .drawer-leave-to .drawer { transform: translateX(100%); }
</style>
