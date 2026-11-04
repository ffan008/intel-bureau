<script setup lang="ts">
/**
 * 资源库：按类型分组的表格（GitHub / X / 公众号 / 网盘 / 视频 / 文档 / 其它）。
 * 每行都有分享人、群、时间；网盘提取码旁有「复制」；链接只放行 http/https。
 */
import { computed, ref } from 'vue'
import type { ResourceDTO } from '@/api/types'
import { safeUrl } from '@/utils/markdown'
import { fmtCompact } from '@/utils/format'
import CopyButton from '../ui/CopyButton.vue'
import { RESOURCE_GROUPS, fmtAt } from './sections'

const props = defineProps<{ resources: ResourceDTO[] }>()
const groups = computed(() => RESOURCE_GROUPS.map((g) => ({ ...g, rows: props.resources.filter((r) => g.kinds.includes(r.kind)) }))
  .filter((g) => g.rows.length))
const root = ref<HTMLElement | null>(null)

const str = (r: ResourceDTO, ...keys: string[]): string => {
  for (const k of keys) {
    const v = r.meta?.[k]
    if (v !== undefined && v !== null && v !== '') return String(v)
  }
  return ''
}
const num = (r: ResourceDTO, k: string): string => {
  const v = Number(r.meta?.[k])
  return Number.isFinite(v) && r.meta?.[k] !== undefined && r.meta?.[k] !== null ? fmtCompact(v) : '—'
}
const desc = (r: ResourceDTO) => str(r, 'description', 'summary', 'text') || r.note || ''
const extraNote = (r: ResourceDTO) => (r.note && r.note !== desc(r) ? r.note : '')
const PROVIDER: Record<string, string> = { baidu: '百度网盘', quark: '夸克网盘', aliyun: '阿里云盘', alipan: '阿里云盘', '115': '115 网盘', lanzou: '蓝奏云', '123pan': '123 云盘', tianyi: '天翼云盘', xunlei: '迅雷云盘' }
const provider = (r: ResourceDTO) => { const p = str(r, 'provider'); return PROVIDER[p.toLowerCase()] ?? p }
const href = (r: ResourceDTO) => safeUrl(r.url)
const jump = (k: string) => root.value?.querySelector<HTMLElement>(`[data-g="${k}"]`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
</script>

<template>
  <div ref="root" class="rt">
    <div class="jumps">
      <button v-for="g in groups" :key="g.key" class="chip" @click="jump(g.key)">{{ g.title }} <b class="num">{{ g.rows.length }}</b></button>
    </div>

    <section v-for="g in groups" :key="g.key" class="grp" :data-g="g.key">
      <h4>{{ g.title }}<span class="num">{{ g.rows.length }}</span></h4>
      <div class="tw">
        <table class="tbl">
          <thead>
            <tr v-if="g.key === 'github'"><th>项目</th><th class="r">星数</th><th>语言</th><th>简介</th><th>分享</th></tr>
            <tr v-else-if="g.key === 'x'"><th>内容</th><th>作者</th><th class="r">点赞</th><th class="r">转发</th><th>分享</th></tr>
            <tr v-else-if="g.key === 'wechat_article'"><th>文章</th><th>作者</th><th class="r">字数</th><th>摘要</th><th>分享</th></tr>
            <tr v-else-if="g.key === 'netdisk'"><th>资料</th><th>平台</th><th>提取码</th><th>说明</th><th>分享</th></tr>
            <tr v-else><th>标题</th><th>说明</th><th>分享</th></tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in g.rows" :key="r.url + i">
              <td class="ttl">
                <a v-if="href(r)" :href="href(r)!" target="_blank" rel="noopener noreferrer">{{ r.title || r.url }}</a>
                <span v-else>{{ r.title || r.url }}</span>
                <span v-if="g.key === 'github' || g.key === 'x'" class="u num">{{ r.url.replace(/^https?:\/\/(www\.)?/, '') }}</span>
              </td>
              <template v-if="g.key === 'github'">
                <td class="r num st">★ {{ num(r, 'stars') }}</td>
                <td class="nw">{{ str(r, 'language') || '—' }}</td>
                <td class="ds">{{ desc(r) || '—' }}<em v-if="extraNote(r)">群友：{{ extraNote(r) }}</em></td>
              </template>
              <template v-else-if="g.key === 'x'">
                <td class="nw">{{ str(r, 'author') || '—' }}</td>
                <td class="r num">{{ num(r, 'likes') }}</td>
                <td class="r num">{{ num(r, 'retweets') }}</td>
              </template>
              <template v-else-if="g.key === 'wechat_article'">
                <td class="nw">{{ str(r, 'author') || '—' }}</td>
                <td class="r num">{{ num(r, 'words') }}</td>
                <td class="ds">{{ desc(r) || '—' }}</td>
              </template>
              <template v-else-if="g.key === 'netdisk'">
                <td class="nw">{{ provider(r) || '—' }}</td>
                <td class="nw">
                  <span v-if="r.code" class="code"><b class="num">{{ r.code }}</b><CopyButton :text="r.code" what="提取码" /></span>
                  <span v-else class="dim">无</span>
                </td>
                <td class="ds">{{ desc(r) || '—' }}</td>
              </template>
              <td v-else class="ds">{{ desc(r) || '—' }}</td>
              <td class="who">
                <span>{{ r.shared_by || '—' }}</span>
                <span v-if="r.group_name" class="dim">{{ r.group_name }}</span>
                <span v-if="r.sent_at" class="dim num">{{ fmtAt(r.sent_at) }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>
  </div>
</template>

<style scoped>
.rt { display: flex; flex-direction: column; gap: 26px; max-width: 1180px; }
.jumps { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: -6px; }
.jumps .chip { height: 26px; padding: 0 12px; font-size: 13px; border-radius: 13px; }
.jumps .chip b { color: var(--cyan); margin-left: 4px; }
.jumps .chip:hover { color: var(--text-0); border-color: var(--line-strong); }
.grp { scroll-margin-top: 12px; }
.grp h4 { display: flex; align-items: baseline; gap: 8px; margin: 0 0 8px; font-size: 16px; color: var(--text-0); }
.grp h4 .num { font-size: 13px; color: var(--text-2); font-weight: 400; }
.tw { border: 1px solid var(--line); overflow-x: auto; }
.tbl { font-size: 14px; line-height: 1.6; }
.tbl th { position: static; font-size: 12.5px; background: rgba(34, 228, 255, 0.05); }
.tbl td { padding: 10px; vertical-align: top; }
.ttl { min-width: 200px; max-width: 320px; }
.ttl a { color: var(--text-0); font-weight: 600; }
.ttl a:hover { color: var(--cyan); }
.ttl .u { display: block; margin-top: 2px; font-size: 11.5px; color: var(--text-2); word-break: break-all; }
.st { color: #f2c879; white-space: nowrap; }
.nw { white-space: nowrap; color: var(--text-1); }
.ds { color: var(--text-1); min-width: 220px; }
.ds em { display: block; margin-top: 4px; font-style: normal; font-size: 12.5px; color: var(--text-2); }
.code { display: inline-flex; align-items: center; gap: 8px; }
.code b { font-size: 15px; letter-spacing: 1px; color: var(--cyan); padding: 0 6px; border: 1px dashed rgba(34, 228, 255, 0.4); border-radius: 3px; }
.who { width: 190px; font-size: 13px; }
.who span { display: block; }
.who .dim { font-size: 12px; }
</style>
