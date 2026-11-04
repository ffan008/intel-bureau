<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import Icon from '../Icon.vue'

const props = withDefaults(defineProps<{ open: boolean; title: string; code?: string; width?: number }>(), { width: 560 })
const emit = defineEmits<{ close: [] }>()
const box = ref<HTMLElement | null>(null)

function onKey(e: KeyboardEvent): void {
  if (e.key === 'Escape') emit('close')
}
watch(() => props.open, async (v) => {
  if (v) {
    document.addEventListener('keydown', onKey)
    await nextTick()
    box.value?.querySelector<HTMLElement>('input,select,textarea,button.primary')?.focus()
  } else document.removeEventListener('keydown', onKey)
}, { immediate: true })
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="open" class="mask" @mousedown.self="emit('close')">
        <div ref="box" class="modal" role="dialog" aria-modal="true" :aria-label="title" :style="{ width: width + 'px' }">
          <header class="head">
            <span class="sq" />
            <h3>{{ title }}</h3>
            <span v-if="code" class="code">{{ code }}</span>
            <span class="spacer" />
            <button class="btn ghost sm icon" aria-label="关闭" @click="emit('close')"><Icon name="close" /></button>
          </header>
          <div class="content"><slot /></div>
          <footer v-if="$slots.foot" class="foot"><slot name="foot" /></footer>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.mask {
  position: fixed;
  inset: 0;
  z-index: 900;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(2, 5, 12, 0.66);
  backdrop-filter: blur(3px);
}
.modal {
  max-width: calc(100vw - 48px);
  max-height: calc(100vh - 48px);
  display: flex;
  flex-direction: column;
  background: linear-gradient(180deg, rgba(14, 30, 62, 0.96), rgba(8, 18, 40, 0.97));
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  box-shadow: var(--shadow-pop), 0 0 40px rgba(34, 228, 255, 0.12);
}
.head { display: flex; align-items: center; gap: 8px; height: 46px; padding: 0 10px 0 16px; border-bottom: 1px solid var(--line); flex: none; }
.head h3 { margin: 0; font-size: 15px; font-weight: 600; }
.sq { width: 6px; height: 6px; background: var(--cyan); box-shadow: var(--glow-cyan); }
.code { font-family: var(--font-display); font-size: 10px; letter-spacing: 2px; color: var(--text-2); }
.spacer { flex: 1; }
.content { padding: 16px; overflow: auto; min-height: 0; }
.foot { display: flex; justify-content: flex-end; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--line); flex: none; }
.modal-enter-active, .modal-leave-active { transition: opacity 0.2s; }
.modal-enter-active .modal, .modal-leave-active .modal { transition: transform 0.28s var(--ease-out-expo), opacity 0.2s; }
.modal-enter-from, .modal-leave-to { opacity: 0; }
.modal-enter-from .modal, .modal-leave-to .modal { transform: translateY(10px) scale(0.98); opacity: 0; }
</style>
