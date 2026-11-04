<script setup lang="ts">
/**
 * 背景层（UI_DESIGN §2）：径向渐变 → Canvas 星点粒子（30fps，近距连线，隐藏时暂停）→ 透视网格地板 → 扫描线/噪点/暗角。
 * 粒子数随特效强度：高 160 / 中 100 / 低 40 / 关 0；lite（普通页面）再减半。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { fx } from '@/stores/fx'

const props = withDefaults(defineProps<{ lite?: boolean }>(), { lite: false })

const canvas = ref<HTMLCanvasElement | null>(null)
const count = computed(() => Math.round(fx.particles * (props.lite ? 0.5 : 1)))

interface P { x: number; y: number; vx: number; vy: number; r: number; a: number; tw: number; star: boolean }
let parts: P[] = []
let ctx: CanvasRenderingContext2D | null = null
let W = 0, H = 0, dpr = 1
let raf = 0
let last = 0
const FRAME = 1000 / 30
const LINK = 118

function seed(n: number): void {
  parts = Array.from({ length: n }, () => {
    const star = Math.random() < 0.35
    return {
      x: Math.random() * W, y: Math.random() * H,
      vx: (Math.random() - 0.5) * (star ? 0.04 : 0.22), vy: (Math.random() - 0.5) * (star ? 0.04 : 0.18),
      r: star ? Math.random() * 0.9 + 0.3 : Math.random() * 1.3 + 0.6,
      a: Math.random() * 0.5 + 0.35, tw: Math.random() * Math.PI * 2, star,
    }
  })
}

function resize(): void {
  const c = canvas.value
  if (!c) return
  dpr = Math.min(1.5, window.devicePixelRatio || 1)
  W = window.innerWidth
  H = window.innerHeight
  c.width = Math.round(W * dpr)
  c.height = Math.round(H * dpr)
  ctx = c.getContext('2d')
  ctx?.setTransform(dpr, 0, 0, dpr, 0, 0)
  if (parts.length !== count.value) seed(count.value)
  else for (const p of parts) { p.x = Math.min(p.x, W); p.y = Math.min(p.y, H) }
  if (!fx.loops) draw(0)
}

function draw(t: number): void {
  if (!ctx) return
  ctx.clearRect(0, 0, W, H)
  const moving = fx.loops
  for (const p of parts) {
    if (moving) {
      p.x += p.vx; p.y += p.vy
      if (p.x < -10) p.x = W + 10; else if (p.x > W + 10) p.x = -10
      if (p.y < -10) p.y = H + 10; else if (p.y > H + 10) p.y = -10
    }
  }
  ctx.lineWidth = 0.6
  for (let i = 0; i < parts.length; i++) {
    const a = parts[i]!
    if (a.star) continue
    for (let j = i + 1; j < parts.length; j++) {
      const b = parts[j]!
      if (b.star) continue
      const dx = a.x - b.x, dy = a.y - b.y
      const d2 = dx * dx + dy * dy
      if (d2 < LINK * LINK) {
        const o = (1 - Math.sqrt(d2) / LINK) * 0.22
        ctx.strokeStyle = `rgba(34,228,255,${o.toFixed(3)})`
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke()
      }
    }
  }
  for (const p of parts) {
    const tw = p.star ? 0.55 + 0.45 * Math.sin(t / 900 + p.tw) : 1
    ctx.globalAlpha = p.a * tw
    ctx.fillStyle = p.star ? '#cfe8ff' : '#22e4ff'
    ctx.beginPath(); ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2); ctx.fill()
  }
  ctx.globalAlpha = 1
}

function loop(t: number): void {
  raf = requestAnimationFrame(loop)
  if (t - last < FRAME) return
  last = t - ((t - last) % FRAME)
  draw(t)
}
function start(): void {
  cancelAnimationFrame(raf)
  if (!fx.loops || document.hidden || !parts.length) { draw(0); return }
  raf = requestAnimationFrame(loop)
}
const onVis = () => (document.hidden ? cancelAnimationFrame(raf) : start())

onMounted(() => {
  resize()
  seed(count.value)
  start()
  window.addEventListener('resize', resize, { passive: true })
  document.addEventListener('visibilitychange', onVis)
})
watch(count, (n) => { seed(n); start() })
watch(() => fx.loops, start)
onBeforeUnmount(() => {
  cancelAnimationFrame(raf)
  window.removeEventListener('resize', resize)
  document.removeEventListener('visibilitychange', onVis)
})
</script>

<template>
  <div class="bg" aria-hidden="true">
    <div class="grad" />
    <canvas ref="canvas" class="stars" />
    <div class="floor" :class="{ lite }">
      <div class="plane fx-rich" />
    </div>
    <div class="scan" />
    <div class="vignette" />
  </div>
</template>

<style scoped>
.bg { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
.grad {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse 70% 60% at 50% 34%, #0a1a3a 0%, rgba(10, 26, 58, 0.55) 38%, transparent 72%),
    radial-gradient(ellipse 40% 30% at 82% 12%, rgba(139, 92, 255, 0.07), transparent 70%),
    var(--bg-0);
}
.stars { position: absolute; inset: 0; width: 100%; height: 100%; }
.floor {
  position: absolute;
  left: 0;
  right: 0;
  bottom: 0;
  height: 30%;
  perspective: 420px;
  perspective-origin: 50% 0%;
  overflow: hidden;
  -webkit-mask-image: linear-gradient(to bottom, transparent 0%, #000 45%);
  mask-image: linear-gradient(to bottom, transparent 0%, #000 45%);
  opacity: 0.55;
}
.floor.lite { opacity: 0.3; }
.plane {
  position: absolute;
  left: -60%;
  right: -60%;
  bottom: -60px;
  height: 320%;
  transform-origin: 50% 100%;
  transform: rotateX(60deg);
  background-image:
    linear-gradient(rgba(34, 228, 255, 0.32) 1px, transparent 1px),
    linear-gradient(90deg, rgba(34, 228, 255, 0.24) 1px, transparent 1px);
  background-size: 60px 60px;
  animation: kf-grid-scroll 3.2s linear infinite;
  will-change: transform;
}
.scan {
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(0deg, rgba(255, 255, 255, 0.04) 0 1px, transparent 1px 3px);
  opacity: 1;
  mix-blend-mode: overlay;
}
.vignette {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(ellipse at center, transparent 55%, rgba(0, 0, 0, 0.55) 100%),
    url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 .05 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
}
</style>
