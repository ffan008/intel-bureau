/**
 * v2 风险标注（docs/V2_KNOWLEDGE.md §2）：风险内容照常提取、扩展、可进头条，只加标注和固定免责声明。
 * 只有「违法高危」用红色；其它类别用柔和的琥珀色，只作提示。
 */
export const RISK_DISCLAIMER = '⚠️ 风险提示：以上内容整理自群聊讨论与公开资料，仅供学习研究。涉及平台规则、账号与资金的操作可能违反服务条款或带来损失，是否采用请自行判断并承担责任。'

export const SEVERE_RISK = '违法高危'
/** §2 表格里的风险类别（展示顺序） */
export const RISK_LABELS = ['合规风险', '平台规则', '账号风险', '金钱风险', '广告引流', '版权风险', '未核实', SEVERE_RISK] as const

export const isSevereRisk = (flag: string): boolean => flag.includes(SEVERE_RISK)
export const hasSevereRisk = (flags: readonly string[] | undefined): boolean => !!flags?.some(isSevereRisk)
/** 文本里是否已经带了固定免责声明（后端会写进 body_md 末尾；没写时前端补一份） */
export const hasDisclaimer = (md: string | undefined | null): boolean => !!md && md.includes('风险提示：以上内容整理自群聊讨论与公开资料')

/** 风险标签排序：违法高危在前，其余按 RISK_LABELS 顺序，未知标签在后 */
export function sortRisks(flags: readonly string[]): string[] {
  const rank = (f: string) => (isSevereRisk(f) ? -1 : (RISK_LABELS as readonly string[]).indexOf(f) + 1 || 99)
  return [...new Set(flags)].sort((a, b) => rank(a) - rank(b))
}
