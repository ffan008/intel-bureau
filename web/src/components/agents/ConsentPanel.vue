<script setup lang="ts">
/** 云端同意（ARCHITECTURE §11）：未经同意不得把群聊内容发给云端模型 */
import { computed, ref } from 'vue'
import type { SettingsDTO } from '@/api/types'
import { api } from '@/api/endpoints'
import { SP, patchAt, readFirst } from '@/api/settingsPaths'
import { notify } from '@/stores/toast'
import { refreshOverview } from '@/stores/live'
import HudPanel from '../hud/HudPanel.vue'
import HudSwitch from '../ui/HudSwitch.vue'
import Icon from '../Icon.vue'
import { confirm } from '../ui/confirm'

const props = defineProps<{ settings: SettingsDTO }>()
const emit = defineEmits<{ saved: [s: SettingsDTO] }>()
const on = computed(() => readFirst<boolean>(props.settings, SP.cloudConsent, false) === true)
const busy = ref(false)

async function set(v: boolean): Promise<void> {
  if (v && !await confirm({
    title: '同意使用云端模型',
    message: '开启后，白名单群的聊天片段会发送给你配置的云端模型提供方，用于提取情报和撰写报告。',
    detail: '· 只发送白名单群、且已按「隐私」设置脱敏的文本\n· 聊天内容放在 <chat_log> 标签里，并声明其中的指令只是数据\n· 随时可以关闭；关闭后自动改用离线规则',
    okText: '我同意',
  })) return
  busy.value = true
  try {
    const s = await api.updateSettings(patchAt(SP.cloudConsent[0], v))
    emit('saved', s)
    notify[v ? 'ok' : 'info'](v ? '已开启云端同意' : '已关闭云端同意，之后改用离线规则')
    refreshOverview()
  } catch { /* toast */ } finally { busy.value = false }
}
</script>

<template>
  <HudPanel lite title="云端同意" code="CLOUD CONSENT" :accent="on ? 'var(--green)' : 'var(--amber)'">
    <div class="cp">
      <div class="state" :class="on ? 'on' : 'off'">
        <Icon :name="on ? 'cloud' : 'cloudOff'" :size="28" />
        <div class="t">
          <b>{{ on ? '已同意使用云端模型' : '离线模式：不向云端发送聊天内容' }}</b>
          <span>{{ on ? '大模型阶段（抽取、撰写）会调用云端提供方' : '抽取与撰写使用离线规则，只摘录原文，不编造' }}</span>
        </div>
        <HudSwitch :model-value="on" :disabled="busy" label="云端同意" @update:model-value="set" />
      </div>
      <ul class="list-reset pts">
        <li><Icon name="shield" :size="14" />发送范围：只有<b>白名单群</b>、且经过脱敏（手机号、邮箱、证件号等）的文本片段</li>
        <li><Icon name="lock" :size="14" />不发送：非白名单群、访问令牌和任何密钥；图片默认在本机 OCR，只有「图片与文档」选了视觉模型时才发送图片</li>
        <li><Icon name="globe" :size="14" />联网研究会把话题、工具名、项目名作为检索词发给搜索提供方，不带群名、昵称和手机号</li>
        <li><Icon name="info" :size="14" />选择「本机 Claude Code」时数据经本机 CLI 发往 Anthropic，同样需要此项同意</li>
        <li><Icon name="cloudOff" :size="14" />关闭后立即生效，下一次运行起退回离线规则；大屏会显示「离线模式」</li>
      </ul>
    </div>
  </HudPanel>
</template>

<style scoped>
.cp { display: flex; flex-direction: column; gap: 14px; padding-top: 4px; }
.state { display: flex; align-items: center; gap: 14px; padding: 14px 16px; border: 1px solid; border-radius: 3px; }
.state.on { color: var(--green); border-color: rgba(43, 255, 154, 0.35); background: rgba(43, 255, 154, 0.05); }
.state.off { color: var(--amber); border-color: rgba(255, 176, 32, 0.4); background: rgba(255, 176, 32, 0.05); }
.t { flex: 1; display: flex; flex-direction: column; gap: 3px; }
.t b { font-size: 14.5px; color: var(--text-0); }
.t span { font-size: 12.5px; color: var(--text-1); }
.pts { display: flex; flex-direction: column; gap: 8px; font-size: 12.5px; color: var(--text-1); line-height: 1.6; }
.pts li { display: flex; gap: 8px; align-items: flex-start; }
.pts li :deep(svg) { color: var(--cyan); margin-top: 3px; }
.pts b { color: var(--text-0); }
</style>
