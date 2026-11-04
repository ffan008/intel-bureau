<script setup lang="ts">
/** 单条情报详情：摘要、步骤、证据原文（引用块，发言人与时间）、上下文、链接。大屏抽屉与情报档案共用。 */
import { computed, ref, watch } from 'vue'
import type { ContextMsg, IntelItemDTO, IntelItemDetail } from '@/api/types'
import { api } from '@/api/endpoints'
import { TREND, categoryColor, categoryName, platformColor, platformLabel } from '@/utils/meta'
import { fmtShort } from '@/utils/format'
import { safeUrl } from '@/utils/markdown'
import ScoreBars from '../ui/ScoreBars.vue'
import RiskBadge from '../ui/RiskBadge.vue'
import Icon from '../Icon.vue'

const props = defineProps<{ item: IntelItemDTO }>()
const detail = ref<IntelItemDetail | null>(null)
const showCtx = ref(false)
const col = computed(() => categoryColor(props.item.category))
const links = computed(() => props.item.links.map((l) => ({ ...l, safe: safeUrl(l.url) })))

watch(() => props.item.id, async (id) => {
  detail.value = null
  showCtx.value = false
  try { detail.value = await api.item(id) } catch { /* 上下文是可选信息 */ }
}, { immediate: true })

const msgText = (m: ContextMsg) => m.text ?? m.quote ?? ''
const msgWho = (m: ContextMsg) => m.sender ?? m.sender_name ?? '—'
</script>

<template>
  <article class="intel" :style="{ '--cc': col }">
    <div class="tags">
      <span class="cat"><i />{{ categoryName(item.category) }}</span>
      <span class="badge grey">{{ item.kind }}</span>
      <span class="badge disp" :class="TREND[item.trend].cls">{{ TREND[item.trend].label }}</span>
      <RiskBadge :flags="item.risk_flags" />
      <span class="spacer" />
      <span class="rank num">#{{ item.rank }}</span>
    </div>
    <h2 class="ttl">{{ item.title }}</h2>
    <p class="hook">{{ item.hook }}</p>

    <div class="scorebox">
      <div class="big"><b class="num">{{ item.score.toFixed(1) }}</b><span>综合评分</span></div>
      <ScoreBars :scores="item.scores" :color="col" />
    </div>

    <section>
      <h4 class="sec-title">摘要<span class="en">SUMMARY</span></h4>
      <p class="sum">{{ item.summary }}</p>
    </section>

    <section v-if="item.steps.length">
      <h4 class="sec-title">关键做法<span class="en">STEPS</span></h4>
      <ol class="steps">
        <li v-for="(s, i) in item.steps" :key="i"><span class="num">{{ String(i + 1).padStart(2, '0') }}</span>{{ s }}</li>
      </ol>
    </section>

    <section>
      <h4 class="sec-title">证据原文<span class="en">EVIDENCE · {{ item.evidence.length }}</span>
        <span class="spacer" />
        <button v-if="detail?.context" class="btn sm ghost" @click="showCtx = !showCtx">{{ showCtx ? '收起上下文' : '查看上下文' }}</button>
      </h4>
      <template v-if="showCtx && detail?.context">
        <div v-for="m in detail.context.before" :key="'b' + (m.message_id ?? m.sent_at)" class="ctx"><span class="w">{{ msgWho(m) }}</span><span class="t num">{{ fmtShort(m.sent_at) }}</span>{{ msgText(m) }}</div>
      </template>
      <blockquote v-for="e in item.evidence" :key="e.message_id" class="ev">
        <p>{{ e.quote }}</p>
        <footer>
          <i class="pdot" :style="{ background: platformColor(e.platform) }" />
          <b>{{ e.sender }}</b><span>{{ platformLabel(e.platform) }}「{{ e.group_name }}」</span>
          <span class="num">{{ fmtShort(e.sent_at) }}</span><span class="mid num">{{ e.message_id }}</span>
        </footer>
      </blockquote>
      <template v-if="showCtx && detail?.context">
        <div v-for="m in detail.context.after" :key="'a' + (m.message_id ?? m.sent_at)" class="ctx"><span class="w">{{ msgWho(m) }}</span><span class="t num">{{ fmtShort(m.sent_at) }}</span>{{ msgText(m) }}</div>
      </template>
    </section>

    <section v-if="links.length">
      <h4 class="sec-title">资源链接<span class="en">LINKS</span></h4>
      <ul class="links">
        <li v-for="l in links" :key="l.url">
          <a v-if="l.safe" :href="l.safe" target="_blank" rel="noopener noreferrer"><Icon name="external" :size="13" />{{ l.title || l.safe }}</a>
          <span v-else class="blocked" title="只允许打开 http/https 链接"><Icon name="lock" :size="13" />{{ l.title || '链接' }}（已拦截非 http/https 链接）</span>
          <span class="u num">{{ l.safe ?? l.url }}</span>
        </li>
      </ul>
    </section>

    <section class="meta">
      <div><span class="k">来源</span>
        <span v-for="s in item.sources" :key="s.group_key" class="chip"><i class="pdot" :style="{ background: platformColor(s.platform) }" />{{ s.group_name }} · {{ s.count }}</span>
      </div>
      <div v-if="item.tools.length"><span class="k">工具</span><span v-for="t in item.tools" :key="t" class="chip">{{ t }}</span></div>
      <div v-if="item.participants.length"><span class="k">参与</span><span class="v">{{ item.participants.join('、') }}</span></div>
      <div v-if="item.tags.length"><span class="k">标签</span><span v-for="t in item.tags" :key="t" class="chip">#{{ t }}</span></div>
    </section>
  </article>
