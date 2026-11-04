<script setup lang="ts">
/**
 * 沿面板边框匀速流动的一段亮光（约 80px，周期 6s）。
 * 四条边各一个裁剪条，亮条只做 translate（WAAPI，合成层执行），按周长分配时间片，速度处处相同。
 */
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fx } from '@/stores/fx'

const props = withDefaults(defineProps<{ period?: number; length?: number; color?: string }>(), {
  period: 6000, length: 80, color: 'var(--cyan)',
})

const STRIPS = [
  { side: 'top', bar: 'h' }, { side: 'right', bar: 'v' }, { side: 'bottom', bar: 'h rev' }, { side: 'left', bar: 'v rev' },
] as const
const host = ref<HTMLElement | null>(null)
const bars = ref<HTMLElement[]>([])
let anims: Animation[] = []
let ro: ResizeObserver | null = null
let lastW = 0, lastH = 0

type Kf = { transform: string; offset: number; easing?: string }

function frames(axis: 'X' | 'Y', from: number, to: number, start: number, dur: number, period: number): Kf[] {
  const tf = (v: number) => `translate${axis}(${v}px)`
  const s = start / period
  const e = (start + dur) / period
  if (e <= 1) {
    const k: Kf[] = []
    if (s > 0) k.push({ transform: tf(from), offset: 0, easing: 'step-end' })
    k.push({ transform: tf(from), offset: s, easing: 'linear' })
    k.push({ transform: tf(to), offset: e, easing: 'step-end' })
    if (e < 1) k.push({ transform: tf(to), offset: 1 })
    return k
  }
  // 跨越周期末尾：开头补上尾段
  const wrap = e - 1
  const mid = from + (to - from) * ((1 - s) / (e - s))
  return [
    { transform: tf(mid), offset: 0, easing: 'linear' },
    { transform: tf(to), offset: wrap, easing: 'step-end' },
    { transform: tf(from), offset: s, easing: 'linear' },
    { transform: tf(mid), offset: 1 },
  ]
}

function stop(): void {
  anims.forEach((a) => a.cancel())
  anims = []
}

function build(): void {
  stop()
  const el = host.value
  if (!el || !fx.comet || bars.value.length !== 4) return
  const W = el.clientWidth, H = el.clientHeight
  if (W < 40 || H < 40) return
  lastW = W; lastH = H
  const L = props.length
  const P = 2 * (W + H)
  const v = P / props.period
  const span = (len: number) => (len + L) / v
  const t = [0, W / v, (W + H) / v, (2 * W + H) / v]
  const spec: [('X' | 'Y'), number, number, number][] = [
    ['X', -L, W, span(W)],
    ['Y', -L, H, span(H)],
    ['X', W, -L, span(W)],
    ['Y', H, -L, span(H)],
  ]
  // 让不同面板的光点错开，不要整齐划一
  const phase = -Math.random() * props.period
  spec.forEach(([axis, from, to, dur], i) => {
    const bar = bars.value[i]
    if (!bar) return
    const a = bar.animate(frames(axis, from, to, t[i]!, dur, props.period) as Keyframe[], {
      duration: props.period, iterations: Infinity, delay: phase,
    })
    anims.push(a)
  })
}

onMounted(() => {
  build()
  ro = new ResizeObserver(() => {
    const el = host.value
    if (!el) return
    if (Math.abs(el.clientWidth - lastW) > 2 || Math.abs(el.clientHeight - lastH) > 2) build()
  })
  if (host.value) ro.observe(host.value)
})
watch(() => fx.comet, build)
onBeforeUnmount(() => { stop(); ro?.disconnect() })
</script>

<template>
  <div v-show="fx.comet" ref="host" class="comet" :style="{ '--c': color, '--L': length + 'px' }" aria-hidden="true">
    <div v-for="(s, i) in STRIPS" :key="s.side" class="strip" :class="s.side">
      <i :ref="(el) => { if (el) bars[i] = el as HTMLElement }" class="bar" :class="s.bar" />
    </div>
  </div>
</template>

<style scoped>
.comet { position: absolute; inset: -1px; pointer-events: none; z-index: 2; }
.strip { position: absolute; overflow: hidden; }
.strip.top { left: 0; right: 0; top: -1px; height: 3px; }
.strip.bottom { left: 0; right: 0; bottom: -1px; height: 3px; }
.strip.left { top: 0; bottom: 0; left: -1px; width: 3px; }
.strip.right { top: 0; bottom: 0; right: -1px; width: 3px; }
.bar { position: absolute; top: 0; left: 0; display: block; will-change: transform; transform: translateX(-200%); }
.bar.h { width: var(--L); height: 3px; background: linear-gradient(90deg, transparent, color-mix(in srgb, var(--c) 70%, transparent) 70%, #fff); }
.bar.h.rev { background: linear-gradient(270deg, transparent, color-mix(in srgb, var(--c) 70%, transparent) 70%, #fff); }
.bar.v { width: 3px; height: var(--L); background: linear-gradient(180deg, transparent, color-mix(in srgb, var(--c) 70%, transparent) 70%, #fff); }
.bar.v.rev { background: linear-gradient(0deg, transparent, color-mix(in srgb, var(--c) 70%, transparent) 70%, #fff); }
.bar::after {
  content: '';
  position: absolute;
  inset: 0;
  filter: blur(2px);
  background: inherit;
  opacity: 0.9;
}
</style>
