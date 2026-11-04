<script setup lang="ts">
/** 顶栏 72px（§4.1）：故障风标题｜模式 LIVE/DEMO｜三平台连接灯｜时钟 + 倒计时｜立即出报 */
import { computed } from 'vue'
import { NAV } from '@/router'
import { app } from '@/stores/app'
import { live } from '@/stores/live'
import Icon from '../Icon.vue'
import MockBadge from '../shell/MockBadge.vue'
import StreamDot from '../shell/StreamDot.vue'
import GlitchTitle from './GlitchTitle.vue'
import PlatformLamps from './PlatformLamps.vue'
import DeckClock from './DeckClock.vue'
import RunButton from './RunButton.vue'

const mode = computed(() => live.overview?.mode ?? app.serverMode)
const links = NAV.filter((n) => n.path !== '/')
</script>

<template>
  <header class="topbar">
    <svg class="bgshape" viewBox="0 0 1888 72" preserveAspectRatio="none" aria-hidden="true">
      <defs>
        <linearGradient id="tb-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stop-color="#0c1d40" stop-opacity="0.85" />
          <stop offset="1" stop-color="#081430" stop-opacity="0.35" />
        </linearGradient>
        <linearGradient id="tb-line" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stop-color="#22e4ff" stop-opacity="0" />
          <stop offset="0.3" stop-color="#22e4ff" stop-opacity="0.55" />
          <stop offset="0.5" stop-color="#8b5cff" stop-opacity="0.9" />
          <stop offset="0.7" stop-color="#22e4ff" stop-opacity="0.55" />
          <stop offset="1" stop-color="#22e4ff" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path d="M0 0H1888V52H1166L1146 70H562L542 52H0Z" fill="url(#tb-fill)" />
      <path d="M0 52H542L562 70H1146L1166 52H1888" fill="none" stroke="url(#tb-line)" stroke-width="1.2" />
      <path d="M582 66H1126" stroke="#22e4ff" stroke-opacity="0.55" stroke-width="2" />
      <path d="M524 52h12M1172 52h12" stroke="#22e4ff" stroke-width="3" />
    </svg>
    <div class="left">
      <GlitchTitle />
      <div class="sub">
        <span class="disp">PERSONAL INTELLIGENCE DECK</span>
        <span class="sep" />
        <span>v{{ app.version || '—' }}</span>
      </div>
    </div>
    <div class="mid">
      <span class="mode" :class="mode" :title="mode === 'demo' ? '演示模式：所有平台使用合成数据' : '实时模式：从白名单群采集真实消息'">
        <i class="fx-loop" />
        <b class="disp">{{ mode === 'demo' ? 'DEMO' : 'LIVE' }}</b>
      </span>
      <PlatformLamps />
      <StreamDot />
    </div>
    <div class="right">
      <nav class="links" aria-label="页面">
        <RouterLink v-for="n in links" :key="n.path" :to="n.path" class="lk" :aria-label="n.title">
          <Icon :name="n.icon" :size="17" />
          <span class="tip">{{ n.title }}</span>
        </RouterLink>
      </nav>
      <DeckClock />
      <MockBadge />
      <RunButton />
    </div>
  </header>
</template>

<style scoped>
.topbar { position: relative; z-index: 10; display: grid; grid-template-columns: 548px 600px 1fr; align-items: center; height: 72px; padding: 0 4px 6px; }
.bgshape { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
.left { position: relative; display: flex; flex-direction: column; gap: 5px; padding-left: 6px; }
.sub { display: flex; align-items: center; gap: 8px; padding-left: 26px; font-size: 10.5px; color: var(--text-2); }
.sub .disp { font-size: 9px; letter-spacing: 3px; }
.sub .sep { width: 18px; height: 1px; background: var(--line-strong); }
.mid { position: relative; display: flex; align-items: center; justify-content: center; gap: 14px; padding-top: 8px; }
.mode { display: inline-flex; align-items: center; gap: 7px; height: 28px; padding: 0 12px; border-radius: 2px; font-size: 12px; color: var(--text-1); border: 1px solid; }
.mode.live { border-color: rgba(43, 255, 154, 0.45); background: rgba(43, 255, 154, 0.07); }
.mode.demo { border-color: rgba(180, 140, 255, 0.5); background: rgba(139, 92, 255, 0.1); }
.mode i { width: 7px; height: 7px; border-radius: 50%; }
.mode.live i { background: var(--green); box-shadow: 0 0 8px var(--green); animation: kf-breathe 2s ease-in-out infinite; }
.mode.demo i { background: var(--demo); box-shadow: 0 0 8px var(--demo); }
.mode b { font-size: 11px; letter-spacing: 2px; color: var(--text-0); }
.right { position: relative; display: flex; align-items: center; justify-content: flex-end; gap: 14px; padding-right: 2px; min-width: 0; }
.links { display: flex; gap: 0; padding-right: 12px; border-right: 1px solid var(--line); }
.lk { position: relative; width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; color: var(--text-2); border-radius: 3px; }
.lk:hover { color: var(--cyan); background: rgba(34, 228, 255, 0.08); text-decoration: none; }
.tip {
  position: absolute;
  top: calc(100% + 6px);
  left: 50%;
  z-index: 50;
  padding: 3px 8px;
  white-space: nowrap;
  font-size: 12px;
  color: var(--text-0);
  background: rgba(6, 14, 32, 0.96);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  opacity: 0;
  transform: translate(-50%, -3px);
  transition: opacity var(--t-fast), transform var(--t-fast);
  pointer-events: none;
}
.lk:hover .tip, .lk:focus-visible .tip { opacity: 1; transform: translate(-50%, 0); }
</style>
