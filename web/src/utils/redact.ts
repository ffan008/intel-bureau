/**
 * 前端脱敏预览：与 ARCHITECTURE §7 clean 阶段的规则同义（手机号、邮箱、身份证、银行卡、微信号）。
 * 只用于「系统 → 隐私」页的实时预览；真正的脱敏在后端执行。
 */
export type RedactKind = 'phone' | 'email' | 'id_card' | 'bank_card' | 'wechat_id'

export const REDACT_KINDS: { key: RedactKind; label: string; sample: string }[] = [
  { key: 'phone', label: '手机号', sample: '13812345678' },
  { key: 'email', label: '邮箱', sample: 'zhang.san@example.com' },
  { key: 'id_card', label: '身份证号', sample: '110105199003071234' },
  { key: 'bank_card', label: '银行卡号', sample: '6222 0212 3456 7890 123' },
  { key: 'wechat_id', label: '微信号', sample: 'wxid_ab12cd34ef' },
]

const RULES: Record<RedactKind, { re: RegExp; mask: (m: string) => string }> = {
  id_card: { re: /(?<!\d)\d{17}[\dXx](?!\d)/g, mask: (m) => m.slice(0, 3) + '*'.repeat(11) + m.slice(-4) },
  bank_card: { re: /(?<!\d)(?:\d[ -]?){15,18}\d(?!\d)/g, mask: (m) => { const d = m.replace(/\D/g, ''); return `${d.slice(0, 4)} **** **** ${d.slice(-4)}` } },
  phone: { re: /(?<!\d)1[3-9]\d{9}(?!\d)/g, mask: (m) => m.slice(0, 3) + '****' + m.slice(-4) },
  email: { re: /[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g, mask: (m) => { const [u, d] = m.split('@'); return `${u!.slice(0, 1)}***@${d}` } },
  wechat_id: { re: /\b(?:wxid_[a-z0-9]{6,20}|(?<=微信[号:：\s]{1,3})[a-zA-Z][-_a-zA-Z0-9]{5,19})/g, mask: (m) => m.slice(0, 2) + '***' + m.slice(-2) },
}

/** 顺序：身份证 → 银行卡 → 手机 → 邮箱 → 微信号（长的先匹配，避免被短规则截断） */
export function redact(text: string, enabled: Partial<Record<RedactKind, boolean>>): { html: string; hits: number } {
  type Seg = { s: string; hit: boolean }
  let segs: Seg[] = [{ s: text, hit: false }]
  let hits = 0
  for (const k of ['id_card', 'bank_card', 'phone', 'email', 'wechat_id'] as RedactKind[]) {
    if (!enabled[k]) continue
    const { re, mask } = RULES[k]
    segs = segs.flatMap((seg) => {
      if (seg.hit) return [seg]
      const out: Seg[] = []
      let last = 0
      for (const m of seg.s.matchAll(re)) {
        const i = m.index ?? 0
        if (i > last) out.push({ s: seg.s.slice(last, i), hit: false })
        out.push({ s: mask(m[0]), hit: true })
        hits++
        last = i + m[0].length
      }
      if (last < seg.s.length) out.push({ s: seg.s.slice(last), hit: false })
      return out
    })
  }
  const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
  return { html: segs.map((x) => (x.hit ? `<mark>${esc(x.s)}</mark>` : esc(x.s))).join(''), hits }
}
