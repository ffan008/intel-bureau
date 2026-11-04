<script setup lang="ts">
/** 小号「复制」按钮：复制成功后 1.4 秒内显示「已复制」 */
import { onBeforeUnmount, ref } from 'vue'
import { copyText } from '@/utils/clipboard'
import { notify } from '@/stores/toast'

const props = withDefaults(defineProps<{ text: string; label?: string; what?: string }>(), { label: '复制' })
const done = ref(false)
let tm: ReturnType<typeof setTimeout> | null = null
async function go(): Promise<void> {
  if (!await copyText(props.text)) { notify.warn('复制失败', { detail: '浏览器拒绝访问剪贴板，请手动选中后复制' }); return }
  done.value = true
  if (tm) clearTimeout(tm)
  tm = setTimeout(() => { done.value = false }, 1400)
}
onBeforeUnmount(() => { if (tm) clearTimeout(tm) })
</script>

<template>
  <button type="button" class="cpb" :class="{ done }" :aria-label="`复制${what ?? ''}`" @click.stop="go">{{ done ? '已复制' : label }}</button>
</template>

<style scoped>
.cpb { height: 22px; padding: 0 9px; font-size: 12px; line-height: 20px; color: var(--text-1); border: 1px solid var(--line-strong); border-radius: 3px; background: rgba(34, 228, 255, 0.06); white-space: nowrap; }
.cpb:hover { color: var(--cyan); border-color: var(--cyan); }
.cpb.done { color: var(--green); border-color: rgba(43, 255, 154, 0.5); }
</style>
