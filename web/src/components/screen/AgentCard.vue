<script setup lang="ts">
/** Agent 卡片（§4.5）：六边形头像、代号、中文名、状态、当前任务（打字机）、一个指标 */
import { computed, ref, watch } from 'vue'
import type { AgentCode } from '@/api/types'
import type { AgentView } from '@/utils/agents'
import { STAGE_STATUS } from '@/utils/meta'
import { useTypewriter } from '@/composables/useTextFx'
import Icon from '../Icon.vue'
import type { IconName } from '../icons'
import HudComet from '../hud/HudComet.vue'

const ICON: Record<AgentCode, IconName> = {
  SCOUT: 'radar', SWEEPER: 'broom', ANALYST: 'chart', DECODER: 'decode', STRATEGIST: 'target', AUDITOR: 'audit', WRITER: 'pen', COURIER: 'plane',
}
const props = defineProps<{ agent: AgentView; step: number }>()
const task = useTypewriter(() => props.agent.task, 18)
const st = computed(() => STAGE_STATUS[props.agent.status])

// 完成闪一次绿、失败闪两次红
const flashKey = ref(0)
watch(() => props.agent.status, (now, prev) => { if (prev && now !== prev && (now === 'done' || now === 'failed')) flashKey.value++ })
</script>

<template>
  <div class="ac" :class="agent.status">
    <HudComet v-if="agent.status === 'running'" :period="2400" :length="56" color="var(--cyan)" />
    <span v-if="flashKey" :key="flashKey" class="flash" aria-hidden="true" />
    <div class="left">
      <div class="ava">
        <span v-if="agent.status === 'running'" class="pulse fx-loop" aria-hidden="true" />
        <svg viewBox="0 0 44 44" aria-hidden="true">
          <path d="M22 2.5 39 12.25v19.5L22 41.5 5 31.75v-19.5z" class="hex" />
          <path d="M22 7 34.5 14.2v15.6L22 37 9.5 29.8V14.2z" class="hex2" />
        </svg>
        <Icon :name="ICON[agent.code]" :size="15" class="ic" />
      </div>
      <span class="st" :class="st.cls"><template v-if="agent.status === 'done'">✓</template><template v-else-if="agent.status === 'failed'">⚠</template>{{ st.label }}</span>
    </div>
    <div class="body">
      <div class="h">
        <span class="code disp">{{ agent.code }}</span>
        <span class="nm">{{ agent.name }}</span>
      </div>
      <div class="task" :title="agent.task">{{ task }}<i v-if="agent.status === 'running'" class="caret fx-loop">▍</i></div>
      <div class="metric num">{{ agent.metric }}</div>
    </div>
    <span class="step num" aria-hidden="true">{{ String(step).padStart(2, '0') }}</span>
  </div>
</template>

<style scoped>
.ac {
  --ac: var(--text-2);
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 0 8px 0 6px;
  background: rgba(6, 16, 36, 0.66);
  border: 1px solid rgba(80, 200, 255, 0.12);
  transition: transform 0.4s var(--ease-out-expo);
}
.ac.running { --ac: var(--cyan); background: linear-gradient(120deg, rgba(34, 228, 255, 0.12), rgba(6, 16, 36, 0.7) 70%); border-color: rgba(34, 228, 255, 0.45); transform: translateY(-2px); box-shadow: 0 6px 18px rgba(34, 228, 255, 0.14); }
.ac.done { --ac: var(--green); }
.ac.failed { --ac: var(--red); border-color: rgba(255, 77, 94, 0.5); }
.ac.skipped { opacity: 0.55; }
.left { flex: none; width: 40px; display: flex; flex-direction: column; align-items: center; gap: 1px; }
.ava { position: relative; width: 36px; height: 36px; flex: none; display: flex; align-items: center; justify-content: center; color: var(--ac); }
.ava svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.hex { fill: color-mix(in srgb, var(--ac) 10%, transparent); stroke: var(--ac); stroke-width: 1.3; }
.hex2 { fill: none; stroke: var(--ac); stroke-opacity: 0.35; stroke-width: 0.8; stroke-dasharray: 2 2.5; }
.pending .ava, .skipped .ava { opacity: 0.6; }
.ic { position: relative; filter: drop-shadow(0 0 4px var(--ac)); }
.pulse { position: absolute; inset: -4px; border-radius: 50%; border: 1px solid var(--cyan); animation: kf-pulse-ring 1.6s ease-out infinite; }
.body { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.h { display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.code { font-size: 10.5px; letter-spacing: 1.2px; color: var(--ac); font-weight: 700; }
.pending .code { color: var(--text-1); }
.nm { font-size: 12px; color: var(--text-0); }
.st { font-size: 10px; line-height: 13px; white-space: nowrap; }
.st.grey { color: var(--text-2); }
.st.cyan { color: var(--cyan); }
.st.green { color: var(--green); }
.st.red { color: var(--red); }
.task { font-size: 11.5px; color: var(--text-1); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pending .task { color: var(--text-2); }
.caret { font-style: normal; color: var(--cyan); margin-left: 1px; animation: kf-blink 0.9s steps(1) infinite; }
.metric { font-size: 11px; color: var(--ac); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pending .metric { color: var(--text-2); }
.step { position: absolute; right: 6px; bottom: 3px; font-size: 9px; color: rgba(108, 134, 163, 0.45); }
.flash { position: absolute; inset: -1px; pointer-events: none; border: 1px solid var(--ac); background: color-mix(in srgb, var(--ac) 16%, transparent); box-shadow: 0 0 18px var(--ac); opacity: 0; }
.done .flash { animation: kf-flash 0.9s ease-out 1; }
.failed .flash { animation: kf-flash-twice 1.1s ease-out 1; }
</style>
