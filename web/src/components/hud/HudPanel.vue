<script setup lang="ts">
/**
 * HUD 面板（UI_DESIGN §3）：半透明底 + blur(10px) + 1px 描边 + 四角 L 形亮角 + 标题栏 + 边框流光 + 依次入场。
 */
import HudComet from './HudComet.vue'

withDefaults(defineProps<{
  title?: string
  code?: string
  /** 入场顺序（每个延迟 60ms） */
  index?: number
  /** 主体不加内边距 */
  flush?: boolean
  comet?: boolean
  /** 普通页面用：不入场、不流光 */
  lite?: boolean
  accent?: string
}>(), { index: 0, flush: false, comet: true, lite: false, accent: 'var(--cyan)' })
</script>

<template>
  <section
    class="hud"
    :class="{ 'hud-enter': !lite, lite }"
    :style="{ animationDelay: lite ? undefined : index * 60 + 'ms', '--accent': accent }"
  >
    <span class="corners" aria-hidden="true" />
    <HudComet v-if="comet && !lite" :color="accent" />
    <header v-if="title || $slots.head" class="hud-head">
      <span class="sq" aria-hidden="true" />
      <h2 class="ttl">{{ title }}</h2>
      <span v-if="code" class="code">{{ code }}</span>
      <slot name="head" />
      <span class="spacer" />
      <slot name="actions" />
    </header>
    <div class="hud-body" :class="{ flush }">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.hud {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background:
    linear-gradient(180deg, rgba(34, 228, 255, 0.045), rgba(34, 228, 255, 0) 38px),
    var(--panel);
  border: 1px solid var(--line);
  border-radius: 2px;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow: inset 0 0 40px rgba(34, 228, 255, 0.025);
}
.corners {
  position: absolute;
  inset: -1px;
  pointer-events: none;
  z-index: 3;
  --c: var(--accent);
  background:
    linear-gradient(var(--c), var(--c)) left top / 14px 2px,
    linear-gradient(var(--c), var(--c)) left top / 2px 14px,
    linear-gradient(var(--c), var(--c)) right top / 14px 2px,
    linear-gradient(var(--c), var(--c)) right top / 2px 14px,
    linear-gradient(var(--c), var(--c)) left bottom / 14px 2px,
    linear-gradient(var(--c), var(--c)) left bottom / 2px 14px,
    linear-gradient(var(--c), var(--c)) right bottom / 14px 2px,
    linear-gradient(var(--c), var(--c)) right bottom / 2px 14px;
  background-repeat: no-repeat;
  filter: drop-shadow(0 0 4px color-mix(in srgb, var(--c) 70%, transparent));
}
.hud-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  height: 34px;
  flex: none;
  padding: 0 12px;
}
.hud-head::after {
  content: '';
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: 0;
  height: 1px;
  background: linear-gradient(90deg, var(--line-strong), rgba(80, 200, 255, 0.08) 60%, transparent);
}
.sq {
  width: 6px;
  height: 6px;
  flex: none;
  background: var(--accent);
  box-shadow: 0 0 6px var(--accent), 0 0 14px color-mix(in srgb, var(--accent) 45%, transparent);
}
.ttl {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-0);
  letter-spacing: 1px;
  white-space: nowrap;
}
.code {
  font-family: var(--font-display);
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--text-2);
  white-space: nowrap;
}
.spacer { flex: 1; }
.hud-body {
  position: relative;
  flex: 1;
  min-height: 0;
  padding: 10px 12px 12px;
}
.hud-body.flush { padding: 0; }
.hud.lite { backdrop-filter: blur(6px); -webkit-backdrop-filter: blur(6px); }
</style>
