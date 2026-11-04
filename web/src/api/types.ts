/**
 * 接口类型：与 docs/API.md「类型」一节逐字段一致（只加了 export）。
 * v2 的类型（ArticleDTO 等）与 docs/V2_KNOWLEDGE.md §7 逐字段一致，ReportDTO 的 v2 字段全部可选（兼容 v1 旧报告）。
 * 第二部分是 API.md 接口表和 SSE 表里出现的请求/响应结构。
 * 改这里之前先改 API.md。
 */

// ───────────────────────── 第一部分：API.md 类型块 ─────────────────────────

export type Platform = 'wechat' | 'qq' | 'feishu' | 'demo'
export type Health = 'ok' | 'degraded' | 'down' | 'disabled' | 'unconfigured'
export type RunStatus = 'queued' | 'running' | 'success' | 'partial' | 'failed' | 'cancelled'
export type StageName = 'collect'|'clean'|'stats'|'segment'|'extract'|'merge'|'score'|'verify'|'compose'|'render'|'deliver'|'archive'
export type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'
export type AgentCode = 'SCOUT'|'SWEEPER'|'ANALYST'|'DECODER'|'STRATEGIST'|'AUDITOR'|'WRITER'|'COURIER'
export type Trend = 'new' | 'developing' | 'repeat'

export interface ConfigField { key: string; label: string; type: 'text'|'secret'|'number'|'bool'|'select'|'textarea'|'url';
  required?: boolean; default?: unknown; options?: {value: string; label: string}[]; help?: string; placeholder?: string }

export interface PlatformDTO { platform: Platform; label: string; enabled: boolean; adapter: string;
  adapters: { key: string; label: string; config_schema: ConfigField[]; available?: boolean; realtime?: boolean }[];
  health: Health; detail: string; hint?: string; checked_at?: string;
  groups_total: number; groups_whitelisted: number; messages_24h: number; last_collect_at?: string;
  /** 当前适配器的配置（密钥已掩码），用来预填表单（后端 v1.0 补充字段） */
  config?: Record<string, unknown> }

export interface GroupDTO { key: string; platform: Platform; native_id: string; name: string; alias?: string;
  member_count?: number; whitelisted: boolean; weight: number; tags: string[];
  messages_24h: number; messages_7d: number; last_message_at?: string; last_collect_at?: string }

export interface StageDTO { name: StageName; agent: AgentCode; status: StageStatus; started_at?: string; finished_at?: string;
  duration_ms?: number; metrics: Record<string, number | string>; message?: string }

export interface RunDTO { id: string; schedule_id?: string; trigger: 'manual'|'schedule'|'catchup'|'demo';
  status: RunStatus; dry_run: boolean; window_start: string; window_end: string;
  started_at?: string; finished_at?: string; stages: StageDTO[];
  totals: { messages_raw: number; messages_clean: number; chunks: number; candidates: number; items: number;
            tokens_in: number; tokens_out: number; cost_cny: number; llm_provider: string };
  report_id?: string; error?: string }

export interface Evidence { message_id: string; group_key: string; group_name: string; platform: Platform;
  sender: string; sent_at: string; quote: string }

export interface IntelItemDTO { id: string; report_id: string; rank: number; title: string; hook: string; summary: string;
  category: string; kind: string; score: number;
  scores: { novelty: number; actionability: number; credibility: number; heat: number; relevance: number };
  trend: Trend; risk_flags: string[]; tags: string[]; steps: string[]; tools: string[];
  links: { url: string; title?: string }[]; evidence: Evidence[];
  sources: { group_key: string; group_name: string; platform: Platform; count: number }[];
  participants: string[]; is_headline: boolean; is_feature: boolean }

export interface ReportSummaryDTO { id: string; run_id: string; title: string; date_label: string; window_label: string;
  created_at: string; items_total: number; headlines: { title: string; category: string; score: number }[];
  deliveries: { channel_id: string; channel_name: string; kind: string; ok: boolean }[] }

export interface ReportDTO extends ReportSummaryDTO { judgments: { text: string; basis: string }[];
  full_md: string; summary_md: string; items: IntelItemDTO[]; stats: StatsDTO
  // ── v2（docs/V2_KNOWLEDGE.md §7）：v1 旧报告没有这些字段，前端退回 full_md 阅读器 ──
  sections?: Partial<Record<SectionKey, string>>
  articles?: ArticleDTO[]
  resources?: ResourceDTO[]
  media?: MediaDTO[]
  groups?: GroupDigestDTO[]
  section_counts?: Partial<Record<SectionKey, number>> }

// ───────────────────────── v2：情报 + 知识库（V2_KNOWLEDGE.md §3.1、§7） ─────────────────────────

/** 当日报告的 12 个板块，key 与顺序固定（§3.1） */
export type SectionKey = 'overview' | 'articles' | 'resources' | 'prompts' | 'sops' | 'tools' | 'data'
  | 'risks' | 'quotes' | 'media' | 'groups' | 'briefs'
export const SECTION_KEYS: SectionKey[] = ['overview', 'articles', 'resources', 'prompts', 'sops', 'tools', 'data',
  'risks', 'quotes', 'media', 'groups', 'briefs']

