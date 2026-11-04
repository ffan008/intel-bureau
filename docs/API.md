# 工作台 REST / SSE 接口契约 v1

前后端都必须严格遵守本文。A 实现后端，C 实现前端（含 mock）。字段名统一 snake_case，时间一律 ISO 8601 带时区（如 `2026-10-28T08:00:00+08:00`）。

## 约定

- 基地址：`http://127.0.0.1:8765`；前端开发时 Vite（5180）把 `/api` 代理到 8765，需设 `changeOrigin: true`。
- 鉴权：先 `GET /api/session` 拿 `token`，之后所有 `/api/*` 请求带 `X-Bureau-Token: <token>`。SSE 改用 `?token=`。免鉴权的只有 `/api/session`、`/api/health`、`/api/ingest/onebot`。
- 错误统一返回 `{"error": {"code": "string", "message": "中文说明", "hint": "可选的修复建议"}}`，配合合适的 HTTP 状态码。
- 列表分页参数 `?limit=&offset=`，返回 `{ "items": [...], "total": n }`。
- 密钥字段只返回掩码 `"••••abcd"`。PUT 时字段为空串或掩码，表示不修改。

## 实现补充（v1.0 后端交付时确认）

- `snr` 一律是 0~1 的比值，前端显示时乘 100。
- `PlatformDTO` 多一个 `config` 字段，是当前适配器配置，密钥已掩码，用来预填表单。`adapters[]` 和 `ChannelKindDTO` 都多一个 `available`，为 false 时前端置灰。
- `GET /api/items/{id}` 的 `context` 结构为 `{before: Msg[], after: Msg[], focus?: Msg}`，其中 `Msg = {message_id, sender_name, sent_at, text}`。
- 报告在工作台里的链接是 `/reports?id=<report_id>`。导出接口也接受 `?token=`，加 `inline=1` 时在浏览器内预览。
- PUT 设置时，密钥字段传空串或掩码表示不修改，传 `null` 表示删除。
- 以下字段只增不改：`is_demo`、`IntelItemDTO.action / unverified / feature`、`msg_types[].label`、`overview.llm.reason / offline_mode`。
- `/api/settings` 各节的字段与 `config/settings.example.yaml` 一致，前端读写路径集中在 `web/src/api/settingsPaths.ts`：
  - `app.fx_level`（high / medium / low / off）、`app.demo_stage_min_ms`
  - `llm.provider / concurrency / max_chunks / max_cost_cny`；提供方配置在 `llm.<提供方>`（`claude_code`、`openai_compat`、`anthropic`），其中 `api_key` 由后端单独存进 secrets.yaml
  - `interests.keywords / blocked / category_weights`；`category_weights` 的键是完整分类名，如 `"01 工具与资源"`
  - `privacy.cloud_llm_consent / desensitize / retention_days / live_preview`；`desensitize` 是种类数组：`phone`、`email`、`idcard`、`bankcard`、`wechat_id`
  - 平台采集配置不在 `/api/settings` 里，读 `PlatformDTO.config`，写 `PUT /api/platforms/{platform}`。
- PUT `/api/settings` 遇到以下情况返回 400，并且不会写入任何内容：
  - `llm` 下出现不认识的配置块（例如 `llm.providers`）
  - 补丁里出现疑似密钥的键（`api_key`、`token`、`secret`、`password` 等），但位置不是 `llm.<提供方>.api_key`
- 定时任务的 cron 按标准语义：星期 0 和 7 是周日，1 是周一；「日」和「周」不能同时限定。

## 类型（TypeScript 描述）

