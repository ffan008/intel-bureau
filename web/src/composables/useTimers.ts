import { onBeforeUnmount, onMounted, ref } from 'vue'

/** 全局 1 秒时钟（所有组件共用一个定时器，对齐到整秒） */
export const now = ref(Date.now())
let clockUsers = 0
let alignTimer: ReturnType<typeof setTimeout> | null = null
let tickTimer: ReturnType<typeof setInterval> | null = null
export function useNow() {
  onMounted(() => {
    if (clockUsers++ > 0) return
    now.value = Date.now()
    alignTimer = setTimeout(() => {
      alignTimer = null
      now.value = Date.now()
      tickTimer = setInterval(() => (now.value = Date.now()), 1000)
    }, 1000 - (Date.now() % 1000))
  })
  onBeforeUnmount(() => {
    if (--clockUsers > 0) return
    if (alignTimer) clearTimeout(alignTimer)
    if (tickTimer) clearInterval(tickTimer)
    alignTimer = tickTimer = null
  })
  return now
}

/** 页面隐藏时暂停的 setInterval，卸载时自动清理 */
export function useInterval(fn: () => void, ms: () => number, enabled: () => boolean = () => true) {
  let t: ReturnType<typeof setInterval> | null = null
  const stop = () => { if (t) clearInterval(t); t = null }
  const start = () => {
    stop()
    if (!enabled() || document.hidden) return
    t = setInterval(() => { if (!document.hidden) fn() }, ms())
  }
  const onVis = () => (document.hidden ? stop() : start())
  onMounted(() => { start(); document.addEventListener('visibilitychange', onVis) })
  onBeforeUnmount(() => { stop(); document.removeEventListener('visibilitychange', onVis) })
  return { restart: start, stop }
}
