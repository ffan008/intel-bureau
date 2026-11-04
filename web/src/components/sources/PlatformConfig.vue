<script setup lang="ts">
/** 平台配置：启用、适配器选择、按 config_schema 动态表单、测试连接、健康状态与修复建议 */
import { computed, ref, watch } from 'vue'
import type { Platform, PlatformDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { readFirst, sourceConfigPaths } from '@/api/settingsPaths'
import { live, refreshOverview } from '@/stores/live'
import { notify } from '@/stores/toast'
import { HEALTH, PLATFORM } from '@/utils/meta'
import { fmtAgo, fmtInt } from '@/utils/format'
import HudPanel from '../hud/HudPanel.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import SchemaForm from '../ui/SchemaForm.vue'
import PlatformIcon from '../ui/PlatformIcon.vue'
import Icon from '../Icon.vue'
import { initForm, serializeForm } from '../ui/schemaForm'

const props = defineProps<{ platform: Platform; dto: PlatformDTO | null }>()
const emit = defineEmits<{ updated: [dto: PlatformDTO] }>()
const adapter = ref('')
const values = ref<Record<string, unknown>>({})
const masks = ref<Record<string, string>>({})
const form = ref<InstanceType<typeof SchemaForm> | null>(null)
const saving = ref(false)
const testing = ref(false)
const collecting = ref(false)
const baseline = ref('')

const schema = computed(() => props.dto?.adapters.find((a) => a.key === adapter.value)?.config_schema ?? [])
const health = computed(() => props.dto?.health ?? 'unconfigured')
const snapshot = () => JSON.stringify([adapter.value, values.value])
const dirty = computed(() => !!baseline.value && snapshot() !== baseline.value)

function initFor(key: string, asBaseline: boolean, src: PlatformDTO | null = props.dto): void {
  // 真实后端在 PlatformDTO.config 里给出当前适配器的配置（密钥已掩码）；切到别的适配器或 mock 时再从 settings 里找
  const fromDto = src && src.adapter === key && src.config ? src.config : null
  const cfg = fromDto ?? readFirst<Record<string, unknown>>(live.settings, sourceConfigPaths(props.platform, key), {})
  const f = initForm(src?.adapters.find((a) => a.key === key)?.config_schema ?? [], cfg)
  values.value = f.values
  masks.value = f.masks
  if (asBaseline) baseline.value = snapshot()
}
watch(() => [props.dto?.adapter, props.platform, live.settings] as const, () => {
  if (!props.dto || dirty.value) return
  adapter.value = props.dto.adapter
  initFor(adapter.value, true)
}, { immediate: true })
watch(adapter, (k, old) => { if (old && k !== old) initFor(k, false) })

async function setEnabled(v: boolean): Promise<void> {
  try {
    const d = await api.updatePlatform(props.platform, { enabled: v })
    emit('updated', d)
    notify.ok(`${PLATFORM[props.platform].label}已${v ? '启用' : '停用'}`)
    refreshOverview()
  } catch { /* toast */ }
}
async function save(): Promise<void> {
  if (!form.value?.validate()) return
  saving.value = true
  try {
    const d = await api.updatePlatform(props.platform, { adapter: adapter.value, config: serializeForm(schema.value, values.value) })
    emit('updated', d)
    baseline.value = ''
    live.settings = await api.settings({ silent: true }).catch(() => live.settings)
    adapter.value = d.adapter
    initFor(d.adapter, true, d)
    notify.ok('采集配置已保存', { detail: '密钥字段留空的保持原值不变' })
    refreshOverview()
  } catch { /* toast */ } finally { saving.value = false }
}
async function test(): Promise<void> {
  testing.value = true
  try {
    const d = await api.testPlatform(props.platform)
    emit('updated', d)
    const h = HEALTH[d.health]
    if (d.health === 'ok') notify.ok(`${d.label}连接正常`, { detail: d.detail })
    else notify.warn(`${d.label}：${h.label}`, { detail: d.detail, hint: d.hint })
  } catch { /* toast */ } finally { testing.value = false }
}

/** 白名单只是「订阅名单」，勾完不会自动拉数据：这里手动跑一次采集任务。 */
async function collect(): Promise<void> {
  collecting.value = true
  try {
    const r = await api.createRun({ platforms: [props.platform], window_hours: 24, dry_run: true })
    live.run = r
    live.sessionRun = true
    notify.ok(`已开始采集${PLATFORM[props.platform].label}`, { detail: '后台运行，跑完这里会自动刷新' })
    void waitCollect(r.id)
  } catch {
    collecting.value = false
  }
}
async function waitCollect(id: string): Promise<void> {
  try {
    for (let i = 0; i < 200; i++) {
      await new Promise((r) => setTimeout(r, 3000))
      const r = await api.run(id, { silent: true }).catch(() => null)
      if (!r || r.status === 'queued' || r.status === 'running') continue
      const all = await api.platforms().catch(() => null)
      const mine = all?.find((x) => x.platform === props.platform)
      if (mine) emit('updated', mine)
      refreshOverview()
      if (r.status === 'success') {
        notify.ok('采集完成', { detail: `近 24 小时 ${fmtInt(mine?.messages_24h ?? 0)} 条消息已入库` })
      } else {
        notify.warn('采集结束但没有成功', { detail: r.error || '到「调度中心」看这次运行的日志' })
      }
      return
    }
    notify.warn('采集还在跑', { detail: '到「调度中心」可以看进度和日志' })
  } finally {
    collecting.value = false
  }
}
</script>

<template>
  <HudPanel lite :title="`${PLATFORM[platform].label}采集`" code="COLLECTOR" :accent="PLATFORM[platform].color">
    <template #actions>
      <HudSwitch v-if="dto" :model-value="dto.enabled" label="启用" @update:model-value="setEnabled" />
    </template>
    <div v-if="dto" class="pc">
      <div class="status" :class="`h-${health}`">
        <PlatformIcon :platform="platform" :size="44" />
        <div class="st">
          <div class="l1"><i class="dot fx-loop" :class="{ 'lamp-ok': health === 'ok', 'lamp-down': health === 'down' }" /><b>{{ HEALTH[health].label }}</b><span class="dim num">检查于 {{ fmtAgo(dto.checked_at) }}</span></div>
          <div class="dt">{{ dto.detail }}</div>
        </div>
        <div class="acts">
          <button class="btn" :disabled="testing" @click="test"><Icon name="pulse" />{{ testing ? '检测中…' : '测试连接' }}</button>
          <button class="btn primary" :disabled="collecting || !dto.enabled" :title="dto.enabled ? '按当前白名单拉最近 24 小时的消息' : '先启用这个平台的采集'" @click="collect">
            <Icon name="play" />{{ collecting ? '采集中…' : '立即采集' }}
          </button>
        </div>
      </div>
      <div v-if="dto.hint" class="callout warn"><b>修复建议：</b>{{ dto.hint }}</div>
      <div class="stat-line">
        <span>群<b>{{ dto.groups_whitelisted }} / {{ dto.groups_total }}</b></span>
        <span>24h 消息<b>{{ fmtInt(dto.messages_24h) }}</b></span>
        <span>最近采集<b>{{ fmtAgo(dto.last_collect_at) }}</b></span>
      </div>
      <div class="hint-line">
        白名单只是订阅名单，勾完不会自动拉消息：点上面的「立即采集」跑一次，或等定时任务（默认每天 8:00）自动跑。
      </div>
      <hr class="divider" />
      <div class="field">
        <span class="lbl">采集适配器</span>
        <div class="adapters">
          <label v-for="a in dto.adapters" :key="a.key" class="ad" :class="{ on: adapter === a.key, off: a.available === false }">
            <input v-model="adapter" type="radio" :value="a.key" :name="`ad-${platform}`" :disabled="a.available === false" />
            <span class="nm">{{ a.label }}</span><span class="k num">{{ a.key }}</span>
            <span v-if="a.available === false" class="badge">未安装</span>
            <span v-else-if="dto.adapter === a.key" class="badge cyan">当前</span>
          </label>
        </div>
      </div>
      <SchemaForm ref="form" v-model="values" :fields="schema" :masks="masks" />
      <div class="row foot">
        <span v-if="dirty" class="dim">有未保存的修改</span>
        <span class="spacer" />
        <button class="btn primary" :disabled="saving || !dirty" @click="save"><Icon name="check" />{{ saving ? '保存中…' : '保存配置' }}</button>
      </div>
    </div>
    <div v-else class="empty"><span class="code">LOADING</span>正在读取平台状态…</div>
  </HudPanel>
</template>

<style scoped>
.pc { display: flex; flex-direction: column; gap: 14px; padding: 6px 4px 4px; }
.status { display: flex; align-items: center; gap: 14px; padding: 12px 14px; border: 1px solid var(--line); background: rgba(4, 12, 28, 0.5); }
.st { flex: 1; min-width: 0; }
.acts { display: flex; gap: 8px; flex-shrink: 0; }
.hint-line { font-size: 12px; color: var(--text-2); line-height: 1.6; padding: 0 2px; }
.l1 { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.l1 b { color: currentColor; }
.dt { margin-top: 4px; font-size: 12.5px; color: var(--text-1); line-height: 1.6; }
.adapters { display: flex; flex-direction: column; gap: 6px; }
.ad { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: 1px solid var(--line); border-radius: 3px; cursor: pointer; font-size: 13px; }
.ad.on { border-color: var(--line-strong); background: rgba(34, 228, 255, 0.05); }
.ad.off { opacity: 0.45; cursor: not-allowed; }
.ad input { accent-color: var(--cyan); }
.ad .nm { color: var(--text-0); }
.ad .k { font-size: 11px; color: var(--text-2); margin-left: auto; }
.foot { margin-top: 2px; }
</style>
