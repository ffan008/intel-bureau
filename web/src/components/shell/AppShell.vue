<script setup lang="ts">
/** 其它页面的外壳（UI_DESIGN §5）：左侧 64px 竖向导航 + 顶部标题与面包屑 + 可滚动内容（最小 1280） */
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { NAV } from '@/router'
import { running, progress } from '@/stores/live'
import Icon from '../Icon.vue'
import MockBadge from './MockBadge.vue'
import StreamDot from './StreamDot.vue'

const route = useRoute()
const current = computed(() => NAV.find((n) => n.path === route.path))
</script>

<template>
  <div class="shell">
    <nav class="side" aria-label="主导航">
      <RouterLink to="/" class="logo" aria-label="作战大屏">
        <svg viewBox="0 0 40 40" aria-hidden="true">
          <defs><linearGradient id="lg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#22e4ff" /><stop offset="1" stop-color="#8b5cff" /></linearGradient></defs>
          <path d="M20 3 35 11.5v17L20 37 5 28.5v-17z" fill="none" stroke="url(#lg)" stroke-width="2" />
          <circle cx="20" cy="20" r="5.5" fill="none" stroke="#22e4ff" stroke-width="1.6" />
          <path d="M20 20 27 14" stroke="#22e4ff" stroke-width="1.6" stroke-linecap="round" />
        </svg>
      </RouterLink>
      <RouterLink v-for="n in NAV" :key="n.path" :to="n.path" class="nav" :class="{ on: route.path === n.path }" :aria-label="n.title">
        <Icon :name="n.icon" :size="20" />
        <span class="tip"><b>{{ n.title }}</b><i class="disp">{{ n.code }}</i></span>
      </RouterLink>
      <span class="grow" />
      <span v-if="running" class="run-ind" :title="`流水线运行中 ${Math.round(progress * 100)}%`">
        <i :style="{ transform: `scaleY(${Math.max(0.04, progress)})` }" />
      </span>
    </nav>
    <div class="main">
      <header class="top">
        <div class="crumb">
          <RouterLink to="/" class="home disp">INTEL BUREAU</RouterLink>
          <Icon name="chevronRight" :size="12" class="sep" />
          <span class="here">{{ current?.title }}</span>
        </div>
        <h1 class="title">{{ current?.title }}<span class="code disp">{{ current?.code }}</span></h1>
        <span class="spacer" />
        <slot name="header" />
        <StreamDot />
        <MockBadge />
      </header>
      <div class="content"><slot /></div>
    </div>
  </div>
</template>

<style scoped>
.shell { position: relative; z-index: 1; display: flex; height: 100vh; }
.side {
  position: relative;
  z-index: 20;
  flex: none;
  width: 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 0;
  background: linear-gradient(180deg, rgba(8, 18, 40, 0.9), rgba(4, 10, 24, 0.92));
  border-right: 1px solid var(--line);
}
.logo { width: 40px; height: 40px; margin-bottom: 14px; filter: drop-shadow(0 0 6px rgba(34, 228, 255, 0.45)); }
.logo svg { width: 100%; height: 100%; }
.nav { position: relative; width: 64px; height: 48px; display: flex; align-items: center; justify-content: center; color: var(--text-2); text-decoration: none; }
.nav:hover { color: var(--text-0); text-decoration: none; }
.nav::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  background: var(--cyan);
  box-shadow: 0 0 10px var(--cyan), 0 0 20px rgba(34, 228, 255, 0.5);
  opacity: 0;
  transform: scaleY(0.3);
  transition: opacity var(--t-fast), transform var(--t-mid) var(--ease-out-expo);
}
.nav.on { color: var(--cyan); }
.nav.on::before { opacity: 1; transform: none; }
.nav.on::after { content: ''; position: absolute; inset: 6px 10px; border-radius: 4px; background: radial-gradient(circle, rgba(34, 228, 255, 0.14), transparent 70%); }
.tip {
  position: absolute;
  left: 58px;
  top: 50%;
  display: flex;
  flex-direction: column;
  gap: 1px;
  padding: 6px 10px;
  white-space: nowrap;
  background: rgba(6, 14, 32, 0.96);
  border: 1px solid var(--line-strong);
  border-radius: 3px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5);
  pointer-events: none;
  opacity: 0;
  transform: translate(-4px, -50%);
  transition: opacity var(--t-fast), transform var(--t-fast);
}
.tip b { font-size: 13px; font-weight: 600; color: var(--text-0); }
.tip i { font-style: normal; font-size: 9px; color: var(--text-2); }
.nav:hover .tip, .nav:focus-visible .tip { opacity: 1; transform: translate(0, -50%); }
.grow { flex: 1; }
.run-ind { width: 4px; height: 80px; border-radius: 2px; background: rgba(34, 228, 255, 0.12); overflow: hidden; display: flex; align-items: flex-end; }
.run-ind i { display: block; width: 100%; height: 100%; background: var(--cyan); box-shadow: 0 0 8px var(--cyan); transform-origin: bottom; transition: transform 0.4s; }
.main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
.top {
  position: relative;
  flex: none;
  display: flex;
  align-items: center;
  gap: 16px;
  height: 64px;
  padding: 0 28px;
  border-bottom: 1px solid var(--line);
  background: linear-gradient(180deg, rgba(8, 18, 40, 0.72), rgba(6, 14, 32, 0.4));
  backdrop-filter: blur(8px);
  min-width: 1216px;
}
.top::after { content: ''; position: absolute; left: 28px; bottom: -1px; width: 180px; height: 1px; background: linear-gradient(90deg, var(--cyan), transparent); box-shadow: 0 0 8px var(--cyan); }
.crumb { display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-2); }
.home { font-size: 10px; letter-spacing: 2px; color: var(--text-2); }
.home:hover { color: var(--cyan); text-decoration: none; }
.sep { color: var(--text-2); }
.here { color: var(--text-1); }
.title { margin: 0 0 0 10px; padding-left: 16px; border-left: 1px solid var(--line); font-size: 18px; font-weight: 600; display: flex; align-items: baseline; gap: 10px; letter-spacing: 1px; }
.code { font-size: 10px; letter-spacing: 3px; color: var(--text-2); font-weight: 400; }
.spacer { flex: 1; }
.content { flex: 1; min-height: 0; overflow: auto; }
.content > :deep(*) { min-width: 1216px; }
</style>
