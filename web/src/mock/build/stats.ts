/** 统计面板：小时分布、7×24 热力、消息构成、群热度、发言榜、词云、上升信号 */
import type { Platform, StatsDTO } from '@/api/types'
import { SPEAKERS, WHITELIST, groupKey } from '../data/groups'
import { between, rng, shuffle } from '../util'

/** 一天 24 小时的活跃曲线（午间与晚间两个峰） */
export const HOUR_CURVE = [0.9, 0.5, 0.3, 0.2, 0.15, 0.2, 0.5, 1.4, 2.6, 3.8, 4.6, 4.9, 5.2, 4.2, 4.1, 4.4, 4.6, 4.5, 4.3, 5.1, 6.3, 6.8, 5.6, 2.8]
const CURVE_SUM = HOUR_CURVE.reduce((a, b) => a + b, 0)

const KEYWORDS: [string, number, 'up' | 'flat' | 'new'][] = [
  ['子 Agent', 96, 'up'], ['worktree', 88, 'up'], ['冲突前置', 74, 'new'], ['线稿上色', 70, 'up'], ['Claude Code', 92, 'flat'],
  ['多图融合', 66, 'new'], ['完播率', 63, 'up'], ['AI 分镜', 58, 'new'], ['字幕本地化', 55, 'up'], ['hooks', 52, 'up'],
  ['提示词', 85, 'flat'], ['ComfyUI', 61, 'flat'], ['即梦', 64, 'flat'], ['可灵', 60, 'flat'], ['小红书', 72, 'flat'],
  ['短剧出海', 57, 'flat'], ['数字人', 46, 'flat'], ['工作流', 68, 'flat'], ['n8n', 44, 'new'], ['多维表格', 42, 'flat'],
  ['绘本号', 40, 'up'], ['Flux', 48, 'flat'], ['ControlNet', 39, 'flat'], ['Nano Banana', 50, 'new'], ['DeepSeek', 47, 'flat'],
  ['TikTok', 45, 'flat'], ['公众号', 43, 'flat'], ['视频号', 38, 'flat'], ['起号', 41, 'flat'], ['变现', 49, 'flat'],
  ['角色一致性', 53, 'up'], ['CLAUDE.md', 37, 'up'], ['动态预览', 33, 'new'], ['CosyVoice', 31, 'new'], ['Whisper', 34, 'flat'],
  ['MCP', 36, 'flat'], ['Skill', 35, 'flat'], ['Cursor', 33, 'flat'], ['Codex', 30, 'flat'], ['开源', 32, 'flat'],
  ['自动化', 40, 'flat'], ['选题', 37, 'flat'], ['封面', 34, 'up'], ['日结', 29, 'new'], ['训练营', 28, 'flat'],
  ['学生认证', 27, 'flat'], ['退款', 26, 'flat'], ['夜间折扣', 25, 'new'], ['缓存', 24, 'flat'], ['量化', 23, 'flat'],
  ['Ollama', 26, 'flat'], ['Qwen3', 25, 'flat'], ['口型', 24, 'flat'], ['Suno', 22, 'flat'], ['漫画', 31, 'flat'],
  ['分镜脚本', 29, 'up'], ['剪映', 27, 'flat'], ['限流', 30, 'flat'], ['推荐量', 22, 'flat'], ['海报', 21, 'flat'],
  ['显存', 20, 'flat'], ['lint', 19, 'flat'], ['Midjourney', 23, 'flat'], ['西语', 18, 'new'],
]

const RISING: StatsDTO['rising'] = [
  { word: '子 Agent', today: 46, avg7: 6.1, z: 4.1, groups: ['Claude Code 实战营', '飞书 · 增长小组'], spark: [4, 5, 6, 5, 9, 14, 46] },
  { word: '冲突前置', today: 21, avg7: 1.3, z: 3.6, groups: ['短剧出海交流'], spark: [0, 1, 2, 1, 2, 3, 21] },
  { word: 'worktree', today: 31, avg7: 4.7, z: 3.4, groups: ['Claude Code 实战营'], spark: [3, 4, 6, 3, 5, 8, 31] },
  { word: '线稿上色', today: 27, avg7: 6.9, z: 2.9, groups: ['水彩手绘研习社', 'ComfyUI 工作流研究'], spark: [5, 6, 8, 7, 6, 10, 27] },
  { word: 'AI 分镜', today: 14, avg7: 2.4, z: 2.6, groups: ['短剧出海交流', 'AI 出图研究所'], spark: [1, 2, 3, 2, 4, 5, 14] },
  { word: '多图融合', today: 18, avg7: 5.1, z: 2.3, groups: ['AI 出图研究所', '小红书起号营'], spark: [4, 5, 4, 6, 7, 8, 18] },
  { word: 'hooks', today: 12, avg7: 3.6, z: 2.1, groups: ['Claude Code 实战营'], spark: [2, 3, 4, 3, 5, 4, 12] },
]

