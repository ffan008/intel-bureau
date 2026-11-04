<script setup lang="ts">
/** 隐私：脱敏开关（实时预览）、实时上报预览、原始消息保留天数 */
import { computed, ref, watch } from 'vue'
import type { SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { SP, mergePatch, patchAt, readFirst } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import { REDACT_KINDS, redact, type RedactKind } from '@/utils/redact'
import HudPanel from '../hud/HudPanel.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import Icon from '../Icon.vue'

const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
/** 前端的规则名 → 后端 privacy.desensitize 里的种类名 */
const KIND: Record<RedactKind, string> = { phone: 'phone', email: 'email', id_card: 'idcard', bank_card: 'bankcard', wechat_id: 'wechat_id' }
const rules = ref<Record<RedactKind, boolean>>({ phone: true, email: true, id_card: true, bank_card: true, wechat_id: true })
const days = ref(30)
const livePreview = ref(false)
const busy = ref(false)
const sample = ref('有需要的加我微信：wxid_ab12cd34ef，或者打 13812345678。\n资料发我邮箱 zhang.san@example.com 就行。\n退款请提供身份证 110105199003071234 和卡号 6222 0212 3456 7890 123。')

watch(() => props.settings, (s) => {
  const kinds = readFirst<string[] | null>(s, SP.desensitize, null)
  rules.value = Object.fromEntries(REDACT_KINDS.map((k) => [k.key, kinds ? kinds.includes(KIND[k.key]) : true])) as Record<RedactKind, boolean>
  days.value = Number(readFirst(s, SP.retentionDays, 30))
  livePreview.value = readFirst<boolean>(s, SP.livePreview, false) === true
}, { immediate: true })

const preview = computed(() => redact(sample.value, rules.value))
async function save(): Promise<void> {
  if (!Number.isFinite(days.value) || days.value < 1) { notify.warn('保留天数至少为 1 天'); return }
  busy.value = true
  try {
    const kinds = REDACT_KINDS.filter((k) => rules.value[k.key]).map((k) => KIND[k.key])
    const s = await api.updateSettings(mergePatch(patchAt(SP.desensitize[0], kinds), patchAt(SP.retentionDays[0], Math.round(days.value)), patchAt(SP.livePreview[0], livePreview.value)))
    emit('saved', s)
    notify.ok('隐私设置已保存')
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="隐私" code="PRIVACY">
    <div class="pv">
      <div class="field">
        <span class="lbl">清洗时脱敏</span>
        <div class="rules">
          <HudSwitch v-for="k in REDACT_KINDS" :key="k.key" v-model="rules[k.key]">{{ k.label }}</HudSwitch>
        </div>
      </div>
      <div class="field">
        <span class="lbl">实时预览 <span class="dim">（只在本页演示规则，真正的脱敏在后端清洗阶段执行）</span></span>
        <div class="prev">
          <textarea v-model="sample" class="textarea" rows="4" aria-label="脱敏示例文本" />
          <div class="out">
            <div class="oh"><Icon name="eye" :size="13" />脱敏后 · 命中 <b class="num">{{ preview.hits }}</b> 处</div>
            <!-- redact() 先转义再包 <mark>，只含受控标签 -->
            <div class="ot" v-html="preview.html" />
          </div>
        </div>
      </div>
      <div class="grid-2">
        <div class="field">
          <span class="lbl">原始消息保留天数</span>
          <div class="row"><input v-model.number="days" class="input num" type="number" min="1" max="3650" style="width: 110px" /><span class="dim">天，归档阶段自动清理</span></div>
        </div>
        <div class="field">
          <span class="lbl">实时上报预览</span>
          <HudSwitch v-model="livePreview">大屏显示发言人和前 30 字</HudSwitch>
          <span class="help">关闭时 SSE 只推送「哪个群来了几条」</span>
        </div>
      </div>
      <div class="row"><span class="spacer" /><button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button></div>
    </div>
  </HudPanel>
</template>

<style scoped>
.pv { display: flex; flex-direction: column; gap: 16px; padding-top: 4px; }
.rules { display: flex; flex-wrap: wrap; gap: 10px 20px; }
.prev { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
.out { border: 1px solid var(--line); background: rgba(0, 3, 9, 0.6); padding: 8px 10px; min-width: 0; }
.oh { display: flex; align-items: center; gap: 6px; font-size: 11.5px; color: var(--text-2); margin-bottom: 4px; }
.oh b { color: var(--cyan); }
.ot { font-size: 13px; line-height: 1.6; white-space: pre-wrap; word-break: break-all; color: var(--text-1); }
.ot :deep(mark) { background: rgba(255, 176, 32, 0.16); color: var(--amber); padding: 0 2px; border-radius: 2px; font-family: var(--font-num); font-size: 12.5px; }
</style>
