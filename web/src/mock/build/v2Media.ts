/** v2 mock：图片（SVG data: URL，模拟 OCR 要点与出处）与文档（模拟正文提炼） */
import type { ArticleDTO, MediaDTO } from '@/api/types'
import { barChart, cards, chatShot, flow, line, table } from './svg'

interface ImgSpec { name: string; who: string; seq: number; why: string; ocr: string[]; draw: () => string }
const IMAGES: ImgSpec[] = [
  { name: 'm0101.png', who: '老K', seq: 1, why: '6 路 worktree 合并记录截图，能看到冲突只有 2 处', ocr: ['git worktree add ../wt-01 … ../wt-06', '合并顺序：wt-03 → wt-01 → wt-05 → wt-02 → wt-06 → wt-04', 'CONFLICT (content): src/core/router.ts', '40 TODO 已关闭，用时 2h51m'],
    draw: () => chatShot('Claude Code 实战营 · 合并记录', [{ who: '老K', text: '6 个 worktree 全部合完了' }, { who: '老K', text: '冲突只有 router.ts 两处' }, { who: 'Leo', text: '目录约束写进 CLAUDE.md 了吗' }, { who: '老K', text: '写了，每个只能改自己的模块', me: true }]) },
  { name: 'm0201.png', who: '画画的阿木', seq: 2, why: '两步法流程图：先锁线稿，再拿线稿当参考图上色', ocr: ['STEP 1 固定角色设定词', 'STEP 2 只出线稿，挑一张', 'STEP 3 线稿作参考图上色', 'STEP 4 同系列只改动作和场景'],
    draw: () => flow('线稿上色两步法', ['固定角色设定词', '只出线稿挑一张', '线稿作参考上色', '只改动作和场景'], '连续 12 张五官基本不漂移（群友自述）') },
  { name: 'm0202.png', who: '十三', seq: 2, why: 'ComfyUI 节点参数截图：ControlNet 强度 0.6、分块 VAE 解码', ocr: ['flux1-dev-fp8', 'ControlNet lineart strength 0.60', 'Tiled VAE Decode tile 512', '显存峰值 11.2 GB'],
    draw: () => table('ComfyUI · 线稿上色参数', ['节点', '参数', '值'], [['Load Checkpoint', 'model', 'flux1-dev-fp8'], ['ControlNet', 'strength', '0.60'], ['ControlNet', 'end', '0.80'], ['VAE Decode', 'tiled', '512'], ['KSampler', 'steps / cfg', '24 / 3.5'], ['显存峰值', '3060 12G', '11.2 GB']]) },
  { name: 'm0301.png', who: '阿青', seq: 3, why: '多图融合示意：三张参考图各取所需', ocr: ['图1 人物（正脸）', '图2 服装（平铺）', '图3 场景', '10 次成功 8 次'],
    draw: () => cards('多图融合 · 逐张点名', [{ label: '图1 人物', color: '#22e4ff' }, { label: '图2 服装', color: '#8b5cff' }, { label: '图3 场景', color: '#ffb020' }], '融合结果') },
  { name: 'm0401.png', who: '数据狗', seq: 4, why: 'A/B 测试完播率对比图', ocr: ['A 版（原开头）完播率 18%', 'B 版（冲突前置）完播率 31%', '各投放 48 小时，样本 2 万+'],
    draw: () => barChart('TikTok 短剧 A/B · 完播率', [{ label: 'A 版 原开头', value: 18, color: '#6c86a3' }, { label: 'B 版 冲突前置', value: 31, color: '#22e4ff' }], '%') },
  { name: 'm0501.png', who: 'Kevin', seq: 5, why: '三段式运镜提示词对照表', ocr: ['镜头：缓慢推近，全景 → 中景', '节奏：前 2 秒静止，之后匀速', '主体：转身看向镜头'],
    draw: () => table('可灵运镜三段式', ['段落', '只写什么', '示例'], [['镜头', '镜头怎么动', '缓慢推近，全景到中景'], ['节奏', '多快、何时停', '前 2 秒静止，之后匀速'], ['主体', '主体做什么', '转身看向镜头，微笑']]) },
  { name: 'm0701.png', who: 'Kevin', seq: 7, why: '字幕本地化单集成本对比', ocr: ['外包翻译 约 35 元/集', '流水线 约 3 元/集', '交付 3 天 → 半天'],
    draw: () => barChart('西语字幕 · 单集成本（元）', [{ label: '外包翻译', value: 35, color: '#6c86a3' }, { label: '转写 + 模型翻译', value: 3, color: '#2bff9a' }]) },
  { name: 'm0901.png', who: '七七', seq: 9, why: '绘本号 30 天粉丝曲线', ocr: ['第 1 天 0', '第 12 天 1,180（单篇 1.1 万赞）', '第 30 天 4,200'],
    draw: () => line('小红书绘本号 · 30 天粉丝', [0, 40, 95, 160, 240, 330, 520, 780, 1180, 1500, 1820, 2150, 2480, 2790, 3100, 3380, 3650, 3900, 4200], '第 12 天单篇 1.1 万赞后增速明显加快') },
  { name: 'm1101.png', who: '大飞', seq: 11, why: '数字人账号播放量断崖', ocr: ['第 1 天 平均播放 3,100', '第 2 天 2,800', '第 3 天 760', '第 4 天 190'],
    draw: () => barChart('视频号数字人 · 日均播放', [{ label: '第 1 天', value: 3100, color: '#22e4ff' }, { label: '第 2 天', value: 2800, color: '#22e4ff' }, { label: '第 3 天', value: 760, color: '#ffb020' }, { label: '第 4 天', value: 190, color: '#ff4d5e' }]) },
]

