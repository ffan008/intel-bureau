/** 12 个阶段的剧本：时长、日志、逐步变化的指标。模拟运行和历史日志共用。 */
import type { ChannelDTO, IntelItemDTO, LogDTO, StageName, StatsDTO } from '@/api/types'
import { STAGE_AGENT } from '@/utils/meta'
import { WHITELIST } from './data/groups'
import { between, fmtN, iso, rng } from './util'

export interface ScriptLog { at: number; level?: LogDTO['level']; text: string; metrics?: Record<string, number | string>; channel?: string }
export interface StageScript { name: StageName; duration: number; logs: ScriptLog[]; final: Record<string, number | string>; message: string }
export interface PlanCtx { stats: StatsDTO; items: IntelItemDTO[]; channels: ChannelDTO[]; seed: number; failChannel?: string }
export interface PlanResult { stages: StageScript[]; totals: { chunks: number; candidates: number; tokens_in: number; tokens_out: number; cost_cny: number } }

const PL: Record<string, string> = { wechat: '微信', qq: 'QQ', feishu: '飞书' }

export function buildPlan(c: PlanCtx): PlanResult {
  const r = rng(c.seed)
  const dur = (lo: number, hi: number) => Math.round(between(r, lo, hi))
  const raw = c.stats.messages_raw, clean = c.stats.messages_clean
  const threads = Math.round(clean / 6.4), chunks = Math.min(38, Math.max(12, Math.round(clean / 34)))
  const cands = Math.round(c.items.length * 3.6), topics = c.items.length + 3
  const tIn = chunks * 2350 + 14200, tOut = Math.round(cands * 190 + 3800)
  const cost = Math.round(((tIn * 2 + tOut * 8) / 1e6) * 100) / 100
  const S: StageScript[] = []

  // 1 collect
  let acc = 0
  const perPlat: Record<string, number> = { wechat: 0, qq: 0, feishu: 0 }
  const cl: ScriptLog[] = [{ at: 0.04, text: `连接 3 个平台：微信 WDA · QQ NapCat · 飞书 lark-cli` }]
  WHITELIST.forEach((g, i) => {
    const n = c.stats.top_groups.find((x) => x.name === g.name)?.messages ?? g.m24
    acc += n; perPlat[g.platform] = (perPlat[g.platform] ?? 0) + n
    cl.push({ at: 0.1 + (i * 0.8) / WHITELIST.length, text: `${PL[g.platform]}「${g.name}」拉取 ${fmtN(n)} 条 · 游标已前移`, metrics: { messages: acc, wechat: perPlat.wechat!, qq: perPlat.qq!, feishu: perPlat.feishu! } })
    if (g.platform === 'feishu' && i === 7) cl.push({ at: 0.12 + (i * 0.8) / WHITELIST.length, level: 'warn', text: '飞书用户身份令牌已过期，回退到机器人身份（只读机器人所在群）' })
  })
  cl.push({ at: 0.97, text: `合并实时上报 ${fmtN(Math.round(raw * 0.04))} 条，去重后共 ${fmtN(raw)} 条` })
  S.push({ name: 'collect', duration: dur(2000, 2500), logs: cl, final: { messages: raw, ...perPlat, failed_groups: 0 }, message: `采集 9 个群 · ${fmtN(raw)} 条` })

  // 2 clean
  const sys = Math.round(raw * 0.05), low = Math.round(raw * 0.39), dup = Math.round(raw * 0.035)
  S.push({ name: 'clean', duration: dur(1200, 1600), message: `清洗 ${fmtN(raw)} → ${fmtN(clean)}`, final: { messages_raw: raw, messages_clean: clean, snr: c.stats.snr }, logs: [
    { at: 0.1, text: `剔除系统消息 / 撤回 / 拍一拍 ${fmtN(sys)} 条，红包 ${Math.round(sys * 0.2)} 条` },
    { at: 0.35, text: `低信息消息（收到 / 好的 / 哈哈 / +1 / 纯表情）${fmtN(low)} 条`, metrics: { messages_clean: raw - sys - low } },
    { at: 0.6, text: `跨群重复文本合并 ${dup} 组，最高扩散度 3 群` },
    { at: 0.82, text: `抽取 URL ${Math.round(clean * 0.08)} 个；脱敏手机号 ${Math.round(r() * 6 + 2)} 处、邮箱 ${Math.round(r() * 3 + 1)} 处` },
    { at: 0.96, text: `有效 ${fmtN(clean)} / ${fmtN(raw)} · 信噪比 ${(c.stats.snr * 100).toFixed(1)}%`, metrics: { messages_clean: clean, snr: c.stats.snr } },
  ] })

  // 3 stats
  const top = c.stats.rising[0]
  S.push({ name: 'stats', duration: dur(900, 1200), message: `统计关键词与上升信号`, final: { keywords: c.stats.keywords.length, rising: c.stats.rising.length, speakers: c.stats.speakers }, logs: [
    { at: 0.15, text: `jieba 分词（加载自定义词典 312 词），TF-IDF 关键词 ${c.stats.keywords.length} 个`, metrics: { keywords: c.stats.keywords.length } },
    { at: 0.5, text: `与 7 日 keyword_daily 比较：上升信号 ${c.stats.rising.length} 个${top ? `，最高「${top.word}」z=${top.z.toFixed(1)}` : ''}`, metrics: { rising: c.stats.rising.length } },
    { at: 0.85, text: `活跃热力 7×24、发言榜 TOP 10、群热度已生成（发言人 ${c.stats.speakers}）` },
  ] })

  // 4 segment
  S.push({ name: 'segment', duration: dur(800, 1100), message: `切分 ${threads} 个线程 → ${chunks} 块`, final: { threads, chunks }, logs: [
    { at: 0.2, text: `按 20 分钟间隔与回复链切分线程 ${threads} 个`, metrics: { threads } },
    { at: 0.75, text: `打包为 ${chunks} 块（每块 ≤ 6,000 字），消息已编号 [m1]…[m${clean}]`, metrics: { threads, chunks } },
  ] })

  // 5 extract
  const el: ScriptLog[] = [{ at: 0.03, text: `调用模型 deepseek-chat · 并发 3 · 预算 ${chunks}/40 块` }]
  const shown = Math.min(9, chunks)
  for (let i = 0; i < shown; i++) {
    const g = WHITELIST[i % WHITELIST.length]!
    const done = Math.round(((i + 1) / shown) * chunks)
    const cc = Math.round(((i + 1) / shown) * cands)
    const cached = i === 2 || i === 6
    el.push({ at: 0.08 + (i * 0.86) / shown, text: `解析 群「${g.name}」块 ${done}/${chunks} → 候选 ${Math.max(1, Math.round(cands / shown + (r() - 0.5) * 3))} 条${cached ? '（缓存命中）' : ''}`,
      metrics: { chunks_done: done, chunks, candidates: cc, tokens_in: Math.round((tIn - 14200) * (done / chunks)), tokens_out: Math.round((tOut - 3800) * (done / chunks)) } })
  }
  S.push({ name: 'extract', duration: dur(2200, 2500), logs: el, message: `抽取候选 ${cands} 条`, final: { chunks_done: chunks, chunks, candidates: cands, tokens_in: tIn - 14200, tokens_out: tOut - 3800 } })

  // 6 merge  7 score
  const h = c.items.filter((i) => i.is_headline).length, fe = c.items.filter((i) => i.is_feature).length
  const risky = c.items.filter((i) => i.risk_flags.length)
  S.push({ name: 'merge', duration: dur(900, 1200), message: `合并为 ${topics} 个话题`, final: { candidates: cands, topics }, logs: [
    { at: 0.25, text: `标题 + 关键词 Jaccard ≥ 0.42：${cands} 条候选 → ${topics} 个话题`, metrics: { topics } },
    { at: 0.7, text: `跨群合并：「${c.items[0]?.title.slice(0, 18) ?? ''}…」来自 ${c.items[0]?.sources.length ?? 1} 个群` },
  ] })
  const n = (t: string) => c.items.filter((i) => i.trend === t).length
  S.push({ name: 'score', duration: dur(1000, 1300), message: `头条 ${h} · 专题 ${fe}`, final: { headlines: h, features: fe, new: n('new'), developing: n('developing'), repeat: n('repeat') }, logs: [
    { at: 0.2, text: `对比 topic_memory：新出现 ${n('new')} · 持续发酵 ${n('developing')} · 重复 ${n('repeat')}` },
    ...risky.slice(0, 2).map((x, i) => ({ at: 0.45 + i * 0.15, level: 'warn' as const, text: `风险降权「${x.title.slice(0, 16)}…」${x.risk_flags.join('/')}` })),
    { at: 0.9, text: `选出头条 TOP ${h}、专题 ${fe} 篇，最高分 ${c.items[0]?.score.toFixed(1) ?? '—'}`, metrics: { headlines: h, features: fe } },
  ] })

  // 8 verify
  const dropped = topics - c.items.length
  S.push({ name: 'verify', duration: dur(1000, 1400), message: `核验通过 ${c.items.length} 条`, final: { passed: c.items.length, dropped, unverified: risky.filter((x) => x.risk_flags.includes('未核实')).length }, logs: [
    { at: 0.2, text: `证据摘录与原文比对 ${c.items.reduce((a, i) => a + i.evidence.length, 0)} 处，全部为原文子串` },
    { at: 0.5, text: `URL 来源校验 ${c.items.reduce((a, i) => a + i.links.length, 0)} 个；非 http(s) 链接 1 个已拦截`, level: 'warn' },
    { at: 0.8, text: `剔除无有效证据 ${dropped} 条；原文找不到的数字标「待核实」${risky.filter((x) => x.risk_flags.includes('未核实')).length} 处`, metrics: { passed: c.items.length, dropped } },
  ] })

  // 9 compose  10 render
  S.push({ name: 'compose', duration: dur(1800, 2300), message: `撰写今日风向与专题`, final: { judgments: 4, features: fe, tokens_in: 14200, tokens_out: 3800 }, logs: [
    { at: 0.1, text: `调用 compose 模板：今日风向 4 条 + 专题深读 ${fe} 篇` },
    { at: 0.55, text: `风向判断已生成，依据已绑定到情报与 z 值`, metrics: { tokens_in: 14200, tokens_out: 2100 } },
    { at: 0.92, text: `本次 tokens：输入 ${fmtN(tIn)} · 输出 ${fmtN(tOut)} · 约 ¥${cost.toFixed(2)}`, metrics: { tokens_in: 14200, tokens_out: 3800 } },
  ] })
  const bytes = 38000 + c.items.length * 2400
  S.push({ name: 'render', duration: dur(800, 1100), message: `生成 MD / HTML / JSON`, final: { bytes, summary_chars: 1640 }, logs: [
    { at: 0.3, text: `完整版 Markdown ${(bytes / 1024).toFixed(1)} KB · 深色 HTML ${(bytes * 2.6 / 1024).toFixed(1)} KB · JSON`, metrics: { bytes } },
    { at: 0.75, text: `推送精简版 1,640 字（≤ 1,800）` },
  ] })

  // 11 deliver  12 archive
  const chs = c.channels.filter((x) => x.enabled)
  const ok = chs.filter((x) => x.id !== c.failChannel).length
  S.push({ name: 'deliver', duration: dur(1400, 1800), message: `投递 ${chs.length} 个通道`, final: { delivered: ok, failed: chs.length - ok }, logs: [
    { at: 0.05, text: `并发投递 ${chs.length} 个通道` },
    ...chs.map((ch, i) => ({ at: 0.2 + (i * 0.7) / chs.length, level: (ch.id === c.failChannel ? 'error' : 'info') as LogDTO['level'], channel: ch.id,
      text: ch.id === c.failChannel ? `${ch.name} ✗ NapCat 未登录，已重试 2 次` : `${ch.name} ✓ ${ch.kind === 'qq_onebot' ? '已发送 3 段' : ch.kind === 'feishu_webhook' ? '卡片 2 段' : '已送达'}`,
      metrics: { delivered: chs.slice(0, i + 1).filter((x) => x.id !== c.failChannel).length, failed: chs.slice(0, i + 1).filter((x) => x.id === c.failChannel).length } })),
  ] })
  S.push({ name: 'archive', duration: dur(800, 1100), message: `归档报告、更新话题记忆`, final: { archived: 1, topics: c.items.length }, logs: [
    { at: 0.25, text: `报告已归档 · topic_memory +${n('new')} · keyword_daily 更新 ${c.stats.keywords.length} 词` },
    { at: 0.7, text: `按保留期 30 天清理原始消息 ${fmtN(Math.round(raw * 0.42))} 条`, metrics: { archived: 1 } },
  ] })
  return { stages: S, totals: { chunks, candidates: cands, tokens_in: tIn, tokens_out: tOut, cost_cny: cost } }
}

/** 历史运行的完整日志 */
export function planLogs(plan: PlanResult, runId: string, startMs: number): LogDTO[] {
  const out: LogDTO[] = []
  let t = startMs
  for (const s of plan.stages) {
    for (const l of s.logs) out.push({ ts: iso(t + l.at * s.duration * 6), level: l.level ?? 'info', source: `pipeline.${s.name}`, message: l.text, run_id: runId, stage: s.name })
    t += s.duration * 6
  }
  return out
}
export const agentOf = (s: StageName) => STAGE_AGENT[s]
