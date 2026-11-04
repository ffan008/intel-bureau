<script setup lang="ts">
/** 群表格：搜索、白名单开关、批量操作、权重滑块、标签、24h/7d 消息数、刷新群列表 */
import { computed, onMounted, ref, watch } from 'vue'
import type { GroupDTO, GroupPatch, Platform } from '@/api/types'
import { api } from '@/api/endpoints'
import { refreshOverview } from '@/stores/live'
import { notify } from '@/stores/toast'
import { PLATFORM } from '@/utils/meta'
import { fmtAgo, fmtInt } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import SegPicker from '../ui/SegPicker.vue'
import TagInput from '../ui/TagInput.vue'
import Icon from '../Icon.vue'

const props = defineProps<{ platform: Platform; version: number }>()
const items = ref<GroupDTO[]>([])
const total = ref(0)
const q = ref('')
const filter = ref<'all' | 'on' | 'off'>('all')
const sel = ref<Set<string>>(new Set())
const loading = ref(false)
const refreshing = ref(false)
const editingTags = ref<string | null>(null)

async function load(): Promise<void> {
  loading.value = true
  try {
    const res = await api.groups({ platform: props.platform, q: q.value.trim() || undefined, whitelisted: filter.value === 'all' ? undefined : filter.value === 'on', limit: 500 })
    items.value = res.items
    total.value = res.total
    sel.value = new Set([...sel.value].filter((k) => res.items.some((g) => g.key === k)))
  } catch { /* toast */ } finally { loading.value = false }
}
let qt: ReturnType<typeof setTimeout> | null = null
watch(q, () => { if (qt) clearTimeout(qt); qt = setTimeout(() => void load(), 250) })
watch([filter, () => props.platform, () => props.version], () => { sel.value = new Set(); void load() })
onMounted(() => void load())

const timers = new Map<string, ReturnType<typeof setTimeout>>()
async function patch(g: GroupDTO, body: GroupPatch, debounce = 0): Promise<void> {
  Object.assign(g, body)
  const tk = `${g.key}|${Object.keys(body).join(',')}`
  const prev = timers.get(tk)
  if (prev) clearTimeout(prev)
  const run = async () => {
    timers.delete(tk)
    try {
      const d = await api.patchGroup(g.key, body)
      Object.assign(g, d)
      if (body.whitelisted !== undefined) refreshOverview()
    } catch { void load() }
  }
  if (debounce) timers.set(tk, setTimeout(run, debounce))
  else await run()
}
async function bulk(on: boolean): Promise<void> {
  const keys = [...sel.value]
  if (!keys.length) return
  try {
    const r = await api.bulkGroups(keys, on)
    notify.ok(`已${on ? '加入' : '移出'}白名单 ${r.updated} 个群`)
    sel.value = new Set()
    await load()
    refreshOverview()
  } catch { /* toast */ }
}
async function refreshList(): Promise<void> {
  refreshing.value = true
  try {
    const r = await api.refreshGroups(props.platform)
    notify.ok(`群列表已刷新：新增 ${r.added}，更新 ${r.updated}，共 ${r.total} 个`)
    await load()
  } catch { /* toast */ } finally { refreshing.value = false }
}
const allChecked = computed(() => items.value.length > 0 && items.value.every((g) => sel.value.has(g.key)))
function toggleAll(): void { sel.value = allChecked.value ? new Set() : new Set(items.value.map((g) => g.key)) }
function toggle(k: string): void { const s = new Set(sel.value); if (s.has(k)) s.delete(k); else s.add(k); sel.value = s }
const wlCount = computed(() => items.value.filter((g) => g.whitelisted).length)
</script>

