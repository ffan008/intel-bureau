<script setup lang="ts">
import { dismissToast, toasts, type Toast } from '@/stores/toast'
import Icon from '../Icon.vue'

const ICON = { info: 'info', success: 'check', warn: 'alert', error: 'alert' } as const
function act(t: Toast): void {
  t.action?.run()
  dismissToast(t.id)
}
</script>

<template>
  <div class="toasts" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.level">
        <Icon :name="ICON[t.level]" :size="16" class="ic" />
        <div class="body">
          <div class="title">{{ t.title }}</div>
          <div v-if="t.detail" class="detail">{{ t.detail }}</div>
          <div v-if="t.hint" class="hint">建议：{{ t.hint }}</div>
          <button v-if="t.action" class="btn sm primary act" @click="act(t)">{{ t.action.label }}</button>
        </div>
        <button class="x" aria-label="关闭" @click="dismissToast(t.id)"><Icon name="close" :size="13" /></button>
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toasts {
  position: fixed;
  top: 18px;
  right: 18px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 360px;
  pointer-events: none;
}
.toast {
  --c: var(--cyan);
  position: relative;
  display: flex;
  gap: 10px;
  padding: 12px 12px 12px 14px;
  background: rgba(6, 14, 32, 0.94);
  border: 1px solid color-mix(in srgb, var(--c) 45%, transparent);
  border-left: 2px solid var(--c);
  border-radius: 3px;
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.5), 0 0 22px color-mix(in srgb, var(--c) 14%, transparent);
  backdrop-filter: blur(8px);
  pointer-events: auto;
}
.toast.success { --c: var(--green); }
.toast.warn { --c: var(--amber); }
.toast.error { --c: var(--red); }
.ic { color: var(--c); margin-top: 2px; }
.body { flex: 1; min-width: 0; }
.title { font-size: 13.5px; color: var(--text-0); font-weight: 600; line-height: 1.45; word-break: break-word; }
.detail { margin-top: 3px; font-size: 12px; color: var(--text-1); line-height: 1.55; word-break: break-word; }
.hint { margin-top: 4px; font-size: 12px; color: var(--text-2); line-height: 1.55; word-break: break-all; }
.act { margin-top: 8px; }
.x { color: var(--text-2); height: 18px; }
.x:hover { color: var(--text-0); }
.toast-enter-active, .toast-leave-active { transition: opacity 0.25s, transform 0.3s var(--ease-out-expo); }
.toast-enter-from { opacity: 0; transform: translateX(24px); }
.toast-leave-to { opacity: 0; transform: translateX(24px); }
</style>
