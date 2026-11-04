<script setup lang="ts">
/** 系统（UI_DESIGN §5 /system）：体检、日志、隐私、演示数据、特效强度 */
import { computed, onMounted, ref } from 'vue'
import type { SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { SP, patchAt } from '@/api/settingsPaths'
import { app } from '@/stores/app'
import { fx, FX_LEVELS, setFxLevel, type FxLevel } from '@/stores/fx'
import { live, refreshOverview } from '@/stores/live'
import { notify } from '@/stores/toast'
import HudPanel from '@/components/hud/HudPanel.vue'
import DoctorPanel from '@/components/system/DoctorPanel.vue'
import LogPanel from '@/components/system/LogPanel.vue'
import PrivacyPanel from '@/components/system/PrivacyPanel.vue'
import Icon from '@/components/Icon.vue'
import { confirm } from '@/components/ui/confirm'

const settings = ref<SettingsDTO | null>(null)
const seeding = ref(false)
const lastSeed = ref<string>('')
onMounted(async () => { try { settings.value = await api.settings(); live.settings = settings.value } catch { /* toast */ } })
function onSaved(s: SettingsDTO): void { settings.value = s; live.settings = s }
const fxLabel = computed(() => FX_LEVELS.find((o) => o.key === fx.level)?.label ?? '')

async function pickFx(v: FxLevel): Promise<void> {
  setFxLevel(v)
  // 偏好以本机 localStorage 为准；同时尽量写回 settings.app.effects，失败不提示
  try { onSaved(await api.updateSettings(patchAt(SP.effects[0], v), { silent: true })) } catch { /* 后端不认这个字段也没关系 */ }
}
async function seed(reset: boolean): Promise<void> {
  if (reset && !await confirm({ title: '重置演示数据', message: '会先清除已有的演示群、消息和报告，再重新写入。', detail: '真实平台的数据不受影响。', okText: '重置并写入', danger: true })) return
  seeding.value = true
  try {
    const r = await api.demoSeed(reset)
    lastSeed.value = `已写入 ${r.groups} 个演示群、${r.messages.toLocaleString('en-US')} 条消息`
    notify.ok('演示数据已写入', { detail: lastSeed.value + '。现在可以到大屏点「立即出报」。' })
    refreshOverview()
  } catch { /* toast */ } finally { seeding.value = false }
}
async function clear(): Promise<void> {
  if (!await confirm({ title: '清除演示数据', message: '删除所有演示群及其消息、报告。', detail: '此操作不可撤销；真实平台的数据不受影响。', okText: '清除', danger: true })) return
  try { await api.demoClear(); lastSeed.value = '演示数据已清除'; notify.ok('演示数据已清除'); refreshOverview() } catch { /* toast */ }
}
</script>

<template>
  <div class="page">
    <div class="two">
      <DoctorPanel />
      <div class="col">
        <HudPanel lite title="特效强度" code="EFFECTS">
          <div class="fx">
            <div class="opts">
              <button v-for="o in FX_LEVELS" :key="o.key" class="op" :class="{ on: fx.chosen === o.key }" :aria-pressed="fx.chosen === o.key" @click="pickFx(o.key)">
                <b>{{ o.label }}</b><span>{{ o.desc }}</span>
              </button>
            </div>
            <div v-if="fx.reducedMotion" class="callout warn">系统开启了「减少动态效果」（prefers-reduced-motion），当前按「关」处理。</div>
            <p class="hint-box">偏好保存在本机浏览器。当前生效：<b class="c-cyan">{{ fxLabel }}</b> · 粒子 <b class="num">{{ fx.particles }}</b> 颗</p>
          </div>
        </HudPanel>
        <HudPanel lite title="演示数据" code="DEMO DATA" accent="var(--demo)">
          <div class="demo">
            <p class="hint-box">写入 9 个演示群（微信 4、QQ 3、飞书 2）× 7 天合成消息，含噪声、跨群转发和一个上升话题，固定随机种子。没有任何外部服务时也能完整跑通出报流程。</p>
            <div v-if="app.mock" class="callout">当前页面本身就在使用前端演示数据（MOCK）：{{ app.mockReason }}</div>
            <div class="row wrap">
              <button class="btn primary" :disabled="seeding" @click="seed(false)"><Icon name="database" />{{ seeding ? '写入中…' : '写入演示数据' }}</button>
              <button class="btn" :disabled="seeding" @click="seed(true)"><Icon name="refresh" />重置并写入</button>
              <button class="btn danger" @click="clear"><Icon name="trash" />清除演示数据</button>
            </div>
            <div v-if="lastSeed" class="dim">{{ lastSeed }}</div>
          </div>
        </HudPanel>
      </div>
    </div>
    <div class="two">
      <PrivacyPanel v-if="settings" :settings="settings" @saved="onSaved" />
      <LogPanel />
    </div>
  </div>
</template>

<style scoped>
.two { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; align-items: start; }
.col { display: flex; flex-direction: column; gap: 18px; }
.fx, .demo { display: flex; flex-direction: column; gap: 12px; padding-top: 4px; }
.opts { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; }
.op { display: flex; flex-direction: column; gap: 4px; padding: 12px; text-align: left; border: 1px solid var(--line); border-radius: 3px; }
.op b { font-size: 18px; color: var(--text-0); }
.op span { font-size: 11.5px; color: var(--text-2); line-height: 1.5; }
.op.on { border-color: var(--cyan); background: rgba(34, 228, 255, 0.08); box-shadow: inset 0 0 0 1px rgba(34, 228, 255, 0.2), 0 0 14px rgba(34, 228, 255, 0.12); }
.op.on b { color: var(--cyan); }
.hint-box { margin: 0; }
.hint-box b { font-weight: 600; }
</style>
