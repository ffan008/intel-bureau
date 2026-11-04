<script setup lang="ts">
import { computed } from 'vue'
import { live } from '@/stores/live'

const info = computed(() => {
  switch (live.stream) {
    case 'open': return { cls: 'ok', text: '实时', tip: '事件流已连接' }
    case 'connecting': return { cls: 'wait', text: '连接中', tip: '正在连接事件流' }
    case 'retrying': return { cls: 'bad', text: `重连 ${Math.ceil(live.retryInMs / 1000)}s`, tip: '事件流断开，正在按指数退避重连（最长 30 秒）' }
    default: return { cls: 'off', text: '离线', tip: '事件流未连接' }
  }
})
</script>

<template>
  <span class="sd" :class="info.cls" :title="info.tip"><i class="fx-loop" />{{ info.text }}</span>
</template>

<style scoped>
.sd { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-1); white-space: nowrap; }
.sd i { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 6px currentColor; }
.ok { color: var(--green); }
.ok i { animation: kf-breathe 2.4s ease-in-out infinite; }
.wait { color: var(--amber); }
.bad { color: var(--red); }
.bad i { animation: kf-blink 0.9s steps(1) infinite; }
.off { color: var(--text-2); }
</style>
