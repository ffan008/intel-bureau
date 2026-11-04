<script setup lang="ts">
/** 新增 / 编辑通道：类型卡片选择 → 按 config_schema 生成表单 */
import { computed, ref, watch } from 'vue'
import type { ChannelDTO, ChannelKindDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { notify } from '@/stores/toast'
import { channelColor } from '@/utils/meta'
import Modal from '../ui/Modal.vue'
import SchemaForm from '../ui/SchemaForm.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import Icon from '../Icon.vue'
import { initForm, serializeForm } from '../ui/schemaForm'

const props = defineProps<{ open: boolean; kinds: ChannelKindDTO[]; editing: ChannelDTO | null }>()
const emit = defineEmits<{ close: []; saved: [c: ChannelDTO] }>()
const step = ref<1 | 2>(1)
const kind = ref<ChannelKindDTO | null>(null)
const name = ref('')
const enabled = ref(true)
const values = ref<Record<string, unknown>>({})
const masks = ref<Record<string, string>>({})
const form = ref<InstanceType<typeof SchemaForm> | null>(null)
const busy = ref(false)

const groups = computed(() => {
  const m = new Map<string, ChannelKindDTO[]>()
  for (const k of props.kinds) m.set(k.platform_label, [...(m.get(k.platform_label) ?? []), k])
  return [...m.entries()]
})

watch(() => props.open, (v) => {
  if (!v) return
  if (props.editing) {
    kind.value = props.kinds.find((k) => k.kind === props.editing!.kind) ?? null
    name.value = props.editing.name
    enabled.value = props.editing.enabled
    const f = initForm(kind.value?.config_schema ?? [], props.editing.config)
    values.value = f.values; masks.value = f.masks
    step.value = 2
  } else { kind.value = null; step.value = 1; name.value = ''; enabled.value = true }
})
function choose(k: ChannelKindDTO): void {
  kind.value = k
  name.value = name.value || `${k.platform_label} · ${k.label.replace(/（.*?）/, '')}`
  const f = initForm(k.config_schema, {})
  values.value = f.values; masks.value = f.masks
  step.value = 2
}
async function save(): Promise<void> {
  if (!kind.value || !form.value?.validate()) return
  if (!name.value.trim()) { notify.warn('请填写通道名称'); return }
  busy.value = true
  try {
    const body = { kind: kind.value.kind, name: name.value.trim(), enabled: enabled.value, config: serializeForm(kind.value.config_schema, values.value) }
    const c = props.editing ? await api.updateChannel(props.editing.id, body) : await api.createChannel(body)
    notify.ok(props.editing ? '通道已更新' : '通道已添加', { detail: '可以点「发送测试」确认是否能收到' })
    emit('saved', c)
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <Modal :open="open" :title="editing ? `编辑通道 · ${editing.name}` : step === 1 ? '新增推送通道 · 选择类型' : '新增推送通道 · 填写配置'" code="CHANNEL" :width="step === 1 ? 760 : 620" @close="emit('close')">
    <div v-if="step === 1" class="kinds">
      <section v-for="[plat, ks] in groups" :key="plat">
        <h4 class="sec-title">{{ plat }}</h4>
        <div class="kgrid">
          <button v-for="k in ks" :key="k.kind" class="kc" :class="{ off: k.available === false }" :disabled="k.available === false" :style="{ '--c': channelColor(k.kind, k.platform_label) }" @click="choose(k)">
            <i /><b>{{ k.label }}</b><span class="num">{{ k.kind }}</span><em>{{ k.available === false ? '未安装' : k.config_schema.filter((f) => f.required).length + ' 个必填项' }}</em>
          </button>
        </div>
      </section>
    </div>
    <div v-else-if="kind" class="cfg">
      <div class="kh" :style="{ '--c': channelColor(kind.kind, kind.platform_label) }">
        <i /><b>{{ kind.label }}</b><span class="num dim">{{ kind.kind }}</span>
        <button v-if="!editing" class="btn sm ghost" @click="step = 1"><Icon name="chevronLeft" />换类型</button>
      </div>
      <div class="grid-2">
        <div class="field"><span class="lbl">通道名称<span class="req">*</span></span><input v-model="name" class="input" maxlength="40" /></div>
        <div class="field"><span class="lbl">状态</span><HudSwitch v-model="enabled" label="启用" /></div>
      </div>
      <hr class="divider" />
      <SchemaForm ref="form" v-model="values" :fields="kind.config_schema" :masks="masks" />
      <p class="hint-box">密钥类字段只保存在本机 <code>config/secrets.yaml</code>，界面上只显示末 4 位；编辑时留空表示不修改。</p>
    </div>
    <template v-if="step === 2" #foot>
      <button class="btn" @click="emit('close')">取消</button>
      <button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.kinds { display: flex; flex-direction: column; gap: 16px; }
.kinds .sec-title { margin-bottom: 8px; font-size: 13px; color: var(--text-1); }
.kc.off { opacity: 0.45; cursor: not-allowed; }
.kgrid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
.kc { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 4px; padding: 12px 14px 12px 18px; text-align: left; border: 1px solid var(--line); background: rgba(4, 12, 28, 0.55); border-radius: 3px; }
.kc:hover { border-color: color-mix(in srgb, var(--c) 70%, transparent); background: color-mix(in srgb, var(--c) 8%, rgba(4, 12, 28, 0.55)); }
.kc i { position: absolute; left: 0; top: 10px; bottom: 10px; width: 3px; background: var(--c); box-shadow: 0 0 8px var(--c); }
.kc b { font-size: 13.5px; color: var(--text-0); }
.kc span { font-size: 11px; color: var(--text-2); }
.kc em { font-style: normal; font-size: 11px; color: var(--text-2); }
.cfg { display: flex; flex-direction: column; gap: 14px; }
.kh { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border: 1px solid var(--line); background: rgba(4, 12, 28, 0.5); }
.kh i { width: 8px; height: 8px; border-radius: 50%; background: var(--c); box-shadow: 0 0 8px var(--c); }
.kh .btn { margin-left: auto; }
.hint-box { margin: 0; }
</style>
