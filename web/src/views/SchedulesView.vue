<script setup lang="ts">
/** 调度中心（UI_DESIGN §5 /schedules）：任务卡片 + 运行历史（点开看阶段时间线和日志） */
import { onMounted, ref, watch } from 'vue'
import type { ChannelDTO, GroupDTO, RunDTO, ScheduleDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { live } from '@/stores/live'
import { RUN_STATUS } from '@/utils/meta'
import { fmtCny, fmtDuration, fmtInt, fmtShort } from '@/utils/format'
import { runProgress } from '@/utils/agents'
import HudPanel from '@/components/hud/HudPanel.vue'
import ScheduleCard from '@/components/schedules/ScheduleCard.vue'
import RunDrawer from '@/components/schedules/RunDrawer.vue'
import Icon from '@/components/Icon.vue'

const schedules = ref<ScheduleDTO[]>([])
const channels = ref<ChannelDTO[]>([])
const groups = ref<GroupDTO[]>([])
const runs = ref<RunDTO[]>([])
const creating = ref(false)
const open = ref<RunDTO | null>(null)

async function loadAll(): Promise<void> {
  const [s, c, g, r] = await Promise.allSettled([api.schedules(), api.channels(), api.groups({ whitelisted: true, limit: 500 }), api.runs(30)])
  if (s.status === 'fulfilled') schedules.value = s.value
  if (c.status === 'fulfilled') channels.value = c.value
  if (g.status === 'fulfilled') groups.value = g.value.items
  if (r.status === 'fulfilled') runs.value = r.value.items
}
async function loadRuns(): Promise<void> { try { runs.value = (await api.runs(30)).items } catch { /* toast */ } }
onMounted(loadAll)
watch(() => live.run?.status, () => void loadRuns())

function onSaved(s: ScheduleDTO): void {
  const i = schedules.value.findIndex((x) => x.id === s.id)
  if (i >= 0) schedules.value.splice(i, 1, s)
  else { schedules.value.push(s); creating.value = false }
}
const TRIGGER: Record<RunDTO['trigger'], string> = { manual: '手动', schedule: '定时', catchup: '补跑', demo: '演示' }
const dur = (r: RunDTO) => r.stages.reduce((a, s) => a + (s.duration_ms ?? 0), 0)
const schName = (id?: string) => schedules.value.find((s) => s.id === id)?.name
</script>

<template>
  <div class="page">
    <div class="page-intro">
      <span>定时任务按 cron 在 Asia/Shanghai 时区触发；电脑关机错过的运行会在启动后补跑一次。同一时间只运行一次流水线。</span>
      <span class="spacer" />
      <button class="btn primary" :disabled="creating" @click="creating = true"><Icon name="plus" />新建任务</button>
    </div>
    <div class="cards sch">
      <ScheduleCard v-if="creating" :schedule="null" :channels="channels" :groups="groups" @saved="onSaved" @cancel="creating = false" />
      <ScheduleCard v-for="s in schedules" :key="s.id" :schedule="s" :channels="channels" :groups="groups"
        @saved="onSaved" @removed="schedules = schedules.filter((x) => x.id !== s.id)" />
    </div>
    <div v-if="!schedules.length && !creating" class="empty"><span class="code">NO SCHEDULE</span>还没有定时任务</div>

    <HudPanel lite title="运行历史" code="RUN HISTORY">
      <template #actions><button class="btn sm" @click="loadRuns"><Icon name="refresh" />刷新</button></template>
      <table class="tbl">
        <thead><tr><th>开始时间</th><th>状态</th><th>触发</th><th>任务</th><th class="r">消息（有效/原始）</th><th class="r">情报</th><th class="r">tokens</th><th class="r">费用</th><th class="r">用时</th><th /></tr></thead>
        <tbody>
          <tr v-for="r in runs" :key="r.id" class="clickable" @click="open = r">
            <td class="num">{{ fmtShort(r.started_at) }}</td>
            <td>
              <span class="badge" :class="RUN_STATUS[r.status].cls">{{ RUN_STATUS[r.status].label }}</span>
              <span v-if="r.status === 'running'" class="prog num">{{ Math.round(runProgress(r) * 100) }}%</span>
              <span v-if="r.dry_run" class="badge violet" style="margin-left: 4px">预览</span>
            </td>
            <td>{{ TRIGGER[r.trigger] }}</td>
            <td class="dim">{{ schName(r.schedule_id) ?? '—' }}</td>
            <td class="r num">{{ fmtInt(r.totals.messages_clean) }} / {{ fmtInt(r.totals.messages_raw) }}</td>
            <td class="r num">{{ r.totals.items || '—' }}</td>
            <td class="r num dim">{{ fmtInt(r.totals.tokens_in + r.totals.tokens_out) }}</td>
            <td class="r num">{{ fmtCny(r.totals.cost_cny) }}</td>
            <td class="r num dim">{{ fmtDuration(dur(r)) }}</td>
            <td class="r"><Icon name="chevronRight" :size="14" class="dim" /></td>
          </tr>
          <tr v-if="!runs.length"><td colspan="10"><div class="empty">还没有运行记录</div></td></tr>
        </tbody>
      </table>
    </HudPanel>
    <RunDrawer :run="open" @close="open = null" />
  </div>
</template>

<style scoped>
.sch { grid-template-columns: repeat(auto-fill, minmax(440px, 1fr)); align-items: start; }
.clickable { cursor: pointer; }
.prog { margin-left: 6px; font-size: 11.5px; color: var(--cyan); }
</style>