export type ResourceKind = 'github' | 'x' | 'wechat_article' | 'netdisk' | 'video' | 'doc' | 'web' | 'other'

export interface ArticleSource { group_name: string; platform: Platform; sender: string; sent_at: string }

export interface ArticleDTO { id: string; seq: number; title: string; hook: string; category: string; body_md: string;
  risk_flags: string[]; risk_note?: string; sources: ArticleSource[];
  images: string[]; kb_id?: string; research_refs: {n: number; title: string; url: string}[] }

export interface ResourceDTO { kind: ResourceKind; title: string; url: string;
  code?: string; meta: Record<string, unknown>; note?: string; shared_by?: string; group_name?: string; sent_at?: string }

export interface MediaDTO { kind: 'image'|'file'; name: string; url?: string; ocr_text?: string; summary?: string; why?: string;
  group_name?: string; sender?: string; sent_at?: string; article_seq?: number }

export interface GroupDigestDTO { group_key: string; group_name: string; platform: Platform; messages: number; summary: string;
  highlights: string[]; counts: {links: number; prompts: number; sops: number; data: number} }

export interface KbSummaryDTO { id: string; title: string; category: string; tags: string[]; hook: string; risk_flags: string[];
  updated_at: string; created_at: string; versions: number; sources: number }

/** §7 写的是 `extends KbSummaryDTO`，但 versions / sources 在详情里是数组、在摘要里是数字，TS 里只能先 Omit 再覆盖 */
export interface KbArticleDTO extends Omit<KbSummaryDTO, 'versions' | 'sources'> { body_md: string;
  versions: {at: string; report_id: string; note: string}[];
  sources: {group_name: string; sender: string; sent_at: string}[]; related: {id: string; title: string}[] }

export interface KbQuery { q?: string; category?: string; tag?: string; limit?: number; offset?: number }
export interface KbListDTO { items: KbSummaryDTO[]; total: number; categories: {name: string; count: number}[];
  tags: {name: string; count: number}[] }
export interface KbCountsDTO { total: number; updated_today: number; new_today: number }

export interface StatsDTO {
  messages_raw: number; messages_clean: number; snr: number; speakers: number;
  by_platform: { platform: Platform; messages: number; groups: number }[];
  hourly: { hour: number; wechat: number; qq: number; feishu: number; demo: number }[]   // 0..23
  heat_7x24: [number, number, number][]          // [dayIndex 0..6 (0=最旧), hour 0..23, count]
  msg_types: { kind: string; count: number }[]
  top_groups: { group_key: string; name: string; platform: Platform; messages: number; speakers: number; heat: number }[]
  top_speakers: { name: string; group_name: string; messages: number }[]
  keywords: { word: string; weight: number; trend: 'up'|'flat'|'new' }[]                  // 词云，最多 80 个
  rising: { word: string; today: number; avg7: number; z: number; groups: string[]; spark: number[] }[]  // spark 为 7 天
}

export interface OverviewDTO {
  generated_at: string; mode: 'live' | 'demo'; window: { start: string; end: string };
  kpis: { messages_24h: number; messages_delta: number; intel_today: number; intel_delta: number;
          groups_active: number; groups_whitelisted: number; snr: number; signals_rising: number;
          next_run_at?: string; last_run_status?: RunStatus };
  platforms: PlatformDTO[]; stats: StatsDTO;
  constellation: { nodes: { id: string; name: string; type: 'platform'|'group'|'topic'; platform?: Platform;
                            value: number; category?: string }[];
                   links: { source: string; target: string; value: number }[] };
  headlines: IntelItemDTO[];                 // 最近一份报告的头条，可能为空
  latest_report?: ReportSummaryDTO; current_run?: RunDTO; last_run?: RunDTO;
  agents: { code: AgentCode; name: string; stages: StageName[]; status: StageStatus; task: string; metric?: string }[];
  ticker: string[];                          // 底部滚动条
  llm: { provider: string; model?: string; ready: boolean; cloud_consent: boolean; tokens_today: number; cost_today_cny: number };
  /** v2：知识库计数（§7）；v1 后端没有 */
  kb?: KbCountsDTO;
}

export interface ScheduleDTO { id: string; name: string; enabled: boolean; cron: string; timezone: string;
  window_mode: 'since_last' | 'fixed_hours'; window_hours: number;
  platforms: Platform[]; group_keys: string[];      // 空数组表示该平台全部白名单群
  channel_ids: string[]; top_n: number; dry_run: boolean; next_run_at?: string; last_run?: { id: string; status: RunStatus; finished_at?: string } }

export interface ChannelKindDTO { kind: string; label: string; platform_label: string; config_schema: ConfigField[]; available?: boolean }
export interface ChannelDTO { id: string; kind: string; name: string; enabled: boolean; config: Record<string, unknown>;  // 密钥已掩码
  last_result?: { ok: boolean; detail: string; at: string } }

