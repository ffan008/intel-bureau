<script setup lang="ts">
/** 兴趣画像：兴趣词、屏蔽词、分类权重、风险策略 */
import { ref, watch } from 'vue'
import type { SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { SP, mergePatch, patchAt, readFirst, readRiskPolicy, type RiskPolicy } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import { categoryColor } from '@/utils/meta'
import HudPanel from '../hud/HudPanel.vue'
import TagInput from '../ui/TagInput.vue'
import SegPicker from '../ui/SegPicker.vue'
import Icon from '../Icon.vue'

const CATS: [string, string][] = [['01', '工具与资源'], ['02', '提示词与工作流'], ['03', 'AI 创作实战'], ['04', '流量与变现'], ['05', '编程与自动化'],
  ['06', '模型与平台动态'], ['07', '需求与机会'], ['08', '风险与避坑'], ['99', '其他']]
/** 后端按完整分类名取权重（与 config/taxonomy.yaml 一致），如 "01 工具与资源" */
const catLabel = (code: string, name: string) => `${code} ${name}`
const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
const keywords = ref<string[]>([])
const blocks = ref<string[]>([])
const weights = ref<Record<string, number>>({})
const risk = ref<RiskPolicy>('label')
const busy = ref(false)
const RISK_OPTS: { value: RiskPolicy; label: string }[] = [
  { value: 'label', label: '只标注（默认）' }, { value: 'flag', label: '标注 + 降权' }, { value: 'drop', label: '直接剔除' },
]
const RISK_DESC: Record<RiskPolicy, string[]> = {
  label: [
    '风险内容照常提取、照常联网扩展，可以进头条和专题，不扣分；只加风险标注，文末附固定免责声明。',
    '隐私类（主要是某个普通人的手机号、住址、证件号）剔除，或只保留脱敏后的要点。',
    '违法高危（诈骗、伪造证件、盗号与买卖账号、洗钱、赌博、色情传播、涉及未成年人）只记录和总结，放进「风险」板块，不做联网扩展、不写成教程。',
  ],
  flag: ['v1 的旧行为：带风险标签的情报按标签扣分，并且不进头条。'],
  drop: ['带风险标签的情报直接剔除，报告里看不到。'],
}

watch(() => props.settings, (s) => {
  keywords.value = [...readFirst<string[]>(s, SP.keywords, [])]
  blocks.value = [...readFirst<string[]>(s, SP.blockWords, [])]
  const w = readFirst<Record<string, number>>(s, SP.categoryWeights, {})
  weights.value = Object.fromEntries(CATS.map(([k, n]) => [k, Number(w[catLabel(k, n)] ?? w[k] ?? 1)]))
  risk.value = readRiskPolicy(s)
}, { immediate: true })

async function save(): Promise<void> {
  busy.value = true
  try {
    const s = await api.updateSettings(mergePatch(patchAt(SP.keywords[0], keywords.value), patchAt(SP.blockWords[0], blocks.value),
      patchAt(SP.categoryWeights[0], Object.fromEntries(CATS.map(([k, n]) => [catLabel(k, n), weights.value[k] ?? 1]))),
      patchAt(SP.riskPolicy[0], risk.value)))
    emit('saved', s)
    notify.ok('兴趣画像已保存', { detail: '下一次运行开始生效' })
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="兴趣画像" code="INTEREST PROFILE">
    <div class="ip">
      <div class="field"><span class="lbl">兴趣词 <span class="dim">命中越多，「相关」分越高</span></span><TagInput v-model="keywords" placeholder="输入兴趣词后回车，如 AI 绘画" /></div>
      <div class="field"><span class="lbl">屏蔽词 <span class="dim">命中直接剔除</span></span><TagInput v-model="blocks" color="#ff4d5e" placeholder="输入屏蔽词后回车" /></div>
      <div class="field">
        <span class="lbl">风险内容处理</span>
        <SegPicker v-model="risk" :options="RISK_OPTS" />
        <ul class="list-reset rdesc"><li v-for="(t, i) in RISK_DESC[risk]" :key="i">{{ t }}</li></ul>
        <span class="help">风险标签：合规风险、平台规则、账号风险、金钱风险、广告引流、版权风险、未核实、违法高危</span>
      </div>
      <div class="field">
        <span class="lbl">分类权重</span>
        <div class="ws">
          <div v-for="[k, n] in CATS" :key="k" class="w" :style="{ '--c': categoryColor(k) }">
            <span class="nm"><i />{{ k }} {{ n }}</span>
            <input v-model.number="weights[k]" class="range" type="range" min="0" max="2" step="0.1" :style="{ '--pct': ((weights[k] ?? 1) / 2) * 100 + '%' }" :aria-label="`${n} 权重`" />
            <b class="num">{{ (weights[k] ?? 1).toFixed(1) }}</b>
          </div>
        </div>
      </div>
      <div class="row"><span class="spacer" /><button class="btn primary" :disabled="busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存画像' }}</button></div>
    </div>
  </HudPanel>
</template>

<style scoped>
.ip { display: flex; flex-direction: column; gap: 16px; padding-top: 4px; }
.ws { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px 22px; }
.w { display: grid; grid-template-columns: 130px 1fr 30px; align-items: center; gap: 10px; }
.nm { font-size: 12.5px; color: var(--text-1); display: flex; align-items: center; gap: 6px; white-space: nowrap; }
.nm i { width: 7px; height: 7px; background: var(--c); box-shadow: 0 0 6px var(--c); }
.w b { font-size: 12px; color: var(--cyan); text-align: right; }
.rdesc { display: flex; flex-direction: column; gap: 4px; padding: 8px 12px; font-size: 12.5px; line-height: 1.7; color: var(--text-1); border-left: 2px solid var(--line-strong); background: rgba(34, 228, 255, 0.03); }
.rdesc li { position: relative; padding-left: 12px; }
.rdesc li::before { content: ''; position: absolute; left: 0; top: 9px; width: 4px; height: 4px; background: var(--cyan-dim); }
</style>
