<script setup lang="ts">
/** 推送通道（UI_DESIGN §5 /channels）：通道卡片（启用开关、发送测试、最近结果）+ 新增 / 编辑 */
import { onMounted, ref } from 'vue'
import type { ChannelDTO, ChannelKindDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { live } from '@/stores/live'
import { notify } from '@/stores/toast'
import { channelColor } from '@/utils/meta'
import { fmtAgo } from '@/utils/format'
import HudPanel from '@/components/hud/HudPanel.vue'
import HudSwitch from '@/components/ui/HudSwitch.vue'
import ChannelEditor from '@/components/channels/ChannelEditor.vue'
import Icon from '@/components/Icon.vue'
import { confirm } from '@/components/ui/confirm'

const kinds = ref<ChannelKindDTO[]>([])
const channels = ref<ChannelDTO[]>([])
const editorOpen = ref(false)
const editing = ref<ChannelDTO | null>(null)
const testing = ref<string | null>(null)

async function load(): Promise<void> {
  const [k, c] = await Promise.allSettled([api.channelKinds(), api.channels()])
  if (k.status === 'fulfilled') kinds.value = k.value
  if (c.status === 'fulfilled') { channels.value = c.value; live.channels = c.value }
}
onMounted(load)
const kindOf = (k: string) => kinds.value.find((x) => x.kind === k)
function summary(c: ChannelDTO): { k: string; v: string }[] {
  const schema = kindOf(c.kind)?.config_schema ?? []
  return schema.filter((f) => c.config[f.key] !== undefined && c.config[f.key] !== '' && f.type !== 'bool').slice(0, 3)
    .map((f) => ({ k: f.label, v: f.type === 'select' ? f.options?.find((o) => o.value === c.config[f.key])?.label ?? String(c.config[f.key]) : String(c.config[f.key]) }))
}
function upsert(c: ChannelDTO): void {
  const i = channels.value.findIndex((x) => x.id === c.id)
  if (i >= 0) channels.value.splice(i, 1, c)
  else channels.value.push(c)
  live.channels = [...channels.value]
}
async function setEnabled(c: ChannelDTO, v: boolean): Promise<void> {
  // 原样回传现有配置（密钥字段是掩码，按 API.md 约定表示不修改），避免后端把空 config 当成清空
  try { upsert(await api.updateChannel(c.id, { kind: c.kind, name: c.name, enabled: v, config: { ...c.config } })) } catch { /* toast */ }
}
async function test(c: ChannelDTO): Promise<void> {
  testing.value = c.id
  try {
    const r = await api.testChannel(c.id)
    if (r.ok) notify.ok(`「${c.name}」测试成功`, { detail: r.detail })
    else notify.error(`「${c.name}」测试失败`, { detail: r.detail })
    c.last_result = { ok: r.ok, detail: r.detail, at: new Date().toISOString() }
  } catch { /* toast */ } finally { testing.value = null }
}
async function remove(c: ChannelDTO): Promise<void> {
  if (!await confirm({ title: '删除通道', message: `确定删除「${c.name}」吗？`, detail: '引用它的定时任务将不再向它投递。', okText: '删除', danger: true })) return
  try { await api.deleteChannel(c.id); channels.value = channels.value.filter((x) => x.id !== c.id); live.channels = [...channels.value]; notify.ok('已删除') } catch { /* toast */ }
}
function edit(c: ChannelDTO | null): void { editing.value = c; editorOpen.value = true }
</script>

<template>
  <div class="page">
    <div class="page-intro">
      <span>每个通道独立投递，单个通道失败不影响其它通道。本地归档始终可用，作为兜底。</span>
      <span class="spacer" />
      <button class="btn primary" @click="edit(null)"><Icon name="plus" />新增通道</button>
    </div>
    <div class="cards">
      <HudPanel v-for="c in channels" :key="c.id" lite :title="c.name" :code="c.kind" :accent="channelColor(c.kind, kindOf(c.kind)?.platform_label)">
        <template #actions><HudSwitch :model-value="c.enabled" :label="`启用 ${c.name}`" sr-only @update:model-value="setEnabled(c, $event)" /></template>
        <div class="cc" :class="{ off: !c.enabled }">
          <div class="kind"><span class="badge grey">{{ kindOf(c.kind)?.platform_label ?? '—' }}</span>{{ kindOf(c.kind)?.label ?? c.kind }}</div>
          <dl class="kv">
            <template v-for="s in summary(c)" :key="s.k"><dt>{{ s.k }}</dt><dd class="ellipsis num">{{ s.v }}</dd></template>
          </dl>
          <div class="last" :class="c.last_result ? (c.last_result.ok ? 'ok' : 'bad') : ''">
            <template v-if="c.last_result"><b>{{ c.last_result.ok ? '✓' : '✗' }}</b><span class="ellipsis">{{ c.last_result.detail }}</span><em>{{ fmtAgo(c.last_result.at) }}</em></template>
            <span v-else class="dim">还没有投递记录</span>
          </div>
          <div class="row">
            <button class="btn sm" :disabled="testing === c.id" @click="test(c)"><Icon name="beaker" />{{ testing === c.id ? '发送中…' : '发送测试' }}</button>
            <button class="btn sm ghost" @click="edit(c)"><Icon name="edit" />编辑</button>
            <span class="spacer" />
            <button class="btn sm ghost icon" :aria-label="`删除 ${c.name}`" @click="remove(c)"><Icon name="trash" /></button>
          </div>
        </div>
      </HudPanel>
    </div>
    <div v-if="!channels.length" class="empty"><span class="code">NO CHANNEL</span>还没有推送通道</div>
    <ChannelEditor :open="editorOpen" :kinds="kinds" :editing="editing" @close="editorOpen = false" @saved="(c) => { upsert(c); editorOpen = false }" />
  </div>
</template>

<style scoped>
.cc { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.cc.off { opacity: 0.6; }
.kind { display: flex; align-items: center; gap: 8px; font-size: 13px; color: var(--text-1); }
.kv { margin: 0; font-size: 12.5px; }
.kv dd { color: var(--text-1); }
.last { display: flex; align-items: center; gap: 8px; padding: 8px 10px; font-size: 12.5px; background: rgba(4, 12, 28, 0.5); border: 1px solid var(--line); min-width: 0; }
.last.ok b { color: var(--green); }
.last.bad { border-color: rgba(255, 77, 94, 0.35); }
.last.bad b { color: var(--red); }
.last span { flex: 1; min-width: 0; color: var(--text-1); }
.last em { font-style: normal; font-size: 11.5px; color: var(--text-2); }
</style>
