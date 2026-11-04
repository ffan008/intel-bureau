<script setup lang="ts">
/** 跑马灯（§4.9）：最新情报标题与投递回执，匀速滚动，悬停暂停，每条前加分类色点 */
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { live } from '@/stores/live'
import { categoryColor, categoryName } from '@/utils/meta'

interface Item { key: string; dot: string; tag?: string; text: string }

const items = computed<Item[]>(() => {
  const heads = live.overview?.headlines ?? []
  const fromOv = (live.overview?.ticker ?? []).map((t, i): Item => {
    const m = /^【([^】]+)】\s*(.*)$/.exec(t)
    if (m) return { key: `o${i}`, dot: categoryColor(m[1]), tag: categoryName(m[1]), text: m[2]! }
    if (/^\s*[✓✔]/.test(t)) return { key: `o${i}`, dot: '#2bff9a', text: t }
    if (/^\s*[✗✘]/.test(t)) return { key: `o${i}`, dot: '#ff4d5e', text: t }
    const h = heads.find((x) => t.includes(x.title))
    return { key: `o${i}`, dot: h ? categoryColor(h.category) : '#22e4ff', text: t }
  })
  const extra = live.tickerExtra.map((x): Item => ({ key: `x${x.id}`, dot: x.color, text: x.text }))
  return [...extra, ...fromOv]
})

const track = ref<HTMLElement | null>(null)
const dur = ref(60)
function measure(): void {
  const el = track.value?.firstElementChild as HTMLElement | null
  if (el) dur.value = Math.max(20, el.offsetWidth / 70)
}
watch(items, () => void nextTick(measure))
onMounted(() => { measure(); window.addEventListener('resize', measure) })
onBeforeUnmount(() => window.removeEventListener('resize', measure))
</script>

<template>
  <footer class="ticker" aria-label="最新情报">
    <div class="lbl"><i class="fx-loop" /><span class="disp">LIVE FEED</span></div>
    <div class="vp">
      <div ref="track" class="track fx-loop" :style="{ animationDuration: dur + 's' }">
        <div v-for="copy in 2" :key="copy" class="copy" :aria-hidden="copy === 2">
          <span v-for="it in items" :key="it.key" class="it">
            <i :style="{ background: it.dot, boxShadow: `0 0 6px ${it.dot}` }" />
            <em v-if="it.tag" :style="{ color: it.dot }">{{ it.tag }}</em>{{ it.text }}
          </span>
          <span v-if="!items.length" class="it dim">等待第一份情报……</span>
        </div>
      </div>
    </div>
  </footer>
</template>

<style scoped>
.ticker {
  position: relative;
  display: flex;
  align-items: center;
  height: 32px;
  background: linear-gradient(90deg, rgba(10, 24, 52, 0.85), rgba(6, 14, 32, 0.6));
  border-top: 1px solid var(--line);
  border-bottom: 1px solid var(--line);
  overflow: hidden;
}
.lbl { flex: none; display: flex; align-items: center; gap: 8px; height: 100%; padding: 0 16px; background: rgba(34, 228, 255, 0.1); border-right: 1px solid var(--line-strong); clip-path: polygon(0 0, 100% 0, calc(100% - 10px) 100%, 0 100%); padding-right: 22px; }
.lbl i { width: 6px; height: 6px; border-radius: 50%; background: var(--red); box-shadow: 0 0 8px var(--red); animation: kf-blink 1.2s steps(1) infinite; }
.lbl .disp { font-size: 10px; letter-spacing: 3px; color: var(--cyan); }
.vp { flex: 1; min-width: 0; height: 100%; overflow: hidden; -webkit-mask-image: linear-gradient(90deg, transparent, #000 40px, #000 calc(100% - 40px), transparent); mask-image: linear-gradient(90deg, transparent, #000 40px, #000 calc(100% - 40px), transparent); }
.track { display: flex; width: max-content; height: 100%; animation: kf-ticker 60s linear infinite; will-change: transform; }
.vp:hover .track { animation-play-state: paused; }
.copy { display: flex; align-items: center; flex: none; }
.it { display: inline-flex; align-items: center; gap: 8px; padding: 0 28px 0 0; font-size: 13px; color: var(--text-1); white-space: nowrap; }
.it i { width: 6px; height: 6px; border-radius: 50%; flex: none; }
.it em { font-style: normal; font-size: 11.5px; opacity: 0.9; }
.it.dim { color: var(--text-2); }
</style>
