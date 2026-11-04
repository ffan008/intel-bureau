/** 接口表（docs/API.md「接口」一节）的一一对应封装 */
import { currentToken, download, request, type RequestOptions } from './client'
import type {
  ChannelDTO, ChannelInput, ChannelKindDTO, DeliverResult, DemoSeedResult, DoctorCheck, ExportFormat,
  GroupBulkResult, GroupDTO, GroupPatch, GroupQuery, HealthDTO, ImportResult, IntelItemDetail, KbArticleDTO, KbListDTO, KbQuery, LlmTestResult,
  LogDTO, LogQuery, OkDTO, OverviewDTO, Paged, Platform, PlatformDTO, PlatformUpdate, PromptDTO, PromptName,
  RefreshGroupsResult, ReportDTO, ReportSummaryDTO, RunCreate, RunDTO, ScheduleDTO, ScheduleInput, SessionDTO,
  SettingsDTO, SettingsPatch, TestResult,
} from './types'

const enc = encodeURIComponent
type O = Pick<RequestOptions, 'silent' | 'signal'>

export const api = {
  session: () => request<SessionDTO>('GET', '/session', { auth: false }),
  health: (o?: O) => request<HealthDTO>('GET', '/health', { auth: false, ...o }),
  overview: (o?: O) => request<OverviewDTO>('GET', '/overview', o),

  platforms: () => request<PlatformDTO[]>('GET', '/platforms'),
  updatePlatform: (p: Platform, body: PlatformUpdate) => request<PlatformDTO>('PUT', `/platforms/${p}`, { body }),
  testPlatform: (p: Platform) => request<PlatformDTO>('POST', `/platforms/${p}/test`, { timeoutMs: 20000 }),
  refreshGroups: (p: Platform) => request<RefreshGroupsResult>('POST', `/platforms/${p}/refresh-groups`, { timeoutMs: 60000 }),

  groups: (q: GroupQuery = {}) => request<Paged<GroupDTO>>('GET', '/groups', { query: { ...q } }),
  patchGroup: (key: string, body: GroupPatch) => request<GroupDTO>('PATCH', `/groups/${enc(key)}`, { body }),
  bulkGroups: (keys: string[], whitelisted: boolean) =>
    request<GroupBulkResult>('POST', '/groups/bulk', { body: { keys, whitelisted } }),
  importChat: (form: FormData) => request<ImportResult>('POST', '/import', { form, timeoutMs: 120000 }),

  schedules: () => request<ScheduleDTO[]>('GET', '/schedules'),
  createSchedule: (body: ScheduleInput) => request<ScheduleDTO>('POST', '/schedules', { body }),
  updateSchedule: (id: string, body: ScheduleInput) => request<ScheduleDTO>('PUT', `/schedules/${enc(id)}`, { body }),
  deleteSchedule: (id: string) => request<OkDTO>('DELETE', `/schedules/${enc(id)}`),
  runSchedule: (id: string, dry_run?: boolean) =>
    request<RunDTO>('POST', `/schedules/${enc(id)}/run`, { body: dry_run === undefined ? {} : { dry_run } }),

  createRun: (body: RunCreate, o?: O) => request<RunDTO>('POST', '/runs', { body, ...o }),
  runs: (limit = 20, offset?: number) => request<Paged<RunDTO>>('GET', '/runs', { query: { limit, offset } }),
  run: (id: string, o?: O) => request<RunDTO>('GET', `/runs/${enc(id)}`, o),
  cancelRun: (id: string) => request<RunDTO>('POST', `/runs/${enc(id)}/cancel`),
  runLogs: (id: string, o?: O) => request<LogDTO[]>('GET', `/runs/${enc(id)}/logs`, o),

  reports: (q: { limit?: number; offset?: number; q?: string } = {}, o?: O) =>
    request<Paged<ReportSummaryDTO>>('GET', '/reports', { query: { ...q }, ...o }),
  report: (id: string) => request<ReportDTO>('GET', `/reports/${enc(id)}`),
  exportReport: (id: string, format: ExportFormat) => download(`/reports/${enc(id)}/export`, { format }),
  deliverReport: (id: string, channel_ids: string[]) =>
    request<DeliverResult>('POST', `/reports/${enc(id)}/deliver`, { body: { channel_ids }, timeoutMs: 120000 }),
  item: (id: string) => request<IntelItemDetail>('GET', `/items/${enc(id)}`),

  channelKinds: () => request<ChannelKindDTO[]>('GET', '/channel-kinds'),
  channels: (o?: O) => request<ChannelDTO[]>('GET', '/channels', o),
  createChannel: (body: ChannelInput) => request<ChannelDTO>('POST', '/channels', { body }),
  updateChannel: (id: string, body: ChannelInput) => request<ChannelDTO>('PUT', `/channels/${enc(id)}`, { body }),
  deleteChannel: (id: string) => request<OkDTO>('DELETE', `/channels/${enc(id)}`),
  testChannel: (id: string) => request<TestResult>('POST', `/channels/${enc(id)}/test`, { timeoutMs: 60000 }),

  settings: (o?: O) => request<SettingsDTO>('GET', '/settings', o),
  updateSettings: (body: SettingsPatch, o?: O) => request<SettingsDTO>('PUT', '/settings', { body, ...o }),
  testLlm: () => request<LlmTestResult>('POST', '/llm/test', { timeoutMs: 120000 }),
  prompts: () => request<PromptDTO[] | Record<string, string>>('GET', '/prompts'),
  savePrompt: (name: PromptName, content: string) =>
    request<PromptDTO>('PUT', `/prompts/${enc(name)}`, { body: { name, content } }),

  logs: (q: LogQuery = {}, o?: O) => request<LogDTO[]>('GET', '/logs', { query: { ...q }, ...o }),
  doctor: () => request<DoctorCheck[]>('GET', '/doctor', { timeoutMs: 60000 }),
  demoSeed: (reset = false) => request<DemoSeedResult>('POST', '/demo/seed', { body: { reset }, timeoutMs: 120000 }),
  demoClear: () => request<OkDTO>('POST', '/demo/clear'),

  // ── v2 知识库（V2_KNOWLEDGE.md §7） ──
  kb: (q: KbQuery = {}, o?: O) => request<KbListDTO>('GET', '/kb', { query: { ...q }, ...o }),
  kbArticle: (id: string, o?: O) => request<KbArticleDTO>('GET', `/kb/${enc(id)}`, o),
}

