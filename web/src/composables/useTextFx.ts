/** 文字动效：数字滚动（easeOutExpo）、乱码解码、打字机。特效「关」时直接显示终值。 */
import { onBeforeUnmount, ref, watch, type Ref } from 'vue'
import { fx } from '@/stores/fx'

const easeOutExpo = (t: number) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t))

/** 数值从当前值滚到目标值；首次从 0 开始。返回显示值和「刚变化」标记（用于闪光） */
export function useCountUp(target: () => number, duration = 1200) {
  const display = ref(0)
  const flash = ref(0)
  let raf = 0
  let first = true
  watch(target, (to, prev) => {
    cancelAnimationFrame(raf)
    if (!Number.isFinite(to)) { display.value = 0; return }
    if (!first && prev !== undefined && to !== prev) flash.value++
    first = false
    if (!fx.textFx) { display.value = to; return }
    const from = display.value
    const t0 = performance.now()
    const step = (t: number) => {
      const p = Math.min(1, (t - t0) / duration)
      display.value = from + (to - from) * easeOutExpo(p)
      if (p < 1) raf = requestAnimationFrame(step)
    }
    raf = requestAnimationFrame(step)
  }, { immediate: true })
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return { display, flash }
}

const GLYPHS = '01<>/\\[]{}#%&*+=?ABCDEFXYZ情报密码信号解析矩阵阵列数据流▓▒░'

/** 解码动效：乱码逐字还原，总时长 ms（默认 600） */
export function useDecode(text: () => string, ms = 600) {
  const out = ref(text())
  let raf = 0
  watch(text, (to) => {
    cancelAnimationFrame(raf)
    if (!fx.textFx || !to) { out.value = to; return }
    const chars = [...to]
    const t0 = performance.now()
    const tick = (t: number) => {
      const p = Math.min(1, (t - t0) / ms)
      const fixed = Math.floor(p * chars.length)
      let s = ''
      for (let i = 0; i < chars.length; i++) {
        const c = chars[i]!
        s += i < fixed || c === ' ' ? c : GLYPHS[(Math.random() * GLYPHS.length) | 0]
      }
      out.value = s
      if (p < 1) raf = requestAnimationFrame(tick)
      else out.value = to
    }
    raf = requestAnimationFrame(tick)
  }, { immediate: true })
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return out
}

/** 打字机：每字 msPerChar。文本变化时从头打。 */
export function useTypewriter(text: Ref<string> | (() => string), msPerChar = 22) {
  const src = typeof text === 'function' ? text : () => text.value
  const out = ref('')
  let raf = 0
  watch(src, (to) => {
    cancelAnimationFrame(raf)
    if (!fx.textFx || !to) { out.value = to ?? ''; return }
    const chars = [...to]
    const t0 = performance.now()
    const tick = (t: number) => {
      const n = Math.min(chars.length, Math.floor((t - t0) / msPerChar) + 1)
      out.value = chars.slice(0, n).join('')
      if (n < chars.length) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
  }, { immediate: true })
  onBeforeUnmount(() => cancelAnimationFrame(raf))
  return out
}
