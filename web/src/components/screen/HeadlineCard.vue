<script setup lang="ts">
import { computed } from 'vue'
import type { IntelItemDTO } from '@/api/types'
import { useDecode } from '@/composables/useTextFx'
import { TREND, categoryColor, categoryName, platformColor } from '@/utils/meta'
import { isSevereRisk } from '@/utils/risk'
import ScoreBars from '../ui/ScoreBars.vue'

const props = defineProps<{ item: IntelItemDTO }>()
defineEmits<{ open: [] }>()
const title = useDecode(() => props.item.title, 600)
const col = computed(() => categoryColor(props.item.category))
</script>

<template>
  <button class="hc" :style="{ '--cc': col }" :aria-label="`查看情报：${item.title}`" @click="$emit('open')">
    <span class="cbar" aria-hidden="true" />
    <div class="main">
      <div class="tags">
        <span class="rank num">#{{ item.rank }}</span>
        <span class="cat">{{ categoryName(item.category) }}</span>
        <span class="badge grey">{{ item.kind }}</span>
        <span class="badge disp" :class="TREND[item.trend].cls">{{ TREND[item.trend].label }}</span>
        <span v-for="r in item.risk_flags" :key="r" class="badge risk" :class="isSevereRisk(r) ? 'red' : 'amber'">{{ r }}</span>
      </div>
      <h3 class="ttl" :title="item.title">{{ title }}</h3>
      <p class="hook">{{ item.hook }}</p>
      <div class="src">
        <span v-for="s in item.sources.slice(0, 3)" :key="s.group_key" class="chip"><i class="pdot" :style="{ background: platformColor(s.platform) }" />{{ s.group_name }}<b class="num">{{ s.count }}</b></span>
        <span class="who">{{ item.participants.slice(0, 3).join(' · ') }}</span>
      </div>
    </div>
    <div class="side">
      <div class="score"><b class="num">{{ item.score.toFixed(1) }}</b><span>综合分</span></div>
      <ScoreBars :scores="item.scores" :color="col" compact />
    </div>
  </button>
</template>

<style scoped>
.hc {
  position: relative;
  display: grid;
  grid-template-columns: 1fr 188px;
  gap: 18px;
  width: 100%;
  height: 100%;
  padding: 10px 16px 10px 20px;
  text-align: left;
  background: linear-gradient(100deg, color-mix(in srgb, var(--cc) 12%, transparent), rgba(4, 12, 28, 0.4) 46%);
  border: 1px solid rgba(80, 200, 255, 0.12);
  cursor: pointer;
}
.hc:hover { border-color: color-mix(in srgb, var(--cc) 55%, transparent); }
.cbar { position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--cc); box-shadow: 0 0 12px var(--cc); }
.main { min-width: 0; display: flex; flex-direction: column; gap: 5px; }
.tags { display: flex; align-items: center; gap: 6px; flex-wrap: nowrap; overflow: hidden; }
.rank { font-size: 12px; color: var(--cc); font-weight: 600; }
.cat { font-size: 12px; color: var(--cc); margin-right: 2px; }
.risk { border-style: solid; background: transparent; }
.ttl { margin: 0; font-size: 18px; font-weight: 700; line-height: 1.35; color: var(--text-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-shadow: 0 0 14px color-mix(in srgb, var(--cc) 30%, transparent); }
.hook { margin: 0; font-size: 13px; color: var(--text-1); line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.src { display: flex; align-items: center; gap: 6px; margin-top: auto; min-width: 0; }
.src .chip b { margin-left: 4px; color: var(--text-0); font-weight: 600; font-size: 10.5px; }
.who { font-size: 11px; color: var(--text-2); margin-left: 4px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.side { display: flex; flex-direction: column; justify-content: center; gap: 6px; padding-left: 16px; border-left: 1px solid rgba(80, 200, 255, 0.1); }
.score { display: flex; align-items: baseline; gap: 6px; }
.score b { font-size: 24px; font-weight: 600; color: var(--cc); line-height: 1; text-shadow: 0 0 12px var(--cc); }
.score span { font-size: 11px; color: var(--text-2); }
</style>
