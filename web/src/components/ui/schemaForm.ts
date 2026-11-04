import type { ConfigField } from '@/api/types'

export const isMasked = (v: unknown): boolean => typeof v === 'string' && v.startsWith('••')

/** 由 schema + 当前配置得到表单初值。secret 字段初值为空串（= 不修改），掩码放进 masks 当占位符。 */
export function initForm(fields: ConfigField[], current: Record<string, unknown> = {}) {
  const values: Record<string, unknown> = {}
  const masks: Record<string, string> = {}
  for (const f of fields) {
    const cur = current[f.key]
    if (f.type === 'secret') {
      values[f.key] = ''
      if (typeof cur === 'string' && cur) masks[f.key] = cur
    } else if (f.type === 'bool') values[f.key] = typeof cur === 'boolean' ? cur : f.default === true
    else if (f.type === 'number') values[f.key] = typeof cur === 'number' ? cur : typeof f.default === 'number' ? f.default : ''
    else values[f.key] = cur ?? f.default ?? (f.type === 'select' ? f.options?.[0]?.value ?? '' : '')
  }
  return { values, masks }
}

export function validateForm(fields: ConfigField[], values: Record<string, unknown>, masks: Record<string, string>): Record<string, string> {
  const errs: Record<string, string> = {}
  for (const f of fields) {
    const v = values[f.key]
    const empty = v === '' || v === undefined || v === null
    if (f.required && empty && !(f.type === 'secret' && masks[f.key])) errs[f.key] = `请填写${f.label}`
    else if (!empty && f.type === 'url' && !/^https?:\/\/[^\s]+$/i.test(String(v))) errs[f.key] = '需要以 http:// 或 https:// 开头的地址'
    else if (!empty && f.type === 'number' && !Number.isFinite(Number(v))) errs[f.key] = '需要是数字'
  }
  return errs
}

/** 表单值 → 提交用的 config。secret 留空表示不修改（API.md 约定，发空串）。 */
export function serializeForm(fields: ConfigField[], values: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of fields) {
    const v = values[f.key]
    if (f.type === 'number') out[f.key] = v === '' || v === null || v === undefined ? null : Number(v)
    else if (f.type === 'bool') out[f.key] = !!v
    else out[f.key] = typeof v === 'string' ? v.trim() : v ?? ''
  }
  return out
}
