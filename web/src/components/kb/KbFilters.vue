<script setup lang="ts">
/** 知识库检索：搜索框、分类筛选、标签云 */
import { computed } from 'vue'
import { categoryColor, categoryName } from '@/utils/meta'
import Icon from '../Icon.vue'

const props = defineProps<{ categories: { name: string; count: number }[]; tags: { name: string; count: number }[] }>()
const q = defineModel<string>('q', { required: true })
const category = defineModel<string>('category', { required: true })
const tag = defineModel<string>('tag', { required: true })

const all = computed(() => props.categories.reduce((a, c) => a + c.count, 0))
const cats = computed(() => [...props.categories].sort((a, b) => a.name.localeCompare(b.name, 'zh-CN')))
const cloud = computed(() => {
  const xs = [...props.tags].sort((a, b) => b.count - a.count).slice(0, 40)
  const max = Math.max(1, ...xs.map((t) => t.count)), min = Math.min(max, ...xs.map((t) => t.count))
  return xs.map((t) => ({ ...t, size: 12 + (max === min ? 1 : ((t.count - min) / (max - min)) * 5) }))
    .sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
})
</script>

<template>
  <div class="kf">
    <div class="search">
      <Icon name="search" :size="14" class="si" />
      <input v-model="q" class="input" placeholder="搜索标题、要点、正文" aria-label="搜索知识库" />
      <button v-if="q" class="clr" aria-label="清空搜索" @click="q = ''"><Icon name="close" :size="12" /></button>
    </div>

    <div class="blk">
      <div class="lbl">分类</div>
      <button class="cat" :class="{ on: !category }" @click="category = ''"><i style="background: var(--text-2)" /><span>全部</span><b class="num">{{ all }}</b></button>
      <button v-for="c in cats" :key="c.name" class="cat" :class="{ on: category === c.name }" :style="{ '--cc': categoryColor(c.name) }"
        @click="category = category === c.name ? '' : c.name">
        <i /><span>{{ categoryName(c.name) }}</span><b class="num">{{ c.count }}</b>
      </button>
    </div>

    <div v-if="cloud.length" class="blk">
      <div class="lbl">标签<button v-if="tag" class="x" @click="tag = ''">清除「{{ tag }}」</button></div>
      <div class="cloud">
        <button v-for="t in cloud" :key="t.name" class="tg" :class="{ on: tag === t.name }" :style="{ fontSize: t.size + 'px' }" :title="`${t.count} 条`"
          @click="tag = tag === t.name ? '' : t.name">{{ t.name }}</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.kf { display: flex; flex-direction: column; gap: 18px; height: 100%; overflow-y: auto; padding-right: 2px; }
.search { position: relative; }
.search .input { padding-left: 30px; padding-right: 28px; }
.si { position: absolute; left: 10px; top: 9px; color: var(--text-2); }
.clr { position: absolute; right: 8px; top: 9px; color: var(--text-2); }
.clr:hover { color: var(--text-0); }
.lbl { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12px; color: var(--text-2); }
.lbl .x { margin-left: auto; font-size: 12px; color: var(--cyan); }
.cat { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 8px; width: 100%; height: 32px; padding: 0 10px; font-size: 13.5px; color: var(--text-1); text-align: left; border-radius: 2px; }
.cat i { width: 7px; height: 7px; background: var(--cc, var(--text-2)); }
.cat b { font-size: 12px; color: var(--text-2); font-weight: 400; }
.cat:hover { background: rgba(34, 228, 255, 0.05); color: var(--text-0); }
.cat.on { background: rgba(34, 228, 255, 0.1); color: var(--text-0); box-shadow: inset 2px 0 0 var(--cc, var(--cyan)); }
.cloud { display: flex; flex-wrap: wrap; gap: 4px 10px; align-items: baseline; line-height: 1.6; }
.tg { color: var(--text-1); padding: 0 2px; }
.tg:hover { color: var(--cyan); }
.tg.on { color: var(--bg-0); background: var(--cyan); border-radius: 2px; padding: 0 6px; }
</style>
