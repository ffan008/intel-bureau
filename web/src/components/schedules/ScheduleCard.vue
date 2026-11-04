<script setup lang="ts">
/** 定时任务卡片：cron 预设 + 人话解释 + 下次运行；平台/群范围、通道多选、TOP N、仅预览 */
import { computed, reactive, ref, watch } from 'vue'
import type { ChannelDTO, GroupDTO, Platform, ScheduleDTO, ScheduleInput } from '@/api/types'
import { api } from '@/api/endpoints'
import { notify } from '@/stores/toast'
import { live, refreshOverview } from '@/stores/live'
import { CRON_PRESETS, describeCron, nextRuns, parseCron } from '@/utils/cron'
import { PLATFORM, REAL_PLATFORMS, RUN_STATUS, channelColor } from '@/utils/meta'
import { WEEK_CN, fmtDateTime, fmtAgo, zoned } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import SegPicker from '../ui/SegPicker.vue'
import Icon from '../Icon.vue'
import { confirm } from '../ui/confirm'

const props = defineProps<{ schedule: ScheduleDTO | null; channels: ChannelDTO[]; groups: GroupDTO[] }>()
const emit = defineEmits<{ saved: [s: ScheduleDTO]; removed: []; cancel: [] }>()

const blank = (): ScheduleInput => ({ name: '新任务', enabled: true, cron: '0 8 * * *', timezone: 'Asia/Shanghai', window_mode: 'since_last', window_hours: 24,
  platforms: ['wechat', 'qq', 'feishu'], group_keys: [], channel_ids: props.channels.filter((c) => c.enabled).map((c) => c.id), top_n: 5, dry_run: false })
/** 响应式代理不能 structuredClone，按 JSON 深拷贝（字段都是 JSON 值） */
const plain = <T>(x: T): T => JSON.parse(JSON.stringify(x)) as T
const d = reactive<ScheduleInput>(blank())
const busy = ref(false)
const pickGroups = ref(false)
watch(() => props.schedule, (s) => {
  const { id: _i, next_run_at: _n, last_run: _l, ...rest } = s ?? ({ ...blank(), id: '' } as ScheduleDTO)
  Object.assign(d, plain(rest))
  pickGroups.value = d.group_keys.length > 0
}, { immediate: true })

const preset = computed({
  get: () => CRON_PRESETS.find((p) => p.cron === d.cron.trim())?.key ?? 'custom',
  set: (k: string) => { const p = CRON_PRESETS.find((x) => x.key === k); if (p) d.cron = p.cron },
})
const parsed = computed(() => parseCron(d.cron))
const human = computed(() => describeCron(d.cron))
const upcoming = computed(() => (parsed.value.ok ? nextRuns(d.cron, 3, d.timezone || 'Asia/Shanghai') : []))
const fmtNext = (t: Date) => { const z = zoned(t)!; return `${fmtDateTime(t)} ${WEEK_CN[z.wd]}` }
const domAndDow = computed(() => {
  const f = d.cron.trim().split(/\s+/)
  const restricted = (v: string | undefined) => !!v && v !== '*' && v !== '?'
  return f.length === 5 && restricted(f[2]) && restricted(f[4])
})
const wlGroups = computed(() => props.groups.filter((g) => g.whitelisted && d.platforms.includes(g.platform)))

function togglePlat(p: Platform): void {
  d.platforms = d.platforms.includes(p) ? d.platforms.filter((x) => x !== p) : [...d.platforms, p]
  d.group_keys = d.group_keys.filter((k) => d.platforms.some((pp) => k.startsWith(pp + ':')))
}
function toggleIn(list: 'group_keys' | 'channel_ids', v: string): void {
  d[list] = d[list].includes(v) ? d[list].filter((x) => x !== v) : [...d[list], v]
}
async function save(): Promise<void> {
  if (!d.name.trim()) { notify.warn('请填写任务名称'); return }
  if (!parsed.value.ok) { notify.warn('cron 表达式无效', { detail: parsed.value.error }); return }
  if (!d.platforms.length) { notify.warn('至少选择一个平台'); return }
  if (!pickGroups.value) d.group_keys = []
  busy.value = true
  try {
    const body = plain({ ...d, name: d.name.trim(), cron: d.cron.trim() })
    const s = props.schedule ? await api.updateSchedule(props.schedule.id, body) : await api.createSchedule(body)
    notify.ok(`已保存「${s.name}」`, { detail: describeCron(s.cron) })
    emit('saved', s)
    refreshOverview()
  } catch { /* toast */ } finally { busy.value = false }
}
async function runNow(): Promise<void> {
  if (!props.schedule) return
  try { const r = await api.runSchedule(props.schedule.id); live.run = r; live.sessionRun = true; notify.ok(`「${props.schedule.name}」已开始运行`, { detail: r.dry_run ? '仅预览，不会投递' : undefined }) } catch { /* toast */ }
}
async function remove(): Promise<void> {
  if (!props.schedule) { emit('cancel'); return }
  if (!await confirm({ title: '删除定时任务', message: `确定删除「${props.schedule.name}」吗？`, detail: '已有的运行记录和报告不受影响。', okText: '删除', danger: true })) return
  try { await api.deleteSchedule(props.schedule.id); notify.ok('已删除'); emit('removed'); refreshOverview() } catch { /* toast */ }
}
</script>