/**
 * 报告图片地址：GET /api/reports/{id}/assets/{name}?token=
 * <img> 不能带 X-Bureau-Token，令牌走查询参数（与 SSE、导出一致）。打开报告前一定已经发过请求，令牌已就绪。
 */
export function reportAssetUrl(reportId: string, name: string): string {
  const t = currentToken()
  return `/api/reports/${enc(reportId)}/assets/${enc(name)}${t ? `?token=${enc(t)}` : ''}`
}

/**
 * MediaDTO.url / ArticleDTO.images 的取值可能是：
 * - 资源名（"m123.png"）→ 拼 assets 接口；
 * - 后端已拼好的同源地址（"/api/reports/…/assets/…"）→ 缺令牌时补上；
 * - data: / blob: 地址（mock）→ 原样使用。
 * 其它（外链 http 等）一律不用：CSP 是 img-src 'self' data: blob:，外链图片显示不了，也不该向外发请求。
 */
export function resolveAssetUrl(reportId: string, raw: string | undefined | null, fallbackName?: string): string | null {
  const v = (raw ?? '').trim()
  if (/^(data:image\/|blob:)/i.test(v)) return v
  if (v.startsWith('/api/')) {
    if (/[?&]token=/.test(v)) return v
    const t = currentToken()
    return t ? `${v}${v.includes('?') ? '&' : '?'}token=${enc(t)}` : v
  }
  if (v && !/^[a-z][a-z0-9+.-]*:/i.test(v) && !v.startsWith('/')) return reportAssetUrl(reportId, v.split(/[\\/]/).pop()!)
  if (!v && fallbackName) return reportAssetUrl(reportId, fallbackName)
  return null
}

/** GET /api/prompts 的返回形态 API.md 未写死：兼容数组 [{name, content}] 与对象 {name: content} */
export function normalizePrompts(res: PromptDTO[] | Record<string, string> | null): PromptDTO[] {
  if (!res) return []
  if (Array.isArray(res)) return res.filter((p) => p && typeof p.name === 'string')
  return Object.entries(res).map(([name, v]) => ({
    name,
    content: typeof v === 'string' ? v : String((v as { content?: unknown })?.content ?? ''),
  }))
}
