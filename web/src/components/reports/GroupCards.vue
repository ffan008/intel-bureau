<script setup lang="ts">
/** 分群摘要：活跃群各一张卡（一句话总结、三件事、各项计数） */
import type { GroupDigestDTO } from '@/api/types'
import { fmtInt } from '@/utils/format'
import { platformColor, platformLabel } from '@/utils/meta'

defineProps<{ groups: GroupDigestDTO[] }>()
const COUNTS: { k: keyof GroupDigestDTO['counts']; label: string }[] = [
  { k: 'links', label: '链接' }, { k: 'prompts', label: '提示词' }, { k: 'sops', label: 'SOP' }, { k: 'data', label: '数据' },
]
</script>

<template>
  <div class="gc">
    <article v-for="g in groups" :key="g.group_key" class="card" :style="{ '--pc': platformColor(g.platform) }">
      <header>
        <i class="pdot" />
        <b class="nm">{{ g.group_name }}</b>
        <span class="pl">{{ platformLabel(g.platform) }}</span>
        <span class="spacer" />
        <span class="msgs"><b class="num">{{ fmtInt(g.messages) }}</b> 条消息</span>
      </header>
      <p class="sum">{{ g.summary }}</p>
      <ol v-if="g.highlights.length" class="hl">
        <li v-for="(h, i) in g.highlights.slice(0, 3)" :key="i">{{ h }}</li>
      </ol>
      <footer>
        <span v-for="c in COUNTS" :key="c.k" :class="{ zero: !g.counts?.[c.k] }">{{ c.label }} <b class="num">{{ g.counts?.[c.k] ?? 0 }}</b></span>
      </footer>
    </article>
  </div>
</template>

<style scoped>
.gc { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 14px; max-width: 1180px; }
.card { display: flex; flex-direction: column; gap: 10px; padding: 14px 16px; border: 1px solid var(--line); border-left: 2px solid var(--pc); background: rgba(10, 22, 46, 0.5); min-width: 0; }
header { display: flex; align-items: center; gap: 8px; min-width: 0; }
.pdot { width: 8px; height: 8px; border-radius: 50%; background: var(--pc); box-shadow: 0 0 6px var(--pc); flex: none; }
.nm { font-size: 15.5px; color: var(--text-0); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.pl { font-size: 12px; color: var(--text-2); flex: none; }
.msgs { font-size: 12px; color: var(--text-2); white-space: nowrap; }
.msgs b { color: var(--text-0); font-size: 13px; }
.sum { margin: 0; font-size: 14.5px; line-height: 1.75; color: var(--text-0); }
.hl { margin: 0; padding-left: 20px; font-size: 14px; line-height: 1.7; color: var(--text-1); }
.hl li { margin: 3px 0; }
.hl li::marker { color: var(--pc); font-family: var(--font-num); }
footer { display: flex; gap: 16px; margin-top: auto; padding-top: 10px; border-top: 1px solid rgba(80, 200, 255, 0.08); font-size: 12.5px; color: var(--text-2); }
footer b { color: var(--text-0); margin-left: 3px; }
footer .zero b { color: var(--text-2); }
</style>
