/** v2 mock：给报告挂上 §7 的 v2 字段（sections / articles / resources / media / groups / section_counts），并按板块重写 full_md、按 §3.5 重写 summary_md */
import { SECTION_KEYS, type GroupDigestDTO, type ReportDTO, type ResourceDTO, type SectionKey } from '@/api/types'
import { DIGESTS, RESOURCES } from '../data/resourcesV2'
import { groupById, groupKey } from '../data/groups'
import { HOUR, iso } from '../util'
import { ARTICLE_SEEDS, ARTICLE_SPECS, buildArticle, pad2 } from './v2Articles'
import { buildMedia, imagesOf } from './v2Media'
import { buildSections } from './v2Sections'
import { seedIndexOfItem } from './items'

const TITLE: Record<SectionKey, string> = { overview: '今日总览', articles: '专题文章', resources: '资源库', prompts: '提示词原文', sops: '方法与 SOP',
  tools: '工具与模型', data: '收益与数据', risks: '风险与踩坑', quotes: '金句与判断', media: '图片与文档', groups: '分群摘要', briefs: '快讯与其余' }

export function attachV2(rep: ReportDTO, end: number): ReportDTO {
  const articles = ARTICLE_SPECS.map((s, i) => ({ ...buildArticle(s, i + 1, rep.items), images: imagesOf(i + 1) }))
  rep.items.forEach((it) => { it.is_feature = ARTICLE_SEEDS.has(seedIndexOfItem(it.id)) })
  const resources: ResourceDTO[] = RESOURCES.map((r, i) => ({ kind: r.kind, title: r.title, url: r.url, code: r.code, meta: r.meta ?? {}, note: r.note,
    shared_by: r.who, group_name: r.group, sent_at: iso(end - r.hoursAgo * HOUR - (i * 7 % 50) * 60_000) }))
  const groups: GroupDigestDTO[] = DIGESTS.map((d) => {
    const g = groupById(d.group)
    const st = rep.stats.top_groups.find((x) => x.name === g.name)
    return { group_key: groupKey(g), group_name: g.name, platform: g.platform, messages: st?.messages ?? g.m24, summary: d.summary, highlights: d.highlights,
      counts: { links: d.counts[0], prompts: d.counts[1], sops: d.counts[2], data: d.counts[3] } }
  })
  rep.articles = articles
  rep.resources = resources
  rep.media = buildMedia(articles)
  rep.groups = groups
  const { sections, counts } = buildSections(rep, rep.items, articles)
  rep.sections = sections
  rep.section_counts = { ...counts, articles: articles.length, resources: resources.length, media: rep.media.length, groups: groups.length }
  rep.full_md = fullMd(rep)
  rep.summary_md = summaryMd(rep)
  return rep
}

/** 导出用的完整 Markdown：按 12 个板块分节 */
function fullMd(r: ReportDTO): string {
  const L = [`# ${r.title}`, '', `> 窗口 ${r.window_label}｜情报 ${r.items_total} 条｜专题 ${r.articles!.length} 篇｜资源 ${r.resources!.length} 个`, '']
  for (const k of SECTION_KEYS) {
    L.push(`## ${TITLE[k]}`, '')
    if (k === 'articles') r.articles!.forEach((a) => L.push(a.body_md.replace(/^## /gm, '#### ').replace(/^# /, '### '), ''))
    else if (k === 'resources') r.resources!.forEach((x) => L.push(`- [${x.kind}] [${x.title}](${x.url})${x.code ? ` 提取码 \`${x.code}\`` : ''} · ${x.shared_by} · ${x.group_name}`))
    else if (k === 'media') r.media!.forEach((m) => L.push(`- ${m.kind === 'image' ? '图片' : '文档'} ${m.name}：${m.why ?? ''}（${m.group_name ?? ''} · ${m.sender ?? ''}）`))
    else if (k === 'groups') r.groups!.forEach((g) => L.push(`### ${g.group_name}`, '', g.summary, '', ...g.highlights.map((h, i) => `${i + 1}. ${h}`), ''))
    else L.push(r.sections?.[k] ?? '')
    L.push('')
  }
  return L.join('\n')
}

/** 推送摘要（§3.5，≤1800 字） */
function summaryMd(r: ReportDTO): string {
  const n = (k: string) => r.resources!.filter((x) => x.kind === k).length
  const risky = r.articles!.filter((a) => a.risk_flags.length).length + r.items.filter((i) => i.risk_flags.includes('违法高危')).length
  return [`今日全部群风向标（${r.date_label}）已更新！`, '', `📌 今日 ${r.articles!.length} 篇深度实操拆解：`,
    ...r.articles!.map((a) => `${pad2(a.seq)}. ${a.title}`), '',
    `🔥 外部精选资源：🐙 GitHub ${n('github')} 项 · 🐦 X ${n('x')} 条 · 📑 公众号 ${n('wechat_article')} 篇 · 💾 网盘 ${n('netdisk')} 套`,
    `⚠️ ${risky} 条带风险提示（详见风险板块）`, `👉 今日风向标直达：http://127.0.0.1:8765/reports?id=${r.id}`, '👉 知识库目录：http://127.0.0.1:8765/kb',
  ].join('\n').slice(0, 1800)
}
