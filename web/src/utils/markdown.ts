/**
 * 安全渲染 Markdown（ARCHITECTURE §14）：
 * markdown-it（html:false，原始 HTML 一律当文本）→ DOMPurify 白名单消毒。
 * 链接只允许 http/https，统一 target=_blank + rel="noopener noreferrer"；其它协议的链接只保留文字。
 * 图片不渲染（报告里的图片可能是外链，也不符合 CSP img-src 'self'），只显示替代文字。
 */
import MarkdownIt from 'markdown-it'
import DOMPurify from 'dompurify'

const HTTP_RE = /^https?:\/\//i

export function safeUrl(raw: unknown): string | null {
  if (typeof raw !== 'string') return null
  const s = raw.trim()
  if (!HTTP_RE.test(s)) return null
  try {
    const u = new URL(s)
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null
  } catch {
    return null
  }
}

const md = new MarkdownIt({ html: false, linkify: true, typographer: false, breaks: true })
md.linkify.set({ fuzzyLink: false, fuzzyEmail: false })
md.validateLink = (url: string) => HTTP_RE.test(url.trim()) || url.startsWith('#')

md.renderer.rules.image = (tokens, idx) => {
  const t = tokens[idx]!
  const alt = md.utils.escapeHtml(String(t.content || t.attrGet('alt') || '图片'))
  return `<span class="md-img">[图片：${alt}]</span>`
}
const defaultLinkOpen = md.renderer.rules.link_open ?? ((tokens, idx, options, _env, self) => self.renderToken(tokens, idx, options))
md.renderer.rules.link_open = (tokens, idx, options, env, self) => {
  const t = tokens[idx]!
  const href = String(t.attrGet('href') ?? '')
  if (HTTP_RE.test(href)) {
    t.attrSet('target', '_blank')
    t.attrSet('rel', 'noopener noreferrer')
  }
  return defaultLinkOpen(tokens, idx, options, env, self)
}
md.renderer.rules.table_open = () => '<div class="md-table"><table>'
md.renderer.rules.table_close = () => '</table></div>'

let hooked = false
function ensureHook(): void {
  if (hooked) return
  hooked = true
  DOMPurify.addHook('afterSanitizeAttributes', (node) => {
    if (node.nodeName !== 'A') return
    const el = node as Element
    const href = el.getAttribute('href') ?? ''
    if (HTTP_RE.test(href)) {
      el.setAttribute('target', '_blank')
      el.setAttribute('rel', 'noopener noreferrer')
    } else if (!href.startsWith('#')) {
      el.removeAttribute('href')
      el.removeAttribute('target')
      el.setAttribute('class', 'link-blocked')
    }
  })
}

const PURIFY_CFG = {
  ALLOWED_TAGS: ['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr', 'strong', 'em', 'del', 's', 'code', 'pre',
    'blockquote', 'ul', 'ol', 'li', 'a', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'span', 'div', 'sup', 'sub'],
  ALLOWED_ATTR: ['href', 'target', 'rel', 'class', 'start', 'colspan', 'rowspan', 'align'],
  ALLOWED_URI_REGEXP: /^(?:https?:|#)/i,
  ALLOW_DATA_ATTR: false,
}

export function renderMarkdown(src: string | null | undefined): string {
  if (!src) return ''
  ensureHook()
  const html = md.render(src)
  return DOMPurify.sanitize(html, PURIFY_CFG) as unknown as string
}

/** 给 ECharts tooltip 等 innerHTML 场景转义 */
export function escapeHtml(s: unknown): string {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}
