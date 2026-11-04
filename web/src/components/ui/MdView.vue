<script setup lang="ts">
/**
 * 正文视图：v-html 渲染 utils/mdEnhance 产出的 HTML（已经 DOMPurify 消毒），并用事件委托处理正文里的交互：
 * 代码块「复制」、长内容折叠、引用编号跳到参考列表、站内锚点（#article-3 等，交给父组件）。
 * 站内锚点一律 preventDefault，不改地址栏的 hash，避免触发路由滚动。
 */
import { ref } from 'vue'
import { copyText } from '@/utils/clipboard'

withDefaults(defineProps<{ html: string; read?: boolean }>(), { read: true })
const emit = defineEmits<{ anchor: [hash: string] }>()
const el = ref<HTMLElement | null>(null)

const behavior = (): ScrollBehavior =>
  (matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.dataset.fx === 'off' ? 'auto' : 'smooth')

function flashBtn(btn: HTMLElement, ok: boolean): void {
  btn.textContent = ok ? '已复制' : '复制失败'
  btn.classList.toggle('done', ok)
  setTimeout(() => { btn.textContent = '复制'; btn.classList.remove('done') }, 1400)
}

async function onClick(e: MouseEvent): Promise<void> {
  const t = e.target as HTMLElement | null
  if (!t) return
  const act = t.closest<HTMLElement>('[data-act]')
  if (act?.dataset.act === 'copy') {
    const pre = act.closest('.md-code')?.querySelector('pre')
    flashBtn(act, await copyText(pre?.textContent ?? ''))
    return
  }
  if (act?.dataset.act === 'fold') {
    const box = act.closest<HTMLElement>('.md-fold')
    if (!box) return
    const open = box.dataset.open !== '1'
    box.dataset.open = open ? '1' : '0'
    act.textContent = open ? '收起' : act.dataset.label ?? '展开'
    if (!open) box.scrollIntoView({ block: 'nearest' })
    return
  }
  const a = t.closest<HTMLAnchorElement>('a[href^="#"]')
  if (!a) return
  e.preventDefault()
  const hash = (a.getAttribute('href') ?? '').slice(1)
  const ref = /^ref-(\d+)$/.exec(hash)
  if (ref) {
    const li = el.value?.querySelector<HTMLElement>(`[data-ref-target="${ref[1]}"]`)
    if (!li) return
    li.scrollIntoView({ behavior: behavior(), block: 'center' })
    li.classList.remove('flash')
    void li.offsetWidth
    li.classList.add('flash')
    return
  }
  emit('anchor', decodeURIComponent(hash))
}

function scrollToHeading(i: number): void {
  el.value?.querySelector<HTMLElement>(`[data-toc="${i}"]`)?.scrollIntoView({ behavior: behavior(), block: 'start' })
}
defineExpose({ el, scrollToHeading })
</script>

<template>
  <div ref="el" class="md" :class="{ read }" @click="onClick" v-html="html" />
</template>
