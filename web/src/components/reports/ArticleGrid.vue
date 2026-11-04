<script setup lang="ts">
/** 专题卡片网格：序号、标题、一句话、分类、风险徽标、来源；点开进阅读视图 */
import type { ArticleDTO } from '@/api/types'
import { categoryColor, categoryName } from '@/utils/meta'
import RiskBadge from '../ui/RiskBadge.vue'
import { pad2, srcSummary } from './sections'

defineProps<{ articles: ArticleDTO[] }>()
const emit = defineEmits<{ open: [seq: number] }>()
</script>

<template>
  <div class="grid">
    <button v-for="a in articles" :key="a.id" class="ac" :style="{ '--cc': categoryColor(a.category) }" @click="emit('open', a.seq)">
      <div class="top">
        <span class="sq num">{{ pad2(a.seq) }}</span>
        <span class="cat">{{ categoryName(a.category) }}</span>
        <span v-if="a.images.length" class="img" :title="`${a.images.length} 张配图`">图 {{ a.images.length }}</span>
      </div>
      <h4 class="tt">{{ a.title }}</h4>
      <p class="hk">{{ a.hook }}</p>
      <div class="ft">
        <span class="src ellipsis">{{ srcSummary(a.sources) }}</span>
        <RiskBadge :flags="a.risk_flags" :max="2" sm />
      </div>
    </button>
  </div>
</template>

<style scoped>
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.ac { display: flex; flex-direction: column; gap: 8px; min-width: 0; padding: 14px 16px 12px; text-align: left; border: 1px solid var(--line); border-top: 2px solid var(--cc);
  background: linear-gradient(170deg, color-mix(in srgb, var(--cc) 9%, transparent), rgba(10, 22, 46, 0.5) 55%); transition: border-color var(--t-fast), transform var(--t-fast) var(--ease-out); }
.ac:hover { border-color: color-mix(in srgb, var(--cc) 55%, transparent); transform: translateY(-1px); }
.ac:hover .tt { color: #fff; }
.top { display: flex; align-items: center; gap: 8px; }
.sq { font-size: 20px; font-weight: 600; color: var(--cc); line-height: 1; }
.cat { font-size: 12px; color: var(--cc); }
.img { margin-left: auto; font-size: 11.5px; color: var(--text-2); border: 1px solid var(--line); padding: 0 6px; border-radius: 2px; }
.tt { margin: 0; font-size: 16px; line-height: 1.5; color: var(--text-0); font-weight: 600; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.hk { margin: 0; font-size: 13.5px; line-height: 1.65; color: var(--text-1); display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.ft { display: flex; align-items: center; gap: 8px; margin-top: auto; padding-top: 8px; border-top: 1px solid rgba(80, 200, 255, 0.08); }
.src { flex: 1; min-width: 0; font-size: 12px; color: var(--text-2); }
</style>
