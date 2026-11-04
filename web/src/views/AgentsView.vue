<script setup lang="ts">
/** 智能体（UI_DESIGN §5 /agents）：提供方、云端同意、并发预算、联网研究、图片与文档、兴趣画像（含风险策略）、提示词；附 Agent 与阶段映射 */
import { onMounted, ref } from 'vue'
import type { SettingsDTO, StageName } from '@/api/types'
import { api } from '@/api/endpoints'
import { live, agentViews } from '@/stores/live'
import { AGENTS, STAGE_LABEL, STAGE_STATUS } from '@/utils/meta'
import HudPanel from '@/components/hud/HudPanel.vue'
import LlmPanel from '@/components/agents/LlmPanel.vue'
import ConsentPanel from '@/components/agents/ConsentPanel.vue'
import InterestPanel from '@/components/agents/InterestPanel.vue'
import PromptEditor from '@/components/agents/PromptEditor.vue'
import ResearchPanel from '@/components/agents/ResearchPanel.vue'
import MediaPanel from '@/components/agents/MediaPanel.vue'

const settings = ref<SettingsDTO | null>(null)
onMounted(async () => { try { settings.value = await api.settings(); live.settings = settings.value } catch { /* toast */ } })
function onSaved(s: SettingsDTO): void { settings.value = s; live.settings = s }
const stageText = (xs: StageName[]) => xs.map((x) => STAGE_LABEL[x]).join(' + ')
</script>

<template>
  <div class="page">
    <template v-if="settings">
      <div class="two">
        <LlmPanel :settings="settings" @saved="onSaved" />
        <div class="col">
          <ConsentPanel :settings="settings" @saved="onSaved" />
          <HudPanel lite title="编队与阶段" code="AGENT · STAGE MAP">
            <ul class="map list-reset">
              <li v-for="(a, i) in AGENTS" :key="a.code">
                <span class="n num">{{ String(i + 1).padStart(2, '0') }}</span>
                <b class="disp">{{ a.code }}</b><span class="nm">{{ a.name }}</span>
                <span class="st">{{ stageText(a.stages) }}</span>
                <span class="badge" :class="STAGE_STATUS[agentViews[i]?.status ?? 'pending'].cls">{{ STAGE_STATUS[agentViews[i]?.status ?? 'pending'].label }}</span>
              </li>
            </ul>
          </HudPanel>
        </div>
      </div>
      <div class="two">
        <ResearchPanel :settings="settings" @saved="onSaved" />
        <MediaPanel :settings="settings" @saved="onSaved" />
      </div>
      <div class="two">
        <InterestPanel :settings="settings" @saved="onSaved" />
        <PromptEditor />
      </div>
    </template>
    <div v-else class="empty"><span class="code">LOADING</span>正在读取设置…</div>
  </div>
</template>

<style scoped>
.two { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 18px; align-items: start; }
.col { display: flex; flex-direction: column; gap: 18px; }
.map li { display: grid; grid-template-columns: 24px 110px 60px 1fr auto; align-items: center; gap: 8px; padding: 7px 0; border-bottom: 1px solid rgba(80, 200, 255, 0.07); font-size: 13px; }
.n { color: var(--text-2); font-size: 11px; }
.map b { font-size: 11px; letter-spacing: 1.5px; color: var(--cyan); }
.nm { color: var(--text-0); }
.st { color: var(--text-2); font-size: 12px; }
</style>
