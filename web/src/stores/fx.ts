/**
 * 特效强度（高 / 中 / 低 / 关）。偏好存 localStorage（不是令牌，允许持久化）。
 * prefers-reduced-motion: reduce 时强制按「关」处理，界面上提示。
 * <html data-fx> 驱动 CSS 门控（styles/motion.css），JS 循环读 fx.* 计算属性。
 */
import { computed, reactive, watchEffect } from 'vue'

export type FxLevel = 'high' | 'medium' | 'low' | 'off'
export const FX_LEVELS: { key: FxLevel; label: string; desc: string }[] = [
  { key: 'high', label: '高', desc: '全部特效：160 粒子、边框流光、故障标题、数据光点' },
  { key: 'medium', label: '中', desc: '100 粒子，保留流光与光点' },
  { key: 'low', label: '低', desc: '40 粒子，关闭边框流光、故障标题和装饰性循环' },
  { key: 'off', label: '关', desc: '停止所有循环动画，数字和文字直接显示' },
]
const KEY = 'bureau.fx'
const PARTICLES: Record<FxLevel, number> = { high: 160, medium: 100, low: 40, off: 0 }

function load(): FxLevel {
  try {
    const v = localStorage.getItem(KEY)
    if (v === 'high' || v === 'medium' || v === 'low' || v === 'off') return v
  } catch { /* 隐私模式下 localStorage 可能不可用 */ }
  return 'high'
}

const mq = typeof matchMedia === 'function' ? matchMedia('(prefers-reduced-motion: reduce)') : null
const state = reactive({ chosen: load(), reducedMotion: mq?.matches ?? false })
mq?.addEventListener('change', (e) => { state.reducedMotion = e.matches })

const level = computed<FxLevel>(() => (state.reducedMotion ? 'off' : state.chosen))

export const fx = reactive({
  chosen: computed(() => state.chosen),
  reducedMotion: computed(() => state.reducedMotion),
  level,
  particles: computed(() => PARTICLES[level.value]),
  /** 任何循环动画是否允许 */
  loops: computed(() => level.value !== 'off'),
  /** 装饰性强的循环（边框流光、故障标题、网格滚动） */
  rich: computed(() => level.value === 'high' || level.value === 'medium'),
  comet: computed(() => level.value === 'high' || level.value === 'medium'),
  glitch: computed(() => level.value === 'high' || level.value === 'medium'),
  /** ECharts lines 光点 */
  flowDots: computed(() => level.value !== 'off'),
  /** 数字滚动、解码、打字机 */
  textFx: computed(() => level.value !== 'off'),
})

export function setFxLevel(v: FxLevel): void {
  state.chosen = v
  try { localStorage.setItem(KEY, v) } catch { /* ignore */ }
}

watchEffect(() => {
  if (typeof document !== 'undefined') document.documentElement.dataset.fx = level.value
})