<template>
  <HudPanel lite :title="schedule ? d.name || '未命名' : '新建定时任务'" code="SCHEDULE" :accent="d.enabled ? 'var(--cyan)' : 'var(--text-2)'">
    <template #actions><HudSwitch v-model="d.enabled" label="启用" /></template>
    <div class="sc">
      <div class="field"><span class="lbl">任务名称</span><input v-model="d.name" class="input" maxlength="40" /></div>
      <div class="field">
        <span class="lbl">运行时间</span>
        <SegPicker v-model="preset" :options="[...CRON_PRESETS.map((p) => ({ value: p.key as string, label: p.label })), { value: 'custom', label: '自定义' }]" />
        <input v-model="d.cron" class="input mono" :class="{ invalid: !parsed.ok }" spellcheck="false" aria-label="cron 表达式" placeholder="分 时 日 月 周" />
        <div class="human" :class="{ bad: !parsed.ok }"><Icon :name="parsed.ok ? 'schedules' : 'alert'" :size="14" />{{ human }}<span class="tz">（{{ d.timezone }}）</span></div>
        <div v-if="domAndDow" class="help">「日」和「周」不能同时限定，保存时会被拒绝，请只保留其中一个。「周」按标准 cron：0 或 7 是周日，1 是周一。</div>
        <ul v-if="upcoming.length" class="next list-reset">
          <li v-for="(t, i) in upcoming" :key="i"><span class="num">{{ fmtNext(t) }}</span><em v-if="i === 0">下次</em></li>
        </ul>
      </div>
      <div class="grid-2">
        <div class="field">
          <span class="lbl">采集窗口</span>
          <SegPicker v-model="d.window_mode" :options="[{ value: 'since_last', label: '自上次运行' }, { value: 'fixed_hours', label: '固定小时' }]" />
          <div v-if="d.window_mode === 'fixed_hours'" class="row"><input v-model.number="d.window_hours" class="input num" type="number" min="1" max="168" style="width: 90px" /><span class="dim">小时</span></div>
          <div v-else class="help">从上次成功运行的结束时间开始，最多回溯 72 小时</div>
        </div>
        <div class="field">
          <span class="lbl">头条数 TOP N</span>
          <div class="row"><input v-model.number="d.top_n" class="input num" type="number" min="1" max="10" style="width: 90px" /><HudSwitch v-model="d.dry_run" label="仅预览（不投递）" /></div>
        </div>
      </div>
      <div class="field">
        <span class="lbl">平台范围</span>
        <div class="row wrap">
          <button v-for="p in REAL_PLATFORMS" :key="p" type="button" class="pill" :class="{ on: d.platforms.includes(p) }" :style="{ '--c': PLATFORM[p].color }" @click="togglePlat(p)">{{ PLATFORM[p].label }}</button>
          <span class="spacer" />
          <HudSwitch v-model="pickGroups" label="只选部分群" />
        </div>
        <div v-if="pickGroups" class="gpick">
          <label v-for="g in wlGroups" :key="g.key" class="gp"><input type="checkbox" :checked="d.group_keys.includes(g.key)" @change="toggleIn('group_keys', g.key)" /><i :style="{ background: PLATFORM[g.platform].color }" />{{ g.alias || g.name }}</label>
          <span v-if="!wlGroups.length" class="dim">所选平台没有白名单群</span>
        </div>
        <div v-else class="help">所选平台的全部白名单群</div>
      </div>
      <div class="field">
        <span class="lbl">推送通道</span>
        <div class="row wrap">
          <button v-for="c in channels" :key="c.id" type="button" class="pill" :class="{ on: d.channel_ids.includes(c.id), dis: !c.enabled }" :style="{ '--c': channelColor(c.kind) }" :title="c.enabled ? '' : '该通道已停用'" @click="toggleIn('channel_ids', c.id)">{{ c.name }}</button>
        </div>
      </div>
      <div v-if="schedule?.last_run" class="last">
        最近运行：<span class="badge" :class="RUN_STATUS[schedule.last_run.status].cls">{{ RUN_STATUS[schedule.last_run.status].label }}</span>
        <span class="dim">{{ fmtAgo(schedule.last_run.finished_at) }}</span>
      </div>
      <div class="row foot">
        <button class="btn danger sm" @click="remove"><Icon name="trash" />{{ schedule ? '删除' : '取消' }}</button>
        <span class="spacer" />
        <button v-if="schedule" class="btn" @click="runNow"><Icon name="play" />立即运行</button>
        <button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button>
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.sc { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.human { display: flex; align-items: center; gap: 6px; font-size: 14px; color: var(--cyan); font-weight: 600; }
.human.bad { color: var(--red); font-weight: 400; font-size: 12.5px; }
.tz { font-size: 11.5px; color: var(--text-2); font-weight: 400; }
.next { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px; color: var(--text-1); }
.next em { font-style: normal; margin-left: 6px; color: var(--amber); font-size: 11px; }
.pill { height: 28px; padding: 0 12px; font-size: 12.5px; color: var(--text-2); border: 1px solid var(--line); border-radius: 14px; }
.pill.on { color: var(--text-0); border-color: color-mix(in srgb, var(--c) 70%, transparent); background: color-mix(in srgb, var(--c) 14%, transparent); }
.pill.dis { opacity: 0.55; }
.gpick { display: flex; flex-wrap: wrap; gap: 6px 14px; padding: 10px; border: 1px solid var(--line); background: rgba(4, 12, 28, 0.4); }
.gp { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; cursor: pointer; }
.gp input { accent-color: var(--cyan); }
.gp i { width: 6px; height: 6px; border-radius: 50%; }
.last { display: flex; align-items: center; gap: 8px; font-size: 12px; color: var(--text-2); }
.foot { padding-top: 4px; border-top: 1px solid var(--line); padding-top: 12px; }
</style>
