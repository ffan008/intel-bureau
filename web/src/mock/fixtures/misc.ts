import type { DoctorCheck, LogDTO, RunDTO, ScheduleDTO } from '@/api/types'
import { nextRuns } from '@/utils/cron'
import { WHITELIST, groupKey } from '../data/groups'
import { iso, rng, pick } from '../util'
import type { PlanResult } from '../stages'
import { agentOf } from '../stages'

export function runFromPlan(o: {
  plan: PlanResult; id: string; trigger: RunDTO['trigger']; start: number; status: RunDTO['status']; dry: boolean
  winStart: number; winEnd: number; reportId?: string; raw: number; clean: number; items: number; scale?: number; error?: string
}): RunDTO {
  const k = o.scale ?? 8
  let t = o.start
  const stages = o.plan.stages.map((s) => {
    const d = s.duration * k
    const st = { name: s.name, agent: agentOf(s.name), status: (o.dry && s.name === 'deliver' ? 'skipped' : 'done') as RunDTO['stages'][number]['status'],
      started_at: iso(t), finished_at: iso(t + d), duration_ms: d, metrics: { ...s.final }, message: s.message }
    t += d
    return st
  })
  return {
    id: o.id, trigger: o.trigger, status: o.status, dry_run: o.dry, window_start: iso(o.winStart), window_end: iso(o.winEnd),
    started_at: iso(o.start), finished_at: iso(t), stages, report_id: o.reportId, error: o.error,
    schedule_id: o.trigger === 'schedule' ? 'sch-morning' : undefined,
    totals: { messages_raw: o.raw, messages_clean: o.clean, chunks: o.plan.totals.chunks, candidates: o.plan.totals.candidates, items: o.items,
      tokens_in: o.plan.totals.tokens_in, tokens_out: o.plan.totals.tokens_out, cost_cny: o.plan.totals.cost_cny, llm_provider: 'openai_compat' },
  }
}

export function initialSchedules(now: number, lastRun?: RunDTO): ScheduleDTO[] {
  const next = (cron: string) => nextRuns(cron, 1, 'Asia/Shanghai', now)[0]?.toISOString()
  const cc = WHITELIST.find((g) => g.id === 'cc')!, growth = WHITELIST.find((g) => g.id === 'growth')!
  return [
    { id: 'sch-morning', name: '晨报', enabled: true, cron: '0 8 * * *', timezone: 'Asia/Shanghai', window_mode: 'since_last', window_hours: 24,
      platforms: ['wechat', 'qq', 'feishu'], group_keys: [], channel_ids: ['ch-feishu-bot', 'ch-serverchan', 'ch-qq', 'ch-local'], top_n: 5, dry_run: false,
      next_run_at: next('0 8 * * *'), last_run: lastRun ? { id: lastRun.id, status: lastRun.status, finished_at: lastRun.finished_at } : undefined },
    { id: 'sch-dev', name: '编程专线 · 午晚双报', enabled: false, cron: '0 12,20 * * *', timezone: 'Asia/Shanghai', window_mode: 'fixed_hours', window_hours: 12,
      platforms: ['qq', 'feishu'], group_keys: [groupKey(cc), groupKey(growth)], channel_ids: ['ch-feishu-bot'], top_n: 3, dry_run: false, next_run_at: next('0 12,20 * * *') },
    { id: 'sch-standup', name: '工作日早会预览', enabled: true, cron: '0 9 * * mon-fri', timezone: 'Asia/Shanghai', window_mode: 'fixed_hours', window_hours: 24,
      platforms: ['feishu'], group_keys: [], channel_ids: ['ch-local'], top_n: 5, dry_run: true, next_run_at: next('0 9 * * mon-fri') },
  ]
}

export const DOCTOR: DoctorCheck[] = [
  { id: 'python', title: 'Python 运行环境', status: 'ok', detail: 'Python 3.12.7 · 虚拟环境 E:\\IntelBureau\\.venv' },
  { id: 'db', title: '数据库', status: 'ok', detail: 'data/bureau.db · WAL 模式 · 版本 3 · 38.6 MB' },
  { id: 'wechat', title: '微信采集（WeChatDataAnalysis）', status: 'ok', detail: '127.0.0.1:10392 可访问，账号已解密' },
  { id: 'wda_cors', title: 'WeChatDataAnalysis 本地 API 安全', status: 'degraded', detail: '该服务没有鉴权且开放了 CORS（*），任何网页都能读取聊天记录', hint: '运行期间不要打开不可信网页；不用时关闭 WeChatDataAnalysis' },
  { id: 'qq', title: 'QQ 采集（NapCat）', status: 'ok', detail: 'OneBot HTTP 127.0.0.1:3010 在线；实时上报签名校验已开启' },
  { id: 'feishu', title: '飞书采集（lark-cli）', status: 'degraded', detail: '用户身份令牌已于 2026-10-13 过期，当前只能读取机器人所在的群', hint: '执行 lark-cli auth login 重新登录' },
  { id: 'llm', title: '大模型', status: 'ok', detail: 'openai_compat · deepseek-chat · 最近一次调用 820ms' },
  { id: 'consent', title: '云端模型同意', status: 'ok', detail: '已同意把白名单群的聊天片段发送给云端模型（可在「智能体」页撤回）' },
  { id: 'channels', title: '推送通道', status: 'ok', detail: '4 个已启用通道最近一次投递全部成功；邮箱通道未启用' },
  { id: 'scheduler', title: '定时任务', status: 'ok', detail: '2 个任务已启用，下次运行 08:00（晨报）' },
  { id: 'claude_cli', title: 'Claude Code CLI', status: 'ok', detail: 'claude 2.1.312 可用（作为备选提供方）' },
  { id: 'disk', title: '磁盘空间', status: 'ok', detail: 'E: 剩余 214 GB；data/ 占用 412 MB' },
]

export function systemLogs(now: number, runLogs: LogDTO[]): LogDTO[] {
  const r = rng(77)
  const out: LogDTO[] = []
  const add = (minAgo: number, level: LogDTO['level'], source: string, message: string) => out.push({ ts: iso(now - minAgo * 60_000), level, source, message })
  for (let i = 0; i < 26; i++) {
    const g = pick(r, WHITELIST.filter((x) => x.platform === 'qq'))
    add(2 + i * 6.5, 'debug', 'ingest.onebot', `上报 群「${g.name}」1 条（正文前 40 字已省略）`)
  }
  add(1, 'info', 'api', 'SSE 客户端已连接（1 个）')
  add(4, 'info', 'collector.feishu', '健康检查：机器人身份可用，用户身份令牌过期')
  add(4, 'warn', 'collector.feishu', '用户身份令牌已过期，回退到机器人身份')
  add(35, 'info', 'scheduler', '下次运行：晨报 · 明天 08:00')
  add(62, 'warn', 'api', '拒绝 Host=evil.example:8765 的请求（DNS 重绑定防护）')
  add(118, 'info', 'llm', 'deepseek-chat 测试调用成功 · 820ms')
  add(240, 'error', 'channel.qq_onebot', '投递失败：NapCat 未登录（已重试 2 次）——3 天前的运行')
  add(300, 'info', 'demo', '演示数据检查：0 个演示群')
  add(420, 'info', 'scheduler', 'APScheduler 已启动，载入 3 个任务（2 个启用）')
  add(421, 'info', 'app', '情报局工作台 v1.0.0 启动 · 监听 127.0.0.1:8765')
  return [...out, ...runLogs].sort((a, b) => a.ts.localeCompare(b.ts))
}
