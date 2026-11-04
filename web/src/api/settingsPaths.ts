/**
 * /api/settings 各节内部字段。API.md 只约定了顶层 {app, llm, pipeline, interests, privacy, llm_providers}，
 * 节内字段名由后端决定。前端读写全部集中在这里：
 * - 读：按候选路径依次尝试（兼容几种常见命名）；
 * - 写：只用第一条路径，构造成深合并补丁 PUT /api/settings。
 * 已确定的字段：privacy.cloud_llm_consent（ARCHITECTURE §11）、privacy.live_preview（API.md SSE 表）。
 */
import type { SettingsDTO, SettingsPatch } from './types'

export type Path = readonly string[]

/**
 * 与后端 settings.yaml 一致（bureau/api/routes_config.py、config/settings.example.yaml）。
 * 写入一律用第一条路径；后端会拒绝把疑似密钥写进 settings.yaml，也会拒绝 llm 下不认识的配置块。
 */
export const SP = {
  effects: [['app', 'fx_level']],
  llmProvider: [['llm', 'provider']],
  llmConcurrency: [['llm', 'concurrency']],
  llmMaxChunks: [['llm', 'max_chunks']],
  llmBudgetCny: [['llm', 'max_cost_cny']],
  cloudConsent: [['privacy', 'cloud_llm_consent']],
  livePreview: [['privacy', 'live_preview']],
  /** 脱敏种类数组，如 ["phone","email","idcard","bankcard","wechat_id"] */
  desensitize: [['privacy', 'desensitize']],
  retentionDays: [['privacy', 'retention_days']],
  keywords: [['interests', 'keywords']],
  blockWords: [['interests', 'blocked']],
  categoryWeights: [['interests', 'category_weights']],
  /** label（v2 默认）/ flag / drop，见 V2_KNOWLEDGE.md §2 */
  riskPolicy: [['pipeline', 'risk_policy']],
  topN: [['pipeline', 'top_n']],
  /** v2：每天专题文章篇数，默认 12，范围 8~15 */
  maxFeatures: [['pipeline', 'max_features']],
} as const satisfies Record<string, readonly Path[]>

// ───────── v2：联网研究、图片与文档（V2_KNOWLEDGE.md §6） ─────────

export type RiskPolicy = 'label' | 'flag' | 'drop'
export const RISK_POLICY_DEFAULT: RiskPolicy = 'label'
/** 读 pipeline.risk_policy：不认识或缺省时按 v2 默认 label */
export function readRiskPolicy(s: SettingsDTO | null | undefined): RiskPolicy {
  const v = readFirst<string>(s, SP.riskPolicy, RISK_POLICY_DEFAULT)
  return v === 'flag' || v === 'drop' ? v : 'label'
}
export const MAX_FEATURES = { def: 12, min: 8, max: 15 } as const

/** research.* 非密钥字段及默认值（与 settings.example.yaml 一致） */
export const RESEARCH_DEFAULTS = {
  enabled: true, provider: 'deepseek', max_searches: 30, max_fetches: 30, per_article_queries: 2, github_enrich: true, x_enrich: true,
} as const
/** media.* 字段及默认值 */
export const MEDIA_DEFAULTS = { enabled: true, ocr: 'windows', max_images: 40, max_files: 15, max_file_mb: 20 } as const

/**
 * 研究用的密钥：GET 时是掩码，PUT 时空串或掩码 = 不修改，null = 删除。
 * 后端把它们存进 secrets.yaml 的同名路径（research.deepseek_api_key / research.github_token），不写 settings.yaml。
 */
export const RESEARCH_SECRET_KEYS = ['deepseek_api_key', 'github_token'] as const
export const researchPath: Path = ['research']
export const mediaPath: Path = ['media']

/** 提供方配置：llm.<key>（密钥字段 api_key 由后端单独存进 secrets.yaml） */
export const providerConfigPaths = (key: string): Path[] => [['llm', key]]
/** 采集器的非密钥配置。真实后端在 PlatformDTO.config 里给出；这里只给 mock 兜底用 */
export const sourceConfigPaths = (platform: string, adapter: string): Path[] => [
  ['sources', platform, adapter.split('.').slice(1).join('.')],
  ['sources', platform, adapter],
]

export function getAt(obj: unknown, path: Path): unknown {
  let cur: unknown = obj
  for (const k of path) {
    if (cur === null || typeof cur !== 'object') return undefined
    cur = (cur as Record<string, unknown>)[k]
  }
  return cur
}

export function readFirst<T>(obj: SettingsDTO | null | undefined, paths: readonly Path[], fallback: T): T {
  for (const p of paths) {
    const v = getAt(obj, p)
    if (v !== undefined && v !== null) return v as T
  }
  return fallback
}

/** ['llm','model'] + 'x' → { llm: { model: 'x' } } */
export function patchAt(path: Path, value: unknown): SettingsPatch {
  const out: Record<string, unknown> = {}
  let cur = out
  path.forEach((k, i) => {
    if (i === path.length - 1) cur[k] = value
    else cur = (cur[k] = {}) as Record<string, unknown>
  })
  return out as SettingsPatch
}

export function mergePatch(...parts: SettingsPatch[]): SettingsPatch {
  const out: Record<string, unknown> = {}
  const merge = (dst: Record<string, unknown>, src: Record<string, unknown>) => {
    for (const [k, v] of Object.entries(src)) {
      if (v && typeof v === 'object' && !Array.isArray(v) && dst[k] && typeof dst[k] === 'object') {
        merge(dst[k] as Record<string, unknown>, v as Record<string, unknown>)
      } else dst[k] = v
    }
  }
  for (const p of parts) merge(out, p as Record<string, unknown>)
  return out as SettingsPatch
}

/** 深合并到本地副本（mock 和乐观更新共用） */
export function deepMerge<T extends Record<string, unknown>>(target: T, patch: Record<string, unknown>): T {
  for (const [k, v] of Object.entries(patch)) {
    const cur = (target as Record<string, unknown>)[k]
    if (v && typeof v === 'object' && !Array.isArray(v) && cur && typeof cur === 'object' && !Array.isArray(cur)) {
      deepMerge(cur as Record<string, unknown>, v as Record<string, unknown>)
    } else (target as Record<string, unknown>)[k] = v
  }
  return target
}