```ts
type Platform = 'wechat' | 'qq' | 'feishu' | 'demo'
type Health = 'ok' | 'degraded' | 'down' | 'disabled' | 'unconfigured'
type RunStatus = 'queued' | 'running' | 'success' | 'partial' | 'failed' | 'cancelled'
type StageName = 'collect'|'clean'|'stats'|'segment'|'extract'|'merge'|'score'|'verify'|'compose'|'render'|'deliver'|'archive'
type StageStatus = 'pending' | 'running' | 'done' | 'skipped' | 'failed'
type AgentCode = 'SCOUT'|'SWEEPER'|'ANALYST'|'DECODER'|'STRATEGIST'|'AUDITOR'|'WRITER'|'COURIER'
type Trend = 'new' | 'developing' | 'repeat'

interface ConfigField { key: string; label: string; type: 'text'|'secret'|'number'|'bool'|'select'|'textarea'|'url';
  required?: boolean; default?: unknown; options?: {value: string; label: string}[]; help?: string; placeholder?: string }

interface PlatformDTO { platform: Platform; label: string; enabled: boolean; adapter: string;
  adapters: { key: string; label: string; config_schema: ConfigField[] }[];
  health: Health; detail: string; hint?: string; checked_at?: string;
  groups_total: number; groups_whitelisted: number; messages_24h: number; last_collect_at?: string }

interface GroupDTO { key: string; platform: Platform; native_id: string; name: string; alias?: string;
  member_count?: number; whitelisted: boolean; weight: number; tags: string[];
  messages_24h: number; messages_7d: number; last_message_at?: string; last_collect_at?: string }

interface StageDTO { name: StageName; agent: AgentCode; status: StageStatus; started_at?: string; finished_at?: string;
  duration_ms?: number; metrics: Record<string, number | string>; message?: string }

interface RunDTO { id: string; schedule_id?: string; trigger: 'manual'|'schedule'|'catchup'|'demo';
  status: RunStatus; dry_run: boolean; window_start: string; window_end: string;
  started_at?: string; finished_at?: string; stages: StageDTO[];
  totals: { messages_raw: number; messages_clean: number; chunks: number; candidates: number; items: number;
            tokens_in: number; tokens_out: number; cost_cny: number; llm_provider: string };
  report_id?: string; error?: string }

interface Evidence { message_id: string; group_key: string; group_name: string; platform: Platform;
  sender: string; sent_at: string; quote: string }

interface IntelItemDTO { id: string; report_id: string; rank: number; title: string; hook: string; summary: string;
  category: string; kind: string; score: number;
  scores: { novelty: number; actionability: number; credibility: number; heat: number; relevance: number };
  trend: Trend; risk_flags: string[]; tags: string[]; steps: string[]; tools: string[];
  links: { url: string; title?: string }[]; evidence: Evidence[];
  sources: { group_key: string; group_name: string; platform: Platform; count: number }[];
  participants: string[]; is_headline: boolean; is_feature: boolean }

interface ReportSummaryDTO { id: string; run_id: string; title: string; date_label: string; window_label: string;
  created_at: string; items_total: number; headlines: { title: string; category: string; score: number }[];
  deliveries: { channel_id: string; channel_name: string; kind: string; ok: boolean }[] }

interface ReportDTO extends ReportSummaryDTO { judgments: { text: string; basis: string }[];
  full_md: string; summary_md: string; items: IntelItemDTO[]; stats: StatsDTO }

interface StatsDTO {
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

interface OverviewDTO {
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
}

interface ScheduleDTO { id: string; name: string; enabled: boolean; cron: string; timezone: string;
  window_mode: 'since_last' | 'fixed_hours'; window_hours: number;
  platforms: Platform[]; group_keys: string[];      // 空数组表示该平台全部白名单群
  channel_ids: string[]; top_n: number; dry_run: boolean; next_run_at?: string; last_run?: { id: string; status: RunStatus; finished_at?: string } }

interface ChannelKindDTO { kind: string; label: string; platform_label: string; config_schema: ConfigField[] }
interface ChannelDTO { id: string; kind: string; name: string; enabled: boolean; config: Record<string, unknown>;  // 密钥已掩码
  last_result?: { ok: boolean; detail: string; at: string } }

interface LogDTO { ts: string; level: 'debug'|'info'|'warn'|'error'; source: string; message: string; run_id?: string; stage?: StageName }
interface DoctorCheck { id: string; title: string; status: Health; detail: string; hint?: string }
```

## 接口

