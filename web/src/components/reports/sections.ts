/** 报告板块（V2_KNOWLEDGE §3.1）的展示元数据、计数与小工具 */
import { SECTION_KEYS, type ReportDTO, type ResourceKind, type SectionKey } from '@/api/types'
import { fmtShort } from '@/utils/format'

export const SECTION_META: Record<SectionKey, { title: string; code: string; empty: string; note?: string }> = {
  overview: { title: '今日总览', code: 'OVERVIEW', empty: '今天没有总览内容' },
  articles: { title: '专题文章', code: 'FEATURES', empty: '今天没有生成专题文章', note: '跨群合并后的话题，结合联网研究扩写；点开卡片阅读全文' },
  resources: { title: '资源库', code: 'RESOURCES', empty: '今天群里没有分享可收录的链接', note: '链接、提取码由程序从群消息原文照录' },
  prompts: { title: '提示词原文', code: 'PROMPTS', empty: '今天群里没有出现完整的提示词', note: '原文照录，一字不改' },
  sops: { title: '方法与 SOP', code: 'SOP', empty: '今天没有被验证过的做法', note: '群里有人实际验证过的做法' },
  tools: { title: '工具与模型', code: 'TOOLS', empty: '今天没有工具选型或实测结论', note: '谁、在什么场景、得出什么结论' },
  data: { title: '收益与数据', code: 'DATA', empty: '今天没有群友自述的数字', note: '群友自述，非平台口径' },
  risks: { title: '风险与踩坑', code: 'RISKS', empty: '今天没有风险条目' },
  quotes: { title: '金句与判断', code: 'QUOTES', empty: '今天没有收录金句', note: '群内原话' },
  media: { title: '图片与文档', code: 'MEDIA', empty: '今天没有提取到有用的图片或文档', note: '图片点开看大图与 OCR 要点；文档已读取正文并提炼' },
  groups: { title: '分群摘要', code: 'GROUPS', empty: '今天没有达到摘要门槛的群' },
  briefs: { title: '快讯与其余', code: 'BRIEFS', empty: '没有其余情报', note: '没有进专题的其余情报，每条一行' },
}

/** 板块 Markdown 开头若是与板块同名的标题，去掉（内容区已经有标题） */
export function stripLeadHeading(md: string, title: string): string {
  return md.replace(/^\s*#{1,2}\s+([^\n]*)\n?/, (m, t: string) => (t.includes(title) ? '' : m))
}

/** 时间：ISO → MM-DD HH:mm；后端给的不是 ISO 时原样显示 */
export function fmtAt(s?: string | null): string {
  if (!s) return ''
  return Number.isNaN(Date.parse(s)) ? s : fmtShort(s)
}

export interface SrcView { group: string; sender: string; at: string; platform: string }
/**
 * ArticleDTO.sources 按 §7 是对象数组；contracts.ArticleBrief.sources 是「微信·水彩手绘研习社 · 发言人 · 10-29 09:50」字符串。
 * 两种都兼容，渲染时不出错。
 */
export function normSources(xs: unknown): SrcView[] {
  if (!Array.isArray(xs)) return []
  return xs.map((s): SrcView => {
    if (typeof s === 'string') {
      const p = s.split(/\s+·\s+/)
      return { group: p[0] ?? s, sender: p[1] ?? '', at: p.slice(2).join(' · '), platform: '' }
    }
    const o = (s ?? {}) as Record<string, unknown>
    return { group: String(o.group_name ?? ''), sender: String(o.sender ?? ''), at: String(o.sent_at ?? ''), platform: String(o.platform ?? '') }
  })
}
export function srcSummary(xs: unknown): string {
  const s = normSources(xs)
  const groups = [...new Set(s.map((x) => x.group).filter(Boolean))]
  const people = new Set(s.map((x) => x.sender).filter(Boolean)).size
  if (!groups.length) return ''
  return `${groups.slice(0, 2).join('、')}${groups.length > 2 ? ` 等 ${groups.length} 群` : ''}${people ? ` · ${people} 位群友` : ''}`
}
export const pad2 = (n: number): string => String(n).padStart(2, '0')

/** 资源库分组（§3.1：GitHub / X / 公众号 / 网盘 / 视频 / 文档 / 其它），web 与 other 合并为「其它」 */
export const RESOURCE_GROUPS: { key: string; title: string; kinds: ResourceKind[] }[] = [
  { key: 'github', title: 'GitHub', kinds: ['github'] },
  { key: 'x', title: 'X / 推特', kinds: ['x'] },
  { key: 'wechat_article', title: '公众号', kinds: ['wechat_article'] },
  { key: 'netdisk', title: '网盘', kinds: ['netdisk'] },
  { key: 'video', title: '视频', kinds: ['video'] },
  { key: 'doc', title: '文档', kinds: ['doc'] },
  { key: 'other', title: '其它', kinds: ['web', 'other'] },
]

/** 有 v2 字段（板块或专题）才用板块阅读器，否则退回 v1 的 full_md 阅读器 */
export function isV2Report(r: ReportDTO | null | undefined): boolean {
  if (!r) return false
  return !!(r.articles?.length || (r.sections && Object.values(r.sections).some((v) => typeof v === 'string' && v.trim())))
}

/**
 * 每个板块的条目数：优先用后端的 section_counts；结构化板块退回数组长度；
 * 纯 Markdown 板块没有计数时返回 null（只显示有无，不猜数字）。
 */
export function sectionCounts(r: ReportDTO): Record<SectionKey, number | null> {
  const sc = r.section_counts ?? {}
  const arr: Partial<Record<SectionKey, number>> = {
    articles: r.articles?.length ?? 0, resources: r.resources?.length ?? 0, media: r.media?.length ?? 0, groups: r.groups?.length ?? 0,
  }
  const out = {} as Record<SectionKey, number | null>
  for (const k of SECTION_KEYS) {
    const v = sc[k]
    if (typeof v === 'number' && Number.isFinite(v)) out[k] = v
    else if (arr[k] !== undefined) out[k] = arr[k]!
    else out[k] = r.sections?.[k]?.trim() ? null : 0
  }
  return out
}

export const hasContent = (r: ReportDTO, k: SectionKey, n: number | null): boolean =>
  n === null ? true : n > 0 || !!r.sections?.[k]?.trim()
