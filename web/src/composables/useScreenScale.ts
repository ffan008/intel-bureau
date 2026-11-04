import { onBeforeUnmount, onMounted, ref } from 'vue'

export const DESIGN_W = 1920
export const DESIGN_H = 1080

/** 大屏缩放：scale = min(innerWidth/1920, innerHeight/1080)，居中（UI_DESIGN §6） */
export const screenScale = ref(1)

export function useScreenScale() {
  const offsetX = ref(0)
  const offsetY = ref(0)
  let raf = 0
  const update = () => {
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(() => {
      const w = window.innerWidth
      const h = window.innerHeight
      const s = Math.min(w / DESIGN_W, h / DESIGN_H)
      screenScale.value = s
      offsetX.value = Math.round((w - DESIGN_W * s) / 2)
      offsetY.value = Math.round((h - DESIGN_H * s) / 2)
    })
  }
  onMounted(() => {
    update()
    window.addEventListener('resize', update, { passive: true })
  })
  onBeforeUnmount(() => {
    cancelAnimationFrame(raf)
    window.removeEventListener('resize', update)
  })
  return { scale: screenScale, offsetX, offsetY }
}
