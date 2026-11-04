/**
 * 目录高亮：观察正文里带 data-toc 的标题，取进入滚动容器上方 35% 区域的第一个；
 * 区域里没有标题时，取最后一个已经滚过顶部的。滚动容器是最近的 .scroller（没有就用视口）。
 */
import { onBeforeUnmount, ref } from 'vue'

export function useTocSpy(container: () => HTMLElement | null | undefined) {
  const active = ref(0)
  let io: IntersectionObserver | null = null
  const visible = new Set<number>()

  function stop(): void {
    io?.disconnect()
    io = null
    visible.clear()
  }
  function start(): void {
    stop()
    active.value = 0
    const root = container()
    if (!root || typeof IntersectionObserver === 'undefined') return
    const scroller = root.closest<HTMLElement>('.scroller')
    const heads = [...root.querySelectorAll<HTMLElement>('[data-toc]')]
    if (!heads.length) return
    io = new IntersectionObserver((entries) => {
      for (const en of entries) {
        const i = Number((en.target as HTMLElement).dataset.toc)
        if (en.isIntersecting) visible.add(i)
        else visible.delete(i)
      }
      if (visible.size) { active.value = Math.min(...visible); return }
      const top = scroller?.getBoundingClientRect().top ?? 0
      let cur = 0
      for (const h of heads) if (h.getBoundingClientRect().top - top < 90) cur = Number(h.dataset.toc)
      active.value = cur
    }, { root: scroller, rootMargin: '0px 0px -65% 0px', threshold: 0 })
    heads.forEach((h) => io!.observe(h))
  }
  onBeforeUnmount(stop)
  return { active, start, stop }
}
