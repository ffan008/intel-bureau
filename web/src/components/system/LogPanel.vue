<script setup lang="ts">
/** 系统日志：按级别筛选、关键字过滤、条数、自动刷新 */
import { computed, onMounted, ref, watch } from 'vue'
import type { LogDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { useInterval } from '@/composables/useTimers'
import { fmtDateTime } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import SegPicker from '../ui/SegPicker.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import Icon from '../Icon.vue'

const level = ref<LogDTO['level']>('info')
const limit = ref(200)
const q = ref('')
const auto = ref(false)
const logs = ref<LogDTO[]>([])
const busy = ref(false)
async function load(silent = false): Promise<void> {
  busy.value = true
  try { logs.value = await api.logs({ level: level.value, limit: limit.value }, { silent }) } catch { /* toast */ } finally { busy.value = false }
}
onMounted(() => void load())
watch([level, limit], () => void load())
useInterval(() => { if (auto.value) void load(true) }, () => 5000)
const shown = computed(() => {
  const k = q.value.trim().toLowerCase()
  const xs = k ? logs.value.filter((l) => `${l.source} ${l.message}`.toLowerCase().includes(k)) : logs.value
  return [...xs].reverse()
})
</script>

<template>
  <HudPanel lite title="系统日志" code="LOGS">
    <template #actions><HudSwitch v-model="auto" label="每 5 秒刷新" /></template>
    <div class="toolbar">
      <SegPicker v-model="level" :options="[{ value: 'debug', label: '调试' }, { value: 'info', label: '信息' }, { value: 'warn', label: '告警' }, { value: 'error', label: '错误' }]" />
      <input v-model="q" class="input" placeholder="过滤来源或内容" aria-label="过滤日志" />
      <select v-model.number="limit" class="select" style="width: 110px" aria-label="条数"><option :value="100">100 条</option><option :value="200">200 条</option><option :value="500">500 条</option></select>
      <span class="spacer" />
      <button class="btn sm" :disabled="busy" @click="load()"><Icon name="refresh" :class="{ spin: busy }" />刷新</button>
    </div>
    <div class="lv">
      <div v-for="(l, i) in shown" :key="i" class="ln" :class="l.level">
        <span class="ts">{{ fmtDateTime(l.ts, true) }}</span>
        <span class="lvl">{{ l.level.toUpperCase() }}</span>
        <span class="src">{{ l.source }}</span>
        <span class="msg">{{ l.message }}</span>
      </div>
      <div v-if="!shown.length" class="empty">没有符合条件的日志</div>
    </div>
    <p class="hint-box">日志不会写入密钥、令牌或完整消息正文；调试级别最多显示正文前 40 字。完整日志在 <code>data/logs/bureau.log</code>。</p>
  </HudPanel>
</template>

<style scoped>
.toolbar { margin: 4px 0 10px; }
.lv { height: 420px; overflow: auto; padding: 8px 10px; background: rgba(0, 3, 9, 0.85); border: 1px solid var(--line); font-family: var(--font-num); font-size: 12px; line-height: 1.75; }
.ln { display: grid; grid-template-columns: 150px 48px 140px 1fr; gap: 10px; color: #9fe9ff; }
.ln.debug { color: var(--text-2); }
.ln.warn { color: var(--amber); }
.ln.error { color: var(--red); }
.ts { color: #3f6b86; }
.lvl { font-size: 10.5px; }
.src { color: var(--violet); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.msg { word-break: break-all; }
.hint-box { margin: 10px 0 0; }
</style>
