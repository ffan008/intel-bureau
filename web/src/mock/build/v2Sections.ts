/** v2 mock：纯 Markdown 板块（总览、提示词、SOP、工具、数据、风险、金句、快讯）与计数 */
import type { ArticleDTO, IntelItemDTO, ReportDTO, SectionKey } from '@/api/types'
import { RISK_DISCLAIMER } from '@/utils/risk'
import { mdhm } from '../util'
import { ARTICLE_SPECS, PL, evidenceFor, pad2, promptGroup } from './v2Articles'
import { SEEDS, seedIndexOfItem } from './items'

const t = (iso?: string) => (iso ? mdhm(Date.parse(iso)) : '')
const link = (seq: number) => `[专题 ${pad2(seq)}](#article-${seq})`

const TOOLS: [tool: string, seq: number, scene: string, verdict: string][] = [
  ['Claude Code + git worktree', 1, '6 路并行清理 40 个 TODO', '耦合低时很快；同一批核心文件的重构收益下降'],
  ['Flux fp8 + ControlNet lineart', 2, '3060 12G 线稿上色', '1024 可跑；强度 0.6 左右最自然'],
  ['Nano Banana', 3, '小红书换装图', '逐张点名用途，10 次成 8 次'],
  ['可灵', 5, '图生视频运镜', '三段式写法镜头更听话'],
  ['Whisper large-v3', 7, '短剧原声转写', '转写准确，人名需要在翻译时约束'],
  ['n8n', 8, '每日内容草稿', '配图提示词单独一个节点效果更好'],
  ['Claude Code hooks', 6, '改完自动跑 lint 和测试', '失败输出回传给 Agent 自己修；测试慢时只跑相关用例'],
]
const DATA: [what: string, val: string, seq: number][] = [
  ['合并冲突', '40 个 TODO 只冲突 2 处', 1], ['连续出图一致性', '12 张五官基本不漂移', 2], ['多图融合成功率', '10 次成 8 次', 3],
  ['TikTok 短剧完播率', '18% → 31%（各 48 小时，样本 2 万+）', 4], ['西语字幕成本', '约 3 元 / 集，交付 3 天 → 半天', 7],
  ['绘本号涨粉', '30 天 +4,200，单篇最高 1.1 万赞', 9], ['数字人账号播放', '第 3 天起断崖', 11], ['训练营收费', '2,980 元（未核实）', 12],
]
/** 金句：[专题序号, 发言人]，原文和出处都从证据里取 */
const QUOTES: [seq: number, who: string][] = [[1, 'Leo'], [2, '小鹿酱'], [11, '十三'], [9, '沐沐'], [10, '小鹿酱'], [4, '数据狗']]

