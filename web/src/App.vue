<script setup lang="ts">
import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { app } from './stores/app'
import { fetchOverview, loadAux, startLive } from './stores/live'
import BackgroundLayer from './components/bg/BackgroundLayer.vue'
import AppShell from './components/shell/AppShell.vue'
import BootScreen from './components/shell/BootScreen.vue'
import ToastHost from './components/ui/ToastHost.vue'
import ConfirmHost from './components/ui/ConfirmHost.vue'

const route = useRoute()

// 模式确定（真实后端或演示数据）后再开 SSE、拉 overview；全站共用一条事件流
watch(() => app.ready, (ready) => {
  if (!ready) return
  startLive()
  void fetchOverview()
  void loadAux()
}, { immediate: true })
</script>

<template>
  <BackgroundLayer :lite="route.meta.shell === true" />
  <BootScreen v-if="!app.ready" />
  <template v-else>
    <AppShell v-if="route.meta.shell">
      <RouterView />
    </AppShell>
    <RouterView v-else />
  </template>
  <ToastHost />
  <ConfirmHost />
</template>
