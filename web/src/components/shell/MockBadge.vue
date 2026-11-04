<script setup lang="ts">
import { app } from '@/stores/app'
</script>

<template>
  <span v-if="app.mock" class="mock" :title="`当前显示的是演示数据，不是真实采集结果。\n原因：${app.mockReason}`" role="note">
    <i class="d" />演示数据 · <b class="disp">MOCK</b>
  </span>
</template>

<style scoped>
.mock {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 24px;
  padding: 0 10px;
  border: 1px solid rgba(180, 140, 255, 0.6);
  background: linear-gradient(90deg, rgba(139, 92, 255, 0.22), rgba(139, 92, 255, 0.06));
  color: #d7c6ff;
  font-size: 12px;
  white-space: nowrap;
  border-radius: 2px;
  box-shadow: 0 0 14px rgba(139, 92, 255, 0.25);
  cursor: help;
}
.mock b { font-size: 10px; letter-spacing: 2px; color: #fff; font-weight: 700; }
.d { width: 6px; height: 6px; background: var(--demo); box-shadow: 0 0 8px var(--demo); transform: rotate(45deg); }
</style>