export function buildStats(seed: number, scale = 1): StatsDTO {
  const r = rng(seed)
  const perGroup = WHITELIST.map((g) => ({ g, n: Math.round(g.m24 * scale * between(r, 0.86, 1.12)), sp: Math.round(g.speakers * between(r, 0.85, 1.1)) }))
  const raw = perGroup.reduce((a, x) => a + x.n, 0)
  const snr = Math.round(between(r, 0.39, 0.44) * 1000) / 1000
  const plats: Platform[] = ['wechat', 'qq', 'feishu']
  const byPlat = plats.map((p) => ({ platform: p, messages: perGroup.filter((x) => x.g.platform === p).reduce((a, x) => a + x.n, 0), groups: perGroup.filter((x) => x.g.platform === p).length }))
  const hourly = HOUR_CURVE.map((c, hour) => {
    const row = { hour, wechat: 0, qq: 0, feishu: 0, demo: 0 }
    for (const b of byPlat) {
      const bias = b.platform === 'feishu' ? (hour >= 9 && hour <= 18 ? 1.8 : 0.35) : 1
      row[b.platform] = Math.max(0, Math.round((b.messages * c * bias) / CURVE_SUM * between(r, 0.8, 1.2)))
    }
    return row
  })
  const heat: [number, number, number][] = []
  for (let d = 0; d < 7; d++) {
    const dayF = (0.72 + d * 0.05) * (d === 6 ? 1.18 : 1)
    for (let h = 0; h < 24; h++) heat.push([d, h, Math.max(0, Math.round((raw * HOUR_CURVE[h]! * dayF) / CURVE_SUM * between(r, 0.7, 1.3)))])
  }
  const typeW: [string, number][] = [['text', 0.62], ['image', 0.14], ['reply', 0.08], ['link', 0.06], ['sticker', 0.05], ['card', 0.02], ['file', 0.012], ['video', 0.01], ['voice', 0.008]]
  const msg_types = typeW.map(([kind, w]) => ({ kind, count: Math.round(raw * w * between(r, 0.9, 1.1)) }))
  const maxN = Math.max(...perGroup.map((x) => x.n))
  const top_groups = perGroup
    .map(({ g, n, sp }) => ({ group_key: groupKey(g), name: g.name, platform: g.platform, messages: n, speakers: sp, heat: Math.round((n / maxN) * 70 + (sp / 90) * 30) }))
    .sort((a, b) => b.heat - a.heat)
  const top_speakers = shuffle(r, SPEAKERS).slice(0, 10).map((name, i) => ({
    name, group_name: perGroup[(i * 4) % perGroup.length]!.g.name, messages: Math.round(between(r, 18, 64) * (1 - i * 0.06) * scale),
  })).sort((a, b) => b.messages - a.messages)
  const keywords = KEYWORDS.map(([word, w, trend]) => ({ word, weight: Math.round(w * between(r, 0.9, 1.1)), trend }))
  const rising = RISING.slice(0, 6).map((x) => ({ ...x, today: Math.round(x.today * scale), spark: [...x.spark.slice(0, 6), Math.round(x.today * scale)] }))
  return {
    messages_raw: raw, messages_clean: Math.round(raw * snr), snr, speakers: Math.round(perGroup.reduce((a, x) => a + x.sp, 0) * 0.86),
    by_platform: byPlat, hourly, heat_7x24: heat, msg_types, top_groups, top_speakers, keywords, rising,
  }
}

/** 往期报告的统计：同一套结构，换种子与规模 */
export const historyStats = (seed: number) => buildStats(seed, between(rng(seed), 0.75, 1.05))