| 方法 路径 | 说明 | 返回 |
|---|---|---|
| GET `/api/session` | 取访问令牌 | `{token, version, mode}` |
| GET `/api/health` | 存活 | `{ok:true, version}` |
| GET `/api/overview` | 大屏全部数据 | `OverviewDTO` |
| GET `/api/platforms` | 平台状态 | `PlatformDTO[]` |
| PUT `/api/platforms/{platform}` | 改启用/适配器/配置 `{enabled?, adapter?, config?}` | `PlatformDTO` |
| POST `/api/platforms/{platform}/test` | 立即健康检查 | `PlatformDTO` |
| POST `/api/platforms/{platform}/refresh-groups` | 从平台拉群列表 | `{added, updated, total}` |
| GET `/api/groups?platform=&whitelisted=&q=` | 群列表（分页） | `{items: GroupDTO[], total}` |
| PATCH `/api/groups/{key}` | `{whitelisted?, weight?, alias?, tags?}`；key 需 URL 编码 | `GroupDTO` |
| POST `/api/groups/bulk` | `{keys: string[], whitelisted: boolean}` | `{updated}` |
| POST `/api/import` | multipart：`file` 或 `text`，加 `platform`、`group_name` | `{group: GroupDTO, imported, skipped, format, warnings}` |
| GET `/api/schedules` | 定时任务 | `ScheduleDTO[]` |
| POST `/api/schedules` | 新建 | `ScheduleDTO` |
| PUT `/api/schedules/{id}` | 修改 | `ScheduleDTO` |
| DELETE `/api/schedules/{id}` | 删除 | `{ok:true}` |
| POST `/api/schedules/{id}/run` | 立即运行该任务 `{dry_run?}` | `RunDTO`（202） |
| POST `/api/runs` | 临时运行 `{platforms?, group_keys?, channel_ids?, window_hours?, dry_run?, demo?}` | `RunDTO`（202）；已有运行时返回 409 |
| GET `/api/runs?limit=` | 运行历史 | `{items: RunDTO[], total}` |
| GET `/api/runs/{id}` | 详情 | `RunDTO` |
| POST `/api/runs/{id}/cancel` | 取消 | `RunDTO` |
| GET `/api/runs/{id}/logs` | 运行日志 | `LogDTO[]` |
| GET `/api/reports?limit=&offset=&q=` | 报告列表 | `{items: ReportSummaryDTO[], total}` |
| GET `/api/reports/{id}` | 报告详情 | `ReportDTO` |
| GET `/api/reports/{id}/export?format=md\|html\|json` | 下载 | 文件 |
| POST `/api/reports/{id}/deliver` | 重新投递 `{channel_ids}` | `{results: {channel_id, ok, detail}[]}` |
| GET `/api/items/{id}` | 单条情报，含证据上下文 `context: {before: Msg[], after: Msg[]}`（前后各 5 条） | `IntelItemDTO & {context}` |
| GET `/api/channel-kinds` | 可用通道类型及表单 schema | `ChannelKindDTO[]` |
| GET `/api/channels` | 通道列表 | `ChannelDTO[]` |
| POST `/api/channels` | `{kind, name, enabled, config}` | `ChannelDTO` |
| PUT `/api/channels/{id}` | 修改 | `ChannelDTO` |
| DELETE `/api/channels/{id}` | 删除 | `{ok:true}` |
| POST `/api/channels/{id}/test` | 发送测试消息 | `{ok, detail}` |
| GET `/api/settings` | 设置（密钥已掩码）：`{app, llm, pipeline, interests, privacy, llm_providers: {key,label,config_schema}[]}` | 对象 |
| PUT `/api/settings` | 局部更新（深合并） | 同上 |
| POST `/api/llm/test` | 用当前设置做一次最小调用 | `{ok, provider, model, latency_ms, detail}` |
| GET `/api/prompts` / PUT `/api/prompts/{name}` | 提示词模板 `extract`、`compose`、`merge`（`{name, content}`） | – |
| GET `/api/logs?level=&limit=` | 系统日志 | `LogDTO[]` |
| GET `/api/doctor` | 体检 | `DoctorCheck[]` |
| POST `/api/demo/seed` | 写入演示数据 `{reset?: boolean}` | `{groups, messages}` |
| POST `/api/demo/clear` | 清除演示数据 | `{ok:true}` |
| POST `/api/ingest/onebot` | NapCat 实时上报（仅本机） | `{}`（204） |
| GET `/api/events?token=` | SSE 事件流 | 见下 |

## SSE 事件（`text/event-stream`，`event:` 为类型，`data:` 为 JSON）

