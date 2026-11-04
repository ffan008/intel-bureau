<script setup lang="ts">
/** 「立即出报」（§4.1）：霓虹描边、悬停扫光；运行中显示能量进度（完成阶段数 / 12），再次点击可取消。 */
import { computed, ref } from 'vue'
import { cancelRun, live, progress, runNow, running } from '@/stores/live'
import { STAGE_LABEL } from '@/utils/meta'
import { confirm } from '../ui/confirm'
import Icon from '../Icon.vue'

const busy = ref(false)
const done = computed(() => Math.round(progress.value * 12))
const stageNow = computed(() => live.run?.stages.find((s) => s.status === 'running'))

async function click(): Promise<void> {
  if (busy.value) return
  busy.value = true
  try {
    if (running.value) {
      const ok = await confirm({ title: '取消本次运行', message: '确定要取消正在进行的出报吗？', detail: '已经完成的阶段不会回滚；未投递的通道不会收到报告。', okText: '取消运行', danger: true })
      if (ok) await cancelRun()
    } else {
      await runNow()
    }
  } catch { /* 错误已由 client 弹出 toast */ } finally {
    busy.value = false
  }
}
</script>

<template>
  <button class="run" :class="{ on: running, busy }" :disabled="busy" :aria-label="running ? '取消本次运行' : '立即出报'" @click="click">
    <svg class="frame" viewBox="0 0 176 44" aria-hidden="true">
      <polygon points="12.5,0.5 175.5,0.5 175.5,31.5 163.5,43.5 0.5,43.5 0.5,12.5" fill="none" stroke="currentColor" stroke-width="1" />
      <polyline points="0.5,20 0.5,12.5 12.5,0.5 40,0.5" fill="none" stroke="currentColor" stroke-width="2.4" />
      <polyline points="136,43.5 163.5,43.5 175.5,31.5 175.5,24" fill="none" stroke="currentColor" stroke-width="2.4" />
    </svg>
    <span class="sweep fx-loop" aria-hidden="true" />
    <span class="body">
      <Icon :name="running ? 'stop' : 'play'" :size="15" />
      <span v-if="!running" class="lbl">立即出报</span>
      <span v-else class="lbl2">
        <b>{{ stageNow ? STAGE_LABEL[stageNow.name] : '准备' }}中 <i class="num">{{ done }}/12</i></b>
        <small>再次点击取消</small>
      </span>
    </span>
    <span class="energy" aria-hidden="true">
      <i :style="{ transform: `scaleX(${running ? Math.max(0.02, progress) : 0})` }" />
      <em v-for="k in 11" :key="k" :style="{ left: (k / 12) * 100 + '%' }" />
    </span>
  </button>
</template>

<style scoped>
.run {
  position: relative;
  width: 176px;
  height: 44px;
  flex: none;
  color: var(--cyan);
  overflow: hidden;
  clip-path: polygon(12px 0, 100% 0, 100% calc(100% - 12px), calc(100% - 12px) 100%, 0 100%, 0 12px);
  background: linear-gradient(180deg, rgba(34, 228, 255, 0.16), rgba(34, 228, 255, 0.04));
  transition: transform var(--t-fast);
}
.run:active { transform: translateY(1px); }
.frame {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  filter: drop-shadow(0 0 4px currentColor);
}
.sweep {
  position: absolute;
  top: 0;
  bottom: 0;
  left: 0;
  width: 40%;
  background: linear-gradient(90deg, transparent, rgba(255, 255, 255, 0.28), transparent);
  transform: translateX(-120%) skewX(-20deg);
  opacity: 0;
}
.run:hover:not(.on) .sweep { opacity: 1; animation: kf-sweep 1.1s var(--ease-out) infinite; }
.body { position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 9px; height: 100%; padding: 0 14px 4px; }
.lbl { font-size: 16px; font-weight: 700; letter-spacing: 4px; color: var(--text-0); text-shadow: 0 0 10px rgba(34, 228, 255, 0.8); }
.lbl2 { display: flex; flex-direction: column; align-items: flex-start; line-height: 1.15; }
.lbl2 b { font-size: 13px; color: var(--text-0); font-weight: 600; white-space: nowrap; }
.lbl2 b i { font-style: normal; color: var(--cyan); margin-left: 4px; }
.lbl2 small { font-size: 10.5px; color: var(--text-2); }
.energy { position: absolute; left: 10px; right: 10px; bottom: 6px; height: 3px; background: rgba(34, 228, 255, 0.12); }
.energy i { position: absolute; inset: 0; transform-origin: left; background: linear-gradient(90deg, var(--cyan), var(--violet)); box-shadow: 0 0 8px var(--cyan); transition: transform 0.5s var(--ease-out-expo); }
.energy em { position: absolute; top: 0; bottom: 0; width: 1px; background: rgba(3, 6, 15, 0.9); }
.run::before { content: ''; position: absolute; inset: 0; box-shadow: inset 0 0 18px rgba(34, 228, 255, 0.22); pointer-events: none; }
.run.on { color: var(--amber); background: linear-gradient(180deg, rgba(255, 176, 32, 0.14), rgba(255, 176, 32, 0.03)); }
.run.on::before { box-shadow: inset 0 0 18px rgba(255, 176, 32, 0.2); }
.run.on .lbl2 b i { color: var(--amber); }
.run:disabled { cursor: progress; }
</style>