export interface LogDTO { ts: string; level: 'debug'|'info'|'warn'|'error'; source: string; message: string; run_id?: string; stage?: StageName }
export interface DoctorCheck { id: string; title: string; status: Health; detail: string; hint?: string }

// ───────────────────── 第二部分：接口表 / SSE 表中的结构 ─────────────────────

export type AgentDTO = OverviewDTO['agents'][number]
export type ConstellationNode = OverviewDTO['constellation']['nodes'][number]
export type ConstellationLink = OverviewDTO['constellation']['links'][number]
export type KeywordTrend = StatsDTO['keywords'][number]['trend']

/** 错误统一格式 */
export interface ApiErrorBody { error: { code: string; message: string; hint?: string } }
/** 列表分页 */
export interface Paged<T> { items: T[]; total: number }
export interface OkDTO { ok: true }

export interface SessionDTO { token: string; version: string; mode: 'live' | 'demo' }
export interface HealthDTO { ok: boolean; version: string }

export interface PlatformUpdate { enabled?: boolean; adapter?: string; config?: Record<string, unknown> }
export interface RefreshGroupsResult { added: number; updated: number; total: number }
export interface GroupQuery { platform?: Platform; whitelisted?: boolean; q?: string; limit?: number; offset?: number }
export interface GroupPatch { whitelisted?: boolean; weight?: number; alias?: string; tags?: string[] }
export interface GroupBulk { keys: string[]; whitelisted: boolean }
export interface GroupBulkResult { updated: number }
export interface ImportResult { group: GroupDTO; imported: number; skipped: number; format: string; warnings: string[] }

/** POST/PUT /api/schedules 的请求体（服务端生成 id、next_run_at、last_run） */
export type ScheduleInput = Omit<ScheduleDTO, 'id' | 'next_run_at' | 'last_run'>
export interface ScheduleRunBody { dry_run?: boolean }
export interface RunCreate { platforms?: Platform[]; group_keys?: string[]; channel_ids?: string[];
  window_hours?: number; dry_run?: boolean; demo?: boolean }

export interface DeliverBody { channel_ids: string[] }
export interface DeliverResult { results: { channel_id: string; ok: boolean; detail: string }[] }
export type ExportFormat = 'md' | 'html' | 'json'

/**
 * GET /api/items/{id} 的证据上下文消息。API.md 只写了 `Msg`，没有给字段；
 * 这里按 RawMessage 取最可能的字段，全部可选，渲染时容错。
 */
export interface ContextMsg { message_id?: string; native_id?: string; sender?: string; sender_name?: string;
  sent_at?: string; text?: string; quote?: string; group_name?: string }
export type IntelItemDetail = IntelItemDTO & { context?: { before: ContextMsg[]; after: ContextMsg[] } }

export interface ChannelInput { kind: string; name: string; enabled: boolean; config: Record<string, unknown> }
export interface TestResult { ok: boolean; detail: string }

export interface LlmProviderDTO { key: string; label: string; config_schema: ConfigField[] }
/** GET /api/settings：各节内部结构由后端决定，前端按 settingsPaths.ts 读写 */
export interface SettingsDTO { app: Record<string, unknown>; llm: Record<string, unknown>;
  pipeline: Record<string, unknown>; interests: Record<string, unknown>; privacy: Record<string, unknown>;
  llm_providers: LlmProviderDTO[]; [section: string]: unknown }
export type SettingsPatch = Partial<Record<'app' | 'llm' | 'pipeline' | 'interests' | 'privacy' | 'sources' | 'research' | 'media',
  Record<string, unknown>>>
export interface LlmTestResult { ok: boolean; provider: string; model: string; latency_ms: number; detail: string }
export type PromptName = 'extract' | 'compose' | 'merge' | 'extract_v2' | 'article' | 'digest' | 'research_queries'
export interface PromptDTO { name: string; content: string }
export interface LogQuery { level?: LogDTO['level']; limit?: number }
export interface DemoSeedResult { groups: number; messages: number }

// ── SSE 事件（event 名 → data） ──
export interface HelloEvent { server_time: string; mode: 'live' | 'demo' }
export interface HeartbeatEvent { server_time: string }
export interface RunStageEvent { run_id: string; stage: StageDTO }
export interface DeliveryEvent { run_id: string; report_id: string; channel_id: string; channel_name: string;
  kind: string; ok: boolean; detail: string }
export interface IngestEvent { platform: Platform; group_name: string; count: number; sender?: string; preview?: string }

export interface SseEventMap {
  hello: HelloEvent
  heartbeat: HeartbeatEvent
  'run.started': RunDTO
  'run.stage': RunStageEvent
  'run.log': LogDTO
  'run.finished': RunDTO
  'report.created': ReportSummaryDTO
  'delivery.result': DeliveryEvent
  'ingest.message': IngestEvent
  'platform.health': PlatformDTO
  'overview.dirty': Record<string, never>
}
export type SseEventName = keyof SseEventMap
export const SSE_EVENTS: SseEventName[] = ['hello', 'heartbeat', 'run.started', 'run.stage', 'run.log',
  'run.finished', 'report.created', 'delivery.result', 'ingest.message', 'platform.health', 'overview.dirty']