| event | data | 用途 |
|---|---|---|
| `hello` | `{server_time, mode}` | 连接成功 |
| `heartbeat` | `{server_time}` | 每 15 秒 |
| `run.started` | `RunDTO` | |
| `run.stage` | `{run_id, stage: StageDTO}` | 阶段状态或指标变化 |
| `run.log` | `LogDTO` | 打字机终端 |
| `run.finished` | `RunDTO` | |
| `report.created` | `ReportSummaryDTO` | |
| `delivery.result` | `{run_id, report_id, channel_id, channel_name, kind, ok, detail}` | |
| `ingest.message` | `{platform, group_name, count}`；设置 `privacy.live_preview=true` 时多带 `sender` 和不超过 30 字的 `preview` | 实时上报动效 |
| `platform.health` | `PlatformDTO` | |
| `overview.dirty` | `{}` | 前端重新拉 `/api/overview` |

前端要处理断线重连（指数退避，最多 30 秒），重连后重新拉一次 overview。

## v2（情报 + 知识库，后端 A2 交付时确认）

规格见 `docs/V2_KNOWLEDGE.md` §7。以下字段只增不改；v1 的字段和含义都不变。

### 报告：`GET /api/reports/{id}` 新增字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `sections` | `Record<SectionKey, string>` | 12 个板块的 Markdown 正文（不含板块标题；板块内小标题从 `###` 起，专题从 `##` 起） |
| `section_counts` | `Record<SectionKey, number>` | 各板块条目数（导航上的计数） |
| `articles` | `ArticleDTO[]` | 专题，按 `seq` 升序 |
| `resources` | `ResourceDTO[]` | 资源库 |
| `media` | `MediaDTO[]` | 图片与文档 |
| `groups` | `GroupDigestDTO[]` | 分群摘要 |
| `doc_links` | `Record<string, string>` | 文档类通道发布后的链接，如 `{feishu_doc: "https://…"}`；没投递时为 `{}` |

`SectionKey` 固定顺序：`overview, articles, resources, prompts, sops, tools, data, risks, quotes, media, groups, briefs`。

v1 生成的旧报告没有这些数据：数组字段返回 `[]`，`sections` / `section_counts` / `doc_links` 返回 `{}`。

DTO 与 §7 一致，补充说明：

- `ArticleDTO` 多两个字段：`source_lines: string[]`（"微信·群名·发言人·10-29 21:44"，推送和飞书用）、`item_id`（对应的 `IntelItemDTO.id`）。`body_md` 是 §3.2 模板的完整正文，第一行是 `# 01-标题`。`images` 是 assets 目录里的文件名（如 `m305.png`）。
- `body_md` 和知识库正文里的图片写成相对路径 `![](<report_id>_assets/m305.png)`。前端显示时改写成 `/api/reports/<report_id>/assets/m305.png?token=…`（路径里的 report_id 就是图片所属的报告；知识库条目跨天合并后可能引用多份报告的图片）。
- `ResourceDTO.meta`：GitHub 有 `stars / language / forks / updated_at`，X 有 `author / likes / retweets`，公众号有 `author / words`，网盘有 `provider`（没有联网增强时只有 `provider`）。`code` 是网盘提取码，从群聊原文照录。条目还带 `risk_flags`（来自哪个带风险标签的话题）。
- `MediaDTO.url` 形如 `/api/reports/{id}/assets/{name}`（需要令牌）；没取回的媒体没有 `url`，`note` 说明原因（如"未取回（媒体模块不可用）"）。
- `IntelItemDTO` 新增：`topic`、`seq`（专题序号，非专题为 0）、`sop_steps`、`prompts[]`（`{text, purpose, sender, group_name, sent_at, message_id, verbatim}`，`text` 是数据库原文；`verbatim=false` 表示原文含个人信息已脱敏）、`data_points[]`、`quotes[]`、`tool_notes[]`、`kb_id`；`links[]` 多 `kind / code / shared_by / group_name / sent_at`。
- `action` 的说法随 `risk_policy` 变化：`label` 下带风险标签的条目照常给建议，末尾提醒"是否采用请自行判断"；违法高危固定为"只作了解，不要参与"。

### 报告附件：`GET /api/reports/{id}/assets/{name}?token=`