<template>
  <HudPanel lite :title="`${PLATFORM[platform].label}群列表`" code="GROUPS · WHITELIST">
    <template #actions>
      <span class="dim">白名单 <b class="num c-cyan">{{ wlCount }}</b> / {{ total }}</span>
      <button class="btn sm" :disabled="refreshing" @click="refreshList"><Icon name="refresh" :class="{ spin: refreshing }" />{{ refreshing ? '刷新中…' : '刷新群列表' }}</button>
    </template>
    <div class="toolbar">
      <input v-model="q" class="input" placeholder="搜索群名、别名、群号、标签" aria-label="搜索群" />
      <SegPicker v-model="filter" :options="[{ value: 'all', label: '全部' }, { value: 'on', label: '白名单' }, { value: 'off', label: '未加入' }]" />
      <span class="spacer" />
      <template v-if="sel.size">
        <span class="dim">已选 {{ sel.size }} 个</span>
        <button class="btn sm primary" @click="bulk(true)">加入白名单</button>
        <button class="btn sm" @click="bulk(false)">移出白名单</button>
      </template>
    </div>
    <div class="callout">只有加入白名单的群才会被读取和存储（QQ 实时上报收到非白名单群的消息会直接丢弃）；24h 显示 0 一般不是没读到，而是这个群最近一天没人说话，看右边「最近消息」就能判断。改完白名单要点上面采集面板的「立即采集」才会拉数据。</div>
    <div class="tw">
      <table class="tbl">
        <thead>
          <tr>
            <th style="width: 34px"><input type="checkbox" :checked="allChecked" aria-label="全选" @change="toggleAll" /></th>
            <th>群</th><th style="width: 76px">白名单</th><th style="width: 190px">权重</th><th>标签</th>
            <th class="r" style="width: 80px">24h</th><th class="r" style="width: 80px">7 天</th><th style="width: 110px">最近消息</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="g in items" :key="g.key" :class="{ sel: sel.has(g.key), off: !g.whitelisted }">
            <td><input type="checkbox" :checked="sel.has(g.key)" :aria-label="`选择 ${g.name}`" @change="toggle(g.key)" /></td>
            <td>
              <div class="gn">{{ g.alias || g.name }}<span v-if="g.alias" class="dim">（{{ g.name }}）</span></div>
              <div class="gid num">{{ g.native_id }}<template v-if="g.member_count"> · {{ g.member_count }} 人</template></div>
            </td>
            <td><HudSwitch :model-value="g.whitelisted" :label="`${g.name} 白名单`" sr-only @update:model-value="patch(g, { whitelisted: $event })" /></td>
            <td>
              <div class="wt">
                <input class="range" type="range" min="0" max="3" step="0.1" :value="g.weight" :style="{ '--pct': (g.weight / 3) * 100 + '%' }"
                  :aria-label="`${g.name} 权重`" @input="patch(g, { weight: Number(($event.target as HTMLInputElement).value) }, 500)" />
                <b class="num">{{ g.weight.toFixed(1) }}</b>
              </div>
            </td>
            <td>
              <TagInput v-if="editingTags === g.key" :model-value="g.tags" placeholder="回车添加" @update:model-value="patch(g, { tags: $event }, 600)" />
              <button v-else class="tags" @click="editingTags = g.key">
                <span v-for="t in g.tags" :key="t" class="chip">{{ t }}</span>
                <span v-if="!g.tags.length" class="dim">+ 标签</span>
              </button>
            </td>
            <td class="r num">{{ fmtInt(g.messages_24h) }}</td>
            <td class="r num dim">{{ fmtInt(g.messages_7d) }}</td>
            <td class="dim">{{ fmtAgo(g.last_message_at) }}</td>
          </tr>
          <tr v-if="!items.length && !loading"><td colspan="8"><div class="empty">没有符合条件的群。点「刷新群列表」从平台拉取，或在右上导入聊天记录。</div></td></tr>
        </tbody>
      </table>
    </div>
  </HudPanel>
</template>

<style scoped>
.toolbar { margin: 4px 0 10px; }
.callout { margin-bottom: 10px; }
.tw { max-height: 560px; overflow: auto; border: 1px solid var(--line); }
.tbl input[type='checkbox'] { accent-color: var(--cyan); }
tr.off .gn { color: var(--text-1); }
.gn { font-size: 13.5px; color: var(--text-0); }
.gid { font-size: 11px; color: var(--text-2); margin-top: 2px; }
.wt { display: flex; align-items: center; gap: 8px; }
.wt b { width: 26px; font-size: 12px; color: var(--cyan); }
.tags { display: flex; flex-wrap: wrap; gap: 4px; text-align: left; min-height: 22px; }
.tags:hover .dim { color: var(--cyan); }
</style>