export function buildSections(rep: ReportDTO, items: IntelItemDTO[], articles: ArticleDTO[]): { sections: Partial<Record<SectionKey, string>>; counts: Partial<Record<SectionKey, number>> } {
  const ev = (seq: number) => evidenceFor(items, ARTICLE_SPECS[seq - 1]?.seeds ?? [])
  // 与后端 bureau/pipeline/sections.py overview_blocks 的 Markdown 结构一致：一句话 → 数据卡一行 → ### 今日风向 → ### 今日 N 篇专题
  const overview = ['**一句话**：多 Agent 并行开发、AI 绘画角色一致性、短剧出海精细化运营是今天跨群的三条主线；一条代开认证的违法高危话术在 3 个群出现，已只记录不扩展。', '',
    `数据卡：消息 ${rep.stats.messages_raw.toLocaleString('en-US')} · 群 ${rep.stats.top_groups.length} · 情报 ${items.length} · 专题 ${articles.length} · 资源 25`, '',
    '### 今日风向', '', ...rep.judgments.map((j, i) => `${i + 1}. **${j.text}**（依据：${j.basis}）`), '',
    `### 今日 ${articles.length} 篇专题`, '', ...articles.map((a) => `${a.seq}. ${a.title}｜${a.category}${a.risk_flags.map((f) => `〔${f}〕`).join('')}`), '',
    `> 有效消息 ${rep.stats.messages_clean.toLocaleString('en-US')} / ${rep.stats.messages_raw.toLocaleString('en-US')}（信噪比 ${(rep.stats.snr * 100).toFixed(1)}%）；隐私内容剔除 1 条`].join('\n')

  const P: string[] = []
  let nPrompt = 0
  ARTICLE_SPECS.forEach((s, i) => s.prompts?.forEach((p) => {
    const e = ev(i + 1)
    const at = e.find((x) => x.sender === p.who)?.sent_at ?? e[0]?.sent_at
    P.push(`### ${++nPrompt}. ${p.label}`, '', `> ${p.who} · ${promptGroup(p, e)} · ${t(at)}　用途：${p.use}　出自 ${link(i + 1)}`, '', '```text', p.text, '```', '')
  }))

  const S: string[] = []
  let nSop = 0
  for (const seq of [1, 2, 4, 6, 7, 8]) {
    const spec = ARTICLE_SPECS[seq - 1]!
    const who = [...new Set(ev(seq).map((e) => e.sender))].slice(0, 3).join('、')
    S.push(`### ${++nSop}. ${articles[seq - 1]!.title}`, '', `> 验证：${who}　${link(seq)}`, '', ...(spec.steps ?? SEEDS[spec.seeds[0]!]!.steps).map((x, k) => `${k + 1}. ${x}`), '')
  }

  const tools = ['| 工具 / 模型 | 谁 | 场景 | 结论 |', '|---|---|---|---|', ...TOOLS.map(([tool, seq, scene, verdict]) => {
    const e = ev(seq)[0]
    return `| ${tool} | ${e ? `${e.sender}（${e.group_name}）` : ''} | ${scene} | ${verdict}，${link(seq)} |`
  })].join('\n')

  const data = ['> 以下数字均为**群友自述，非平台口径**，未经核实。', '', '| 指标 | 数字 | 谁 · 群 · 时间 |', '|---|---|---|',
    ...DATA.map(([what, val, seq]) => { const e = ev(seq)[0]; return `| ${what} | ${val} | ${e ? `${e.sender} · ${e.group_name} · ${t(e.sent_at)}` : ''} |` })].join('\n')

  const severe = items.filter((i) => i.risk_flags.includes('违法高危'))
  const flagged = articles.filter((a) => a.risk_flags.length)
  // 出处取自证据：[踩坑, 专题序号, 发言人]
  const who = (seq: number, sender: string) => { const e = ev(seq).find((x) => x.sender === sender); return e ? `（${e.sender} · ${e.group_name} · ${t(e.sent_at)}）` : '' }
  const pits = [
    `子 Agent 不限定目录时会互相覆盖文件${who(1, 'Leo')}`, `一步出图到第 5 张左右发型开始漂移${who(2, '小鹿酱')}`,
    `数字人同模板高频发布，第 3 天起播放断崖${who(11, '大飞')}`, `付费训练营先交费后上课，退款被拖延${who(12, '鱼丸')}`,
  ]
  const risks = ['### 违法高危（只记录，不扩展）', '', ...severe.map((it) => `- \`违法高危\` **${it.title}**　${it.hook}。涉及 ${it.sources.map((s) => s.group_name).join('、')}，共 ${it.sources.reduce((a, s) => a + s.count, 0)} 条相关消息。`),
    '', '### 带风险标签的专题', '', ...flagged.map((a) => `- ${a.risk_flags.map((r) => `〔${r}〕`).join('')} ${link(a.seq)}　${a.title}`),
    '', '### 踩坑经验', '', ...pits.map((p) => `- ${p}`), '', '另有 1 条主要内容是个人手机号的消息按隐私规则剔除。', '', `> ${RISK_DISCLAIMER}`].join('\n')

  const qs = QUOTES.map(([seq, w]) => ev(seq).find((x) => x.sender === w)).filter((e): e is NonNullable<typeof e> => !!e)
  const quotes = qs.flatMap((e) => [`> ${e.quote}`, '>', `> —— ${e.sender} · ${e.group_name} · ${t(e.sent_at)}`, '']).join('\n')
  const covered = new Set(ARTICLE_SPECS.flatMap((s) => s.seeds))
  const rest = items.filter((i) => !covered.has(seedIndexOfItem(i.id)) && !i.risk_flags.includes('违法高危'))
  const briefs = rest.map((i) => `- **${i.title}**　${i.hook}（${i.sources.map((s) => `${PL[s.platform]}·${s.group_name}`).join('、')}）`).join('\n')

  return {
    sections: { overview, prompts: P.join('\n'), sops: S.join('\n'), tools, data, risks, quotes, briefs },
    counts: { overview: rep.judgments.length, prompts: nPrompt, sops: nSop, tools: TOOLS.length, data: DATA.length,
      risks: severe.length + flagged.length + pits.length, quotes: qs.length, briefs: rest.length },
  }
}