- 只能读这份报告 `data/reports/<日期>/<report_id>_assets/` 目录里、并且登记在这份报告 `media[].url` 里的文件。
- 文件名只允许字母、数字、`_ . -`，不能含 `/`、`\`、`..`；扩展名只允许图片（png / jpg / gif / webp / bmp）和文档（pdf / docx / xlsx / pptx / txt / md / csv）。其它一律 400 / 404。
- 图片 `inline`，文档 `attachment`；响应带 `Content-Security-Policy: default-src 'none'; sandbox`。
- 和 `/export` 一样接受 `?token=`（`<img src>` 无法带请求头）。
- `GET /api/reports/{id}/export?format=html&inline=1&token=…` 预览时，HTML 里的相对路径图片会改写成这个接口的地址（带同一个令牌）；下载（不带 `inline`）的文件保持相对路径，和 assets 目录放在一起即可离线打开。

### 重新投递：`POST /api/reports/{id}/deliver`

先投文档类通道（`feishu_doc`），拿到链接后写进 `doc_links`、重新生成推送版（`summary_md` / `summary_text`），再并发投其它通道；新的链接和推送版写回报告。返回的 `results[]` 里文档类通道多一个 `url`。SSE `delivery.result` 事件同样多一个可选的 `url`。

### 知识库

| 方法 路径 | 说明 | 返回 |
|---|---|---|
| GET `/api/kb?q=&category=&tag=&limit=&offset=&scope=` | 列表（按更新时间倒序）。`q` 全文搜索（标题、正文、标签；3 个字以上走 FTS5 trigram，更短的用 LIKE）。`scope` 默认跟随工作台模式（`demo` / `live`） | `{items: KbSummaryDTO[], total, categories: {name, count}[], tags: {name, count}[], scope}` |
| GET `/api/kb/{id}` | 详情 | `KbArticleDTO`（另有 `first_day`、`last_day`） |
| GET `/api/kb/{id}/versions/{version_id}` | 某个历史版本的正文 | `{id, kb_id, at, report_id, day, note, title, body_md}` |

- `KbArticleDTO.versions[]` 按时间升序，每次写入一条：`{at, report_id, note, id}`（`note` 如"2026-10-30 新建（报告 …）"、"同日重跑，刷新当天内容"、"合并更新：新增来源 3 条"）。`versions[]` 不带正文，要看旧版本时用 `id` 调上面的版本接口。
- 合并规则：话题指纹（话题名或标题归一化后的哈希）相同，或核心词至少 3 个重叠且重叠系数 ≥ 0.5，或共享链接。之后的日子在正文末尾追加 `## {日期} 更新` 一节（其中的小标题降一级），同一天重跑只替换当天内容。
- `KbSummaryDTO.versions` / `.sources` 是个数，`KbArticleDTO.versions` / `.sources` 是数组（与 §7 一致）。

### `GET /api/overview` 新增

`kb: {total, updated_today, new_today}`（当前模式的知识库；`updated_today` 不含当天新建的条目）。

### 设置：`GET / PUT /api/settings`

- 可修改的部分加上 `research`、`media`（字段见 `config/settings.example.yaml`）。
- `research.deepseek_api_key`、`research.github_token` 存进 `secrets.yaml`，返回 `••••末4位`；传掩码或空串表示不修改，`null` 表示删除。
- 校验（不合格返回 400，什么都不写入）：`pipeline.risk_policy ∈ {label, flag, drop}`；`pipeline.max_features` 8~15 的整数；`pipeline.risk_penalty` 0~5；`research.provider ∈ {deepseek, none}`；`research.per_article_queries` 1~3；`media.ocr ∈ {windows, llm, off}`；`media.max_file_mb` 0.1~200。

### 提示词：`GET / PUT /api/prompts`

名字增加 `extract_v2`、`article`、`digest`、`research_queries`（必须保留的占位符分别是 `{{chat_log}}`、`{{data}}`、`{{data}}`、`{{data}}`）。v1 的 `extract`、`compose`、`merge` 仍可读写，但 v2 流水线只在开启 `llm.merge_judge` 时用到 `merge`；`extract_v2.md` 缺失时退回 `extract.md`。

### 运行指标（`StageDTO.metrics`，只增）

- `clean.media_candidates`；`extract.prompts / privacy_flagged`；`merge.points`（要点数）、`topics`；`score.illegal / privacy_dropped / risk_policy / features`；`verify.prompts / prompts_dropped / data_points / media_refs / refs_dropped / features`；`compose.media_* / research_* / enrich_* / llm / offline / digest_*`；`render.resources / prompts / risks / media / assets`；`deliver.doc_channels / doc_links`；`archive.kb_new / kb_merged`。
- `RunDTO.totals` 可能多 `research_searches / research_fetches / research_cost_cny`；研究的费用已经计入 `cost_cny`。
