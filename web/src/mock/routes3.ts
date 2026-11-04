/** mock 路由（三）：v2 知识库 GET /kb、GET /kb/{id}（V2_KNOWLEDGE §7） */
import type { KbArticleDTO, KbSummaryDTO } from '@/api/types'
import { S } from './state'
import { clone, err, ok, type Route } from './routes'

const summary = (a: KbArticleDTO): KbSummaryDTO => ({ id: a.id, title: a.title, category: a.category, tags: a.tags, hook: a.hook, risk_flags: a.risk_flags,
  updated_at: a.updated_at, created_at: a.created_at, versions: a.versions.length, sources: a.sources.length })
const facet = (xs: string[]) => [...xs.reduce((m, x) => m.set(x, (m.get(x) ?? 0) + 1), new Map<string, number>())].map(([name, count]) => ({ name, count }))

export const ROUTES_C: Route[] = [
  ['GET', /^\/kb$/, ({ q }) => {
    const kw = q.get('q')?.trim().toLowerCase(), cat = q.get('category') || '', tag = q.get('tag') || ''
    const hit = (a: KbArticleDTO) => !kw || `${a.title} ${a.hook} ${a.tags.join(' ')} ${a.body_md}`.toLowerCase().includes(kw)
    const base = S.kb.filter(hit)
    const xs = base.filter((a) => (!cat || a.category === cat) && (!tag || a.tags.includes(tag))).sort((a, b) => b.updated_at.localeCompare(a.updated_at))
    const off = Number(q.get('offset') ?? 0), lim = Number(q.get('limit') ?? 30)
    return ok({ items: xs.slice(off, off + lim).map(summary), total: xs.length,
      categories: facet(base.filter((a) => !tag || a.tags.includes(tag)).map((a) => a.category)),
      tags: facet(base.filter((a) => !cat || a.category === cat).flatMap((a) => a.tags)) })
  }],
  ['GET', /^\/kb\/([\w-]+)$/, ({ m }) => {
    const a = S.kb.find((x) => x.id === m[1])
    return a ? ok(clone(a)) : err(404, 'not_found', '知识库条目不存在')
  }],
]