</template>

<style scoped>
.intel { display: flex; flex-direction: column; gap: 18px; }
.tags { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.cat { display: inline-flex; align-items: center; gap: 6px; font-size: 12.5px; color: var(--cc); }
.cat i { width: 8px; height: 8px; background: var(--cc); box-shadow: 0 0 8px var(--cc); }
.spacer { flex: 1; }
.rank { color: var(--text-2); font-size: 12px; }
.ttl { margin: -8px 0 0; font-size: 20px; line-height: 1.45; font-weight: 700; }
.hook { margin: -10px 0 0; font-size: 14px; line-height: 1.7; color: var(--text-1); }
.scorebox { display: grid; grid-template-columns: 110px 1fr; gap: 18px; align-items: center; padding: 12px 14px; background: rgba(4, 12, 28, 0.55); border: 1px solid var(--line); }
.big { display: flex; flex-direction: column; }
.big b { font-size: 34px; color: var(--cc); line-height: 1; font-weight: 600; text-shadow: 0 0 16px var(--cc); }
.big span { font-size: 11.5px; color: var(--text-2); margin-top: 4px; }
section .sec-title { margin-bottom: 10px; }
.sum { margin: 0; font-size: 13.5px; line-height: 1.85; color: var(--text-1); }
.steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.steps li { display: flex; gap: 10px; font-size: 13.5px; line-height: 1.7; color: var(--text-0); }
.steps li span { flex: none; color: var(--cc); font-size: 12px; margin-top: 2px; }
.ev { margin: 0 0 10px; padding: 10px 14px; border-left: 2px solid var(--cc); background: linear-gradient(90deg, color-mix(in srgb, var(--cc) 8%, transparent), rgba(4, 12, 28, 0.4)); }
.ev p { margin: 0 0 6px; font-size: 14px; line-height: 1.75; color: var(--text-0); }
.ev p::before { content: '“'; color: var(--cc); margin-right: 2px; }
.ev p::after { content: '”'; color: var(--cc); margin-left: 2px; }
.ev footer { display: flex; align-items: center; gap: 8px; font-size: 11.5px; color: var(--text-2); flex-wrap: wrap; }
.ev footer b { color: var(--text-1); font-weight: 600; }
.ev .pdot { width: 6px; height: 6px; border-radius: 50%; }
.ev .mid { margin-left: auto; opacity: 0.6; }
.ctx { display: flex; gap: 8px; padding: 4px 14px; font-size: 12.5px; color: var(--text-2); }
.ctx .w { color: var(--text-1); flex: none; }
.ctx .t { flex: none; font-size: 11px; }
.links { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 8px; }
.links li { display: flex; flex-direction: column; gap: 2px; }
.links a, .blocked { display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; }
.blocked { color: var(--amber); }
.u { font-size: 11px; color: var(--text-2); word-break: break-all; padding-left: 19px; }
.meta { display: flex; flex-direction: column; gap: 8px; padding-top: 12px; border-top: 1px solid var(--line); }
.meta > div { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.meta .k { width: 34px; font-size: 12px; color: var(--text-2); }
.meta .v { font-size: 12.5px; color: var(--text-1); }
</style>