const FILES: { name: string; seq?: number; why: string; summary: string; srcSeq?: number; group?: string; sender?: string }[] = [
  { name: '子Agent并行开发SOP.pdf', seq: 1, why: '老K 整理的完整流程，12 页', summary: '- worktree 命名：`wt-{任务编号}`，分支同名\n- 每个子 Agent 的 CLAUDE.md 模板（目录范围、禁止改的文件、提交规范）\n- 合并顺序按依赖图排列，每合并一路跑一次测试\n- 附录：冲突处理清单和回滚步骤' },
  { name: '短剧AB测试数据.xlsx', seq: 4, why: 'A/B 两版的逐小时投放数据', summary: '- 两个工作表：A 版、B 版，各 48 行（每小时一行）\n- 字段：曝光、3 秒留存、完播、点赞、评论\n- B 版 3 秒留存 62%，A 版 41%（群友自述数据）' },
  { name: '漫画分镜模板.docx', seq: 10, why: '分镜表模板，配合拆分镜提示词使用', summary: '- 表格五列：格号、景别、画面动作、台词、备注\n- 预置远 / 全 / 中 / 近 / 特写的构图示意\n- 一页 8 格，两页为一话' },
  { name: '封面工具需求调研.md', why: '小红书起号营整理的封面批量工具需求', summary: '- 12 位博主回复，9 位每天做 10 张以上封面\n- 需求：批量导入标题、自动套模板、换字体和配色\n- 付费意愿：一次性 300~500 元（群友自述）', group: '小红书起号营', sender: '七七' },
]

/** 出处取对应专题的第一条来源 */
export function buildMedia(articles: ArticleDTO[]): MediaDTO[] {
  const src = (seq?: number, who?: string) => {
    const xs = articles.find((a) => a.seq === seq)?.sources ?? []
    return xs.find((x) => x.sender === who) ?? xs[0]
  }
  const imgs = IMAGES.map((m): MediaDTO => {
    const s = src(m.seq, m.who)
    return { kind: 'image', name: m.name, url: m.draw(), ocr_text: m.ocr.join('\n'), why: m.why, group_name: s?.group_name, sender: s?.sender, sent_at: s?.sent_at, article_seq: m.seq }
  })
  const files = FILES.map((f): MediaDTO => {
    const s = src(f.seq)
    return { kind: 'file', name: f.name, summary: f.summary, why: f.why, group_name: f.group ?? s?.group_name, sender: f.sender ?? s?.sender,
      sent_at: s?.sent_at ?? articles[0]?.sources[0]?.sent_at, article_seq: f.seq }
  })
  return [...imgs, ...files]
}
/** 每篇专题的配图名（与 MediaDTO.name 对应） */
export const imagesOf = (seq: number): string[] => IMAGES.filter((m) => m.seq === seq).map((m) => m.name)
