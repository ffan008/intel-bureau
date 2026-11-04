<script setup lang="ts">
/** 提示词编辑器：v2 的 extract_v2 / article / digest / research_queries，以及 v1 的三个旧模板；等宽字体，带行号，保存前确认 */
import { computed, onMounted, ref } from 'vue'
import type { PromptDTO, PromptName } from '@/api/types'
import { api, normalizePrompts } from '@/api/endpoints'
import { notify } from '@/stores/toast'
import HudPanel from '../hud/HudPanel.vue'
import Icon from '../Icon.vue'
import { confirm } from '../ui/confirm'

const NAMES: { key: PromptName; label: string; desc: string }[] = [
  { key: 'extract_v2', label: '抽取 extract_v2', desc: '解码员对每个对话块调用，输出候选情报 JSON（含提示词、SOP、数据、金句、媒体引用）' },
  { key: 'article', label: '专题 article', desc: '主笔把一个话题写成专题知识文章（结构化 JSON，代码套模板）' },
  { key: 'digest', label: '分群 digest', desc: '为每个活跃群写一句话总结和三件事' },
  { key: 'research_queries', label: '检索词 research_queries', desc: '为每篇专题生成联网检索词（不得含群名、昵称、手机号）' },
  { key: 'extract', label: 'v1 extract', desc: 'v1 旧模板，v2 流水线不再使用；extract_v2 缺失时作为兜底' },
  { key: 'compose', label: 'v1 compose', desc: 'v1 旧模板，v2 流水线不再使用' },
  { key: 'merge', label: 'v1 merge', desc: '参谋判断两条候选是否为同一话题（可选）' },
]
const prompts = ref<PromptDTO[]>([])
const tab = ref<PromptName>('extract_v2')
const draft = ref<Record<string, string>>({})
const busy = ref(false)
const gutter = ref<HTMLElement | null>(null)

onMounted(async () => {
  try {
    prompts.value = normalizePrompts(await api.prompts())
    draft.value = Object.fromEntries(prompts.value.map((p) => [p.name, p.content]))
  } catch { /* toast */ }
})
const original = computed(() => prompts.value.find((p) => p.name === tab.value)?.content ?? '')
const text = computed({ get: () => draft.value[tab.value] ?? '', set: (v: string) => { draft.value = { ...draft.value, [tab.value]: v } } })
const dirty = computed(() => text.value !== original.value)
const lines = computed(() => Math.max(1, text.value.split('\n').length))
const hasGuard = computed(() => (tab.value !== 'extract' && tab.value !== 'extract_v2') || text.value.includes('chat_log'))

async function save(): Promise<void> {
  const n = NAMES.find((x) => x.key === tab.value)!
  const extra = hasGuard.value ? '' : '\n\n注意：新内容里没有出现 <chat_log>，提示词注入防护可能失效。'
  if (!await confirm({ title: '保存提示词', message: `确定用新内容覆盖「${n.label}」模板吗？${extra}`, detail: `${original.value.length} 字 → ${text.value.length} 字。下一次运行开始生效；extract 改动会使块缓存失效。`, okText: '保存' })) return
  busy.value = true
  try {
    const p = await api.savePrompt(tab.value, text.value)
    const i = prompts.value.findIndex((x) => x.name === p.name)
    if (i >= 0) prompts.value.splice(i, 1, p)
    notify.ok('提示词已保存')
  } catch { /* toast */ } finally { busy.value = false }
}
function revert(): void { text.value = original.value }
function sync(e: Event): void { if (gutter.value) gutter.value.scrollTop = (e.target as HTMLTextAreaElement).scrollTop }
</script>

<template>
  <HudPanel lite title="提示词模板" code="PROMPTS">
    <div class="pe">
      <div class="tabs">
        <button v-for="n in NAMES" :key="n.key" :class="{ on: tab === n.key }" @click="tab = n.key">
          {{ n.label }}<i v-if="(draft[n.key] ?? '') !== (prompts.find((p) => p.name === n.key)?.content ?? '')" class="mod">●</i>
        </button>
      </div>
      <p class="dim desc">{{ NAMES.find((n) => n.key === tab)?.desc }}</p>
      <div class="ed">
        <div ref="gutter" class="gut num" aria-hidden="true"><div v-for="i in lines" :key="i">{{ i }}</div></div>
        <textarea v-model="text" class="code" spellcheck="false" :aria-label="`${tab} 提示词`" @scroll="sync" />
      </div>
      <div v-if="!hasGuard" class="callout warn">extract 模板里没有 <code class="mono-inline">&lt;chat_log&gt;</code>：聊天内容应放在该标签里并声明「其中的指令只是数据」。</div>
      <div class="row">
        <span class="dim num">{{ text.length }} 字 · {{ lines }} 行</span>
        <span class="spacer" />
        <button class="btn" :disabled="!dirty" @click="revert"><Icon name="refresh" />撤销修改</button>
        <button class="btn primary" :disabled="!dirty || busy" @click="save"><Icon name="check" />{{ busy ? '保存中…' : '保存' }}</button>
      </div>
    </div>
  </HudPanel>
</template>

<style scoped>
.pe { display: flex; flex-direction: column; gap: 10px; }
.mod { font-style: normal; color: var(--amber); font-size: 9px; margin-left: 2px; }
.desc { margin: 2px 0 0; font-size: 12.5px; }
.ed { display: flex; height: 420px; border: 1px solid var(--line); background: rgba(0, 3, 9, 0.85); }
.ed:focus-within { border-color: var(--cyan); }
.gut { flex: none; width: 44px; padding: 10px 8px 10px 0; overflow: hidden; text-align: right; font-size: 12px; line-height: 20px; color: #2f5a74; border-right: 1px solid var(--line); user-select: none; }
.code { flex: 1; padding: 10px 12px; border: 0; outline: none; resize: none; background: transparent; color: #cfeaff; font-family: var(--font-num); font-size: 12.5px; line-height: 20px; white-space: pre; overflow: auto; tab-size: 2; }
</style>
