<script setup lang="ts">
/** 运行详情：阶段时间线（按耗时比例）+ 每阶段指标 + 运行日志 */
import { computed, ref, watch } from 'vue'
import type { LogDTO, RunDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { AGENT_BY_CODE, RUN_STATUS, STAGE_LABEL, STAGE_STATUS } from '@/utils/meta'
import { fmtCny, fmtDateTime, fmtDuration, fmtInt, fmtTime } from '@/utils/format'
import Drawer from '../ui/Drawer.vue'

const props = defineProps<{ run: RunDTO | null }>()
defineEmits<{ close: [] }>()
const logs = ref<LogDTO[]>([])
const level = ref<'all' | 'warn'>('all')
watch(() => props.run?.id, async (id) => {
  logs.value = []
  if (id) try { logs.value = await api.runLogs(id) } catch { /* toast */ }
}, { immediate: true })

const total = computed(() => Math.max(1, (props.run?.stages ?? []).reduce((a, s) => a + (s.duration_ms ?? 0), 0)))
const shown = computed(() => logs.value.filter((l) => l.level !== 'debug' && (level.value === 'all' || l.level === 'warn' || l.level === 'error')))
const TRIGGER: Record<RunDTO['trigger'], string> = { manual: '手动', schedule: '定时', catchup: '补跑', demo: '演示' }
const metricText = (m: Record<string, number | string>) => Object.entries(m).slice(0, 6).map(([k, v]) => `${k}=${typeof v === 'number' ? (Number.isInteger(v) ? fmtInt(v) : v.toFixed(3)) : v}`).join('  ')
</script>

<template>
  <Drawer :open="!!run" :title="run ? `运行 ${run.id}` : ''" code="RUN DETAIL" :width="720" @close="$emit('close')">
    <template v-if="run">
      <div class="hd">
        <span class="badge" :class="RUN_STATUS[run.status].cls">{{ RUN_STATUS[run.status].label }}</span>
        <span class="badge grey">{{ TRIGGER[run.trigger] }}</span>
        <span v-if="run.dry_run" class="badge violet">仅预览</span>
        <span class="dim num">{{ fmtDateTime(run.started_at, true) }} 开始 · 用时 {{ fmtDuration(total) }}</span>
      </div>
      <div v-if="run.error" class="callout err">{{ run.error }}</div>
      <dl class="kv tot">
        <dt>窗口</dt><dd class="num">{{ fmtDateTime(run.window_start) }} ~ {{ fmtDateTime(run.window_end) }}</dd>
        <dt>消息</dt><dd class="num">{{ fmtInt(run.totals.messages_clean) }} / {{ fmtInt(run.totals.messages_raw) }}（有效 / 原始）</dd>
        <dt>块 / 候选 / 情报</dt><dd class="num">{{ run.totals.chunks }} / {{ run.totals.candidates }} / {{ run.totals.items }}</dd>
        <dt>模型</dt><dd class="num">{{ run.totals.llm_provider }} · 输入 {{ fmtInt(run.totals.tokens_in) }} · 输出 {{ fmtInt(run.totals.tokens_out) }} · {{ fmtCny(run.totals.cost_cny) }}</dd>
      </dl>

      <h4 class="sec-title">阶段时间线<span class="en">STAGES · 12</span></h4>
      <div class="tlbar">
        <i v-for="s in run.stages" :key="s.name" :class="s.status" :style="{ flexGrow: Math.max(0.02, (s.duration_ms ?? 0) / total) }" :title="`${STAGE_LABEL[s.name]} · ${fmtDuration(s.duration_ms)}`" />
      </div>
      <ol class="stages list-reset">
        <li v-for="(s, i) in run.stages" :key="s.name" :class="s.status">
          <span class="n num">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="dot" />
          <div class="b">
            <div class="l1"><b>{{ STAGE_LABEL[s.name] }}</b><span class="disp ag">{{ s.agent }}</span><span class="dim">{{ AGENT_BY_CODE[s.agent]?.name }}</span>
              <span class="spacer" /><span class="badge" :class="STAGE_STATUS[s.status].cls">{{ STAGE_STATUS[s.status].label }}</span><span class="num du">{{ fmtDuration(s.duration_ms) }}</span></div>
            <div v-if="s.message" class="msg">{{ s.message }}</div>
            <div v-if="Object.keys(s.metrics ?? {}).length" class="mt num">{{ metricText(s.metrics) }}</div>
          </div>
        </li>
      </ol>

      <h4 class="sec-title">运行日志<span class="en">LOGS · {{ shown.length }}</span><span class="spacer" />
        <select v-model="level" class="select" style="width: 120px; height: 26px"><option value="all">全部级别</option><option value="warn">仅告警 / 错误</option></select>
      </h4>
      <div class="logs">
        <div v-for="(l, i) in shown" :key="i" class="ln" :class="l.level"><span class="ts">[{{ fmtTime(l.ts) }}]</span><span class="st">{{ l.stage ?? l.source }}</span>{{ l.message }}</div>
        <div v-if="!shown.length" class="dim">没有日志</div>
      </div>
    </template>
  </Drawer>
</template>

<style scoped>
.hd { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 12px; font-size: 12.5px; }
.tot { margin: 12px 0 22px; padding: 12px 14px; background: rgba(4, 12, 28, 0.5); border: 1px solid var(--line); font-size: 12.5px; }
.tlbar { display: flex; gap: 2px; height: 10px; margin-bottom: 14px; }
.tlbar i { flex-basis: 0; border-radius: 1px; background: rgba(80, 200, 255, 0.2); }
.tlbar i.done { background: linear-gradient(90deg, var(--cyan-dim), var(--cyan)); }
.tlbar i.failed { background: var(--red); }
.tlbar i.skipped { background: rgba(108, 134, 163, 0.35); }
.tlbar i.running { background: var(--amber); }
.stages { position: relative; margin-bottom: 22px; }
.stages::before { content: ''; position: absolute; left: 33px; top: 8px; bottom: 8px; width: 1px; background: var(--line); }
.stages li { position: relative; display: grid; grid-template-columns: 22px 14px 1fr; gap: 6px; padding: 7px 0; }
.n { font-size: 11px; color: var(--text-2); padding-top: 2px; }
.dot { width: 9px; height: 9px; margin: 5px 0 0 1px; border-radius: 50%; border: 1px solid var(--cyan-dim); background: var(--bg-1); position: relative; z-index: 1; }
.done .dot { background: var(--green); border-color: var(--green); box-shadow: 0 0 6px var(--green); }
.failed .dot { background: var(--red); border-color: var(--red); }
.running .dot { background: var(--cyan); border-color: var(--cyan); box-shadow: 0 0 8px var(--cyan); }
.l1 { display: flex; align-items: center; gap: 8px; font-size: 13px; }
.ag { font-size: 9.5px; color: var(--violet); letter-spacing: 1.5px; }
.du { width: 52px; text-align: right; font-size: 11.5px; color: var(--text-1); }
.msg { font-size: 12.5px; color: var(--text-1); margin-top: 2px; }
.mt { font-size: 11px; color: var(--text-2); margin-top: 2px; word-break: break-all; }
.logs { max-height: 360px; overflow: auto; padding: 10px 12px; background: rgba(0, 3, 9, 0.85); border: 1px solid var(--line); font-family: var(--font-num); font-size: 12px; line-height: 1.7; }
.ln { color: #9fe9ff; white-space: pre-wrap; word-break: break-all; }
.ln.warn { color: var(--amber); }
.ln.error { color: var(--red); }
.ts { color: #3f6b86; margin-right: 6px; }
.st { color: var(--violet); margin-right: 8px; }
</style>
