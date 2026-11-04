<script setup lang="ts">
/** 体检清单（GET /api/doctor） */
import { computed, onMounted, ref } from 'vue'
import type { DoctorCheck } from '@/api/types'
import { api } from '@/api/endpoints'
import { HEALTH } from '@/utils/meta'
import HudPanel from '../hud/HudPanel.vue'
import Icon from '../Icon.vue'

const checks = ref<DoctorCheck[]>([])
const busy = ref(false)
const at = ref<Date | null>(null)
async function run(): Promise<void> {
  busy.value = true
  try { checks.value = await api.doctor(); at.value = new Date() } catch { /* toast */ } finally { busy.value = false }
}
onMounted(run)
const counts = computed(() => ({
  ok: checks.value.filter((c) => c.status === 'ok').length,
  warn: checks.value.filter((c) => c.status === 'degraded' || c.status === 'unconfigured').length,
  bad: checks.value.filter((c) => c.status === 'down').length,
}))
const ICON = { ok: 'check', degraded: 'alert', down: 'close', disabled: 'info', unconfigured: 'info' } as const
</script>

<template>
  <HudPanel lite title="体检" code="DOCTOR">
    <template #actions>
      <span class="sum"><b class="c-green num">{{ counts.ok }}</b> 正常 · <b class="c-amber num">{{ counts.warn }}</b> 需关注 · <b class="c-red num">{{ counts.bad }}</b> 故障</span>
      <button class="btn sm" :disabled="busy" @click="run"><Icon name="refresh" :class="{ spin: busy }" />{{ busy ? '检查中…' : '重新检查' }}</button>
    </template>
    <ul class="list-reset dc">
      <li v-for="c in checks" :key="c.id" :class="`h-${c.status}`">
        <span class="ic"><Icon :name="ICON[c.status]" :size="13" :stroke="2.2" /></span>
        <div class="b">
          <div class="t"><b>{{ c.title }}</b><span class="st">{{ HEALTH[c.status].label }}</span></div>
          <div class="d">{{ c.detail }}</div>
          <div v-if="c.hint" class="h">建议：{{ c.hint }}</div>
        </div>
      </li>
      <li v-if="!checks.length && !busy" class="empty">没有体检结果</li>
    </ul>
  </HudPanel>
</template>

<style scoped>
.sum { font-size: 12px; color: var(--text-2); }
.dc { display: flex; flex-direction: column; }
.dc li { display: flex; gap: 12px; padding: 10px 2px; border-bottom: 1px solid rgba(80, 200, 255, 0.07); }
.ic { flex: none; width: 22px; height: 22px; display: flex; align-items: center; justify-content: center; border-radius: 50%; border: 1px solid currentColor; background: color-mix(in srgb, currentColor 12%, transparent); margin-top: 1px; }
.b { flex: 1; min-width: 0; }
.t { display: flex; align-items: center; gap: 10px; font-size: 13.5px; }
.t b { color: var(--text-0); font-weight: 600; }
.st { font-size: 11.5px; color: currentColor; }
.d { font-size: 12.5px; color: var(--text-1); margin-top: 2px; line-height: 1.6; }
.h { font-size: 12.5px; color: var(--amber); margin-top: 3px; line-height: 1.6; }
</style>
