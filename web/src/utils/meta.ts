/** 展示用的元数据：平台、健康、阶段、Agent、分类、趋势 */
import type { AgentCode, Health, Platform, RunStatus, StageName, StageStatus, Trend } from '@/api/types'
import { hashStr } from './format'

export const PLATFORM: Record<Platform, { label: string; color: string; short: string }> = {
  wechat: { label: '微信', color: '#2bd96b', short: 'WX' },
  qq: { label: 'QQ', color: '#2aa8ff', short: 'QQ' },
  feishu: { label: '飞书', color: '#4f7cff', short: 'FS' },
  demo: { label: '演示', color: '#b48cff', short: 'DM' },
}
export const REAL_PLATFORMS: Platform[] = ['wechat', 'qq', 'feishu']
export const platformColor = (p?: Platform | string): string => PLATFORM[p as Platform]?.color ?? '#6c86a3'
export const platformLabel = (p?: Platform | string): string => PLATFORM[p as Platform]?.label ?? String(p ?? '')

export const HEALTH: Record<Health, { label: string; color: string }> = {
  ok: { label: '正常', color: '#2bff9a' },
  degraded: { label: '降级', color: '#ffb020' },
  down: { label: '中断', color: '#ff4d5e' },
  disabled: { label: '已停用', color: '#50627a' },
  unconfigured: { label: '未配置', color: '#50627a' },
}

export const RUN_STATUS: Record<RunStatus, { label: string; cls: string }> = {
  queued: { label: '排队中', cls: 'grey' },
  running: { label: '运行中', cls: 'cyan' },
  success: { label: '成功', cls: 'green' },
  partial: { label: '部分成功', cls: 'amber' },
  failed: { label: '失败', cls: 'red' },
  cancelled: { label: '已取消', cls: 'grey' },
}

export const STAGE_STATUS: Record<StageStatus, { label: string; cls: string }> = {
  pending: { label: '待命', cls: 'grey' },
  running: { label: '执行中', cls: 'cyan' },
  done: { label: '完成', cls: 'green' },
  skipped: { label: '跳过', cls: 'grey' },
  failed: { label: '告警', cls: 'red' },
}

export const STAGES: StageName[] = ['collect', 'clean', 'stats', 'segment', 'extract', 'merge', 'score', 'verify', 'compose', 'render', 'deliver', 'archive']
export const STAGE_LABEL: Record<StageName, string> = {
  collect: '采集', clean: '清洗', stats: '统计', segment: '切分', extract: '抽取', merge: '合并',
  score: '评分', verify: '核验', compose: '撰写', render: '渲染', deliver: '投递', archive: '归档',
}

export interface AgentMeta { code: AgentCode; name: string; stages: StageName[]; role: string }
/** ARCHITECTURE §7：8 个 Agent 与 12 个阶段的映射（按流水线顺序） */
export const AGENTS: AgentMeta[] = [
  { code: 'SCOUT', name: '侦察兵', stages: ['collect'], role: '从白名单群采集消息' },
  { code: 'SWEEPER', name: '清道夫', stages: ['clean'], role: '去噪、去重、脱敏' },
  { code: 'ANALYST', name: '分析师', stages: ['stats', 'segment'], role: '统计风向、切分对话' },
  { code: 'DECODER', name: '解码员', stages: ['extract'], role: '从对话块提取候选情报' },
  { code: 'STRATEGIST', name: '参谋', stages: ['merge', 'score'], role: '合并话题、打分排序' },
  { code: 'AUDITOR', name: '审查官', stages: ['verify'], role: '核对证据与数字' },
  { code: 'WRITER', name: '主笔', stages: ['compose', 'render'], role: '撰写风向判断、生成报告' },
  { code: 'COURIER', name: '通讯兵', stages: ['deliver', 'archive'], role: '多通道投递、归档' },
]
export const AGENT_BY_CODE = Object.fromEntries(AGENTS.map((a) => [a.code, a])) as Record<AgentCode, AgentMeta>
export const STAGE_AGENT = Object.fromEntries(AGENTS.flatMap((a) => a.stages.map((s) => [s, a.code]))) as Record<StageName, AgentCode>

export const TREND: Record<Trend, { label: string; cls: string }> = {
  new: { label: 'NEW', cls: 'cyan' },
  developing: { label: '发酵中', cls: 'amber' },
  repeat: { label: '重复', cls: 'grey' },
}

/** 默认分类（ARCHITECTURE §9）的配色。用户自定义分类按名字哈希到同一色板。 */
const CAT_COLORS: Record<string, string> = {
  '01': '#22e4ff', '02': '#8b5cff', '03': '#ff3db8', '04': '#ffb020', '05': '#2bff9a',
  '06': '#4f9dff', '07': '#ff8a4c', '08': '#ff4d5e', '99': '#6c86a3',
}
const CAT_NAMES: Record<string, string> = {
  工具: '01', 资源: '01', 提示词: '02', 工作流: '02', 创作: '03', 流量: '04', 变现: '04', 编程: '05',
  自动化: '05', 模型: '06', 平台: '06', 需求: '07', 机会: '07', 风险: '08', 避坑: '08', 其他: '99',
}
const PALETTE = Object.values(CAT_COLORS).slice(0, 8)
export function categoryColor(cat?: string | null): string {
  if (!cat) return CAT_COLORS['99']!
  const code = /^\s*(\d{2})/.exec(cat)?.[1]
  if (code && CAT_COLORS[code]) return CAT_COLORS[code]!
  for (const [k, v] of Object.entries(CAT_NAMES)) if (cat.includes(k)) return CAT_COLORS[v]!
  return PALETTE[hashStr(cat) % PALETTE.length]!
}
/** "02 提示词与工作流" → "提示词与工作流" */
export const categoryName = (cat?: string | null): string => (cat ?? '').replace(/^\s*\d{2}\s*/, '') || '其他'

export const MSG_KIND_LABEL: Record<string, string> = {
  text: '文本', image: '图片', link: '链接', file: '文件', video: '视频', voice: '语音', sticker: '表情',
  card: '卡片', forward: '合并转发', reply: '引用回复', system: '系统', recall: '撤回', redpacket: '红包', other: '其他',
}

export const SCORE_DIMS: { key: 'novelty' | 'actionability' | 'credibility' | 'heat' | 'relevance'; label: string }[] = [
  { key: 'novelty', label: '新颖' }, { key: 'actionability', label: '可执行' }, { key: 'credibility', label: '可信' },
  { key: 'heat', label: '热度' }, { key: 'relevance', label: '相关' },
]

/** 推送通道 kind → 平台色（未知 kind 用平台标签猜） */
export function channelColor(kind: string, platformLabel?: string): string {
  if (kind.startsWith('feishu')) return PLATFORM.feishu.color
  if (kind.startsWith('qq')) return PLATFORM.qq.color
  if (['wecom_webhook', 'serverchan', 'pushplus', 'wxpusher'].includes(kind)) return PLATFORM.wechat.color
  if (kind.startsWith('email')) return '#ffb020'
  if (kind === 'local_archive') return '#a9c4dd'
  if (platformLabel === '飞书') return PLATFORM.feishu.color
  if (platformLabel === '微信') return PLATFORM.wechat.color
  if (platformLabel === 'QQ') return PLATFORM.qq.color
  return '#a9c4dd'
}
