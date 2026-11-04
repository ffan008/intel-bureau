/**
 * 报告 / 知识库正文的阅读增强。先 renderMarkdown（markdown-it html:false + DOMPurify），再在惰性的 <template> 里做 DOM 后处理。
 * 后处理只插入固定结构和纯文本（textContent），不会引入新的可执行内容：
 * - h2 / h3 编号（data-toc），供目录跳转；
 * - 代码块加工具条：类型、字数、「复制」按钮（复制的是 <pre> 的 textContent，即原文）；
 * - 长代码块、长引用、长表格折叠；
 * - 扩展研究的引用编号 [n] 变成可点击的上标，末尾参考列表重建为带编号的链接；
 * - 行内代码里的风险标签（`⚠ 账号风险`）变成风险徽标；免责声明、「一句话」段落单独样式。
 */
import { renderMarkdown, safeUrl } from './markdown'
import { RISK_LABELS, isSevereRisk } from './risk'

export interface TocEntry { i: number; level: 2 | 3; text: string }
export interface RefEntry { n: number; title: string; url: string }
export interface EnhanceOptions {
  /** 去掉第一个 h1（阅读器头部已经显示标题） */
  dropTitle?: boolean
  /** 去掉开头的「> 分类：…｜来源：…」元信息引用块（头部已经结构化显示） */
  dropMeta?: boolean
  /** ArticleDTO.research_refs；不给时从正文末尾的「参考：」块解析 */
  refs?: RefEntry[]
  /** 长内容折叠，默认开 */
  fold?: boolean
  /** 正文没写免责声明时补上的文字（放在参考列表之前） */
  appendDisclaimer?: string
  /**
   * 今日总览专用：去掉「数据卡：…」一行和「今日 N 篇专题」标题及其后的列表（前端用结构化卡片和可点的专题列表代替），
   * 板块里的 h3 升为 h2。
   */
  overview?: boolean
}
export interface Enhanced { html: string; toc: TocEntry[] }

const FOLD_CODE_LINES = 18
const FOLD_QUOTE_CHARS = 320
const FOLD_TABLE_ROWS = 12
const RISK_CODE_RE = new RegExp(`^\\s*(?:⚠️?\\s*)?(${RISK_LABELS.join('|')})\\s*$`)
/** 参考块的起始行：「参考：…」「**参考**」「## 参考资料」 */
const REF_HEAD_RE = /^(#{2,4}\s*)?(\*\*)?参考(资料|链接|来源)?(\*\*)?\s*([：:]|$)/
const REF_HEAD_STRIP = /^\s*(#{2,4}\s*)?(\*\*)?参考(资料|链接|来源)?(\*\*)?\s*[：:]?(\*\*)?/
const REF_LINE_RE = /^\s*(?:\[(\d{1,3})\]|(\d{1,3})[.、)])\s*([\s\S]*)$/
const CITE_RE = /\[(\d{1,3})\]/g
const CITE_TEST = /\[\d{1,3}\]/
const URL_RE = /https?:\/\/[^\s<>"'）)】]+/

function mk(doc: Document, tag: string, cls?: string, text?: string): HTMLElement {
  const e = doc.createElement(tag)
  if (cls) e.className = cls
  if (text !== undefined) e.textContent = text
  return e
}

function fold(doc: Document, target: Element, label: string): void {
  const box = mk(doc, 'div', 'md-fold')
  box.setAttribute('data-open', '0')
  target.parentNode!.insertBefore(box, target)
  box.appendChild(target)
  const btn = mk(doc, 'button', 'md-fold-btn', label)
  btn.setAttribute('type', 'button')
  btn.setAttribute('data-act', 'fold')
  btn.setAttribute('data-label', label)
  box.appendChild(btn)
}

/** 「[1] 标题 · https://…」或「[1] [标题](https://…)」 */
function parseRefChunk(chunk: string): RefEntry | null {
  const m = REF_LINE_RE.exec(chunk.replace(/^\s*[-*+]\s+/, ''))
  if (!m) return null
  const n = Number(m[1] ?? m[2])
  const rest = (m[3] ?? '').trim()
  const tidy = (s: string) => s.replace(/\s+/g, ' ').replace(/[\s·・\-—|｜：:]+$/, '').replace(/^[\s·・\-—|｜：:]+/, '').trim()
  const link = /\[([^\]]*)\]\((https?:\/\/[^)\s]+)\)/.exec(rest)
  if (link) {
    // 「标题 · [url](url)」：链接文字就是网址时，标题取链接前面的文字
    const before = tidy(rest.slice(0, link.index))
    const text = link[1]!.trim()
    return { n, title: (text && text !== link[2] ? text : before) || link[2]!, url: link[2]! }
  }
  const url = URL_RE.exec(rest)?.[0] ?? ''
  const title = tidy(rest.replace(url, ''))
  return { n, title: title || url, url }
}

/**
 * 从 Markdown 源文末尾切出参考块（§3.2 模板：`---` 之后的「参考：[1] 标题 · 链接 …」，一行或多行都可以）。
 * 只认「参考」开头的最后一段，且之后只有参考条目；解析不出条目时原样保留。
 */
export function splitRefs(src: string): { body: string; refs: RefEntry[] } {
  const lines = src.replace(/\r\n?/g, '\n').split('\n')
  let at = -1
  for (let i = lines.length - 1; i >= 0; i--) if (REF_HEAD_RE.test(lines[i]!.trim())) { at = i; break }
  if (at < 0) return { body: src, refs: [] }
  const tail = lines.slice(at).join('\n').replace(REF_HEAD_STRIP, '')
  // 条目可以是「[1] …」（同一行多条也行）或有序列表「1. …」（后端 compose_article.py 的写法）
  const chunks = tail.split(/(?=\[\d{1,3}\]\s*[^(\]])|\n(?=\s*\d{1,3}[.、)]\s)/).map((c) => c.trim()).filter(Boolean)
  const refs = chunks.map(parseRefChunk).filter((r): r is RefEntry => !!r)
  if (!refs.length || chunks.length !== refs.length) return { body: src, refs: [] }
  let cut = at
  while (cut > 0 && lines[cut - 1]!.trim() === '') cut--
  if (cut > 0 && /^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(lines[cut - 1]!)) cut--
  return { body: lines.slice(0, cut).join('\n'), refs }
}

function buildRefList(doc: Document, refs: RefEntry[]): HTMLElement {
  const sec = mk(doc, 'section', 'md-refs')
  sec.appendChild(mk(doc, 'h4', undefined, '参考'))
  const ol = mk(doc, 'ol')
  for (const r of [...refs].sort((a, b) => a.n - b.n)) {
    const li = mk(doc, 'li')
    li.setAttribute('data-ref-target', String(r.n))
    li.appendChild(mk(doc, 'span', 'n', `[${r.n}]`))
    const body = mk(doc, 'span')
    const href = safeUrl(r.url)
    if (href) {
      const a = mk(doc, 'a', undefined, r.title || href)
      a.setAttribute('href', href)
      a.setAttribute('target', '_blank')
      a.setAttribute('rel', 'noopener noreferrer')
      body.appendChild(a)
      try { body.appendChild(mk(doc, 'span', 'host', new URL(href).host)) } catch { /* safeUrl 已校验 */ }
    } else body.appendChild(doc.createTextNode(r.title || r.url))
    li.appendChild(body)
    ol.appendChild(li)
  }
  sec.appendChild(ol)
  return sec
}

/** 正文里的 [n] → <a class="md-cite">。跳过链接、代码、标题和参考列表本身 */
function linkCitations(doc: Document, root: DocumentFragment, known: Set<number>): void {
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => ((n.parentElement?.closest('a,code,pre,h1,h2,h3,h4,.md-refs')) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  })
  const targets: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) if (CITE_TEST.test(n.nodeValue ?? '')) targets.push(n as Text)
  for (const t of targets) {
    const s = t.nodeValue ?? ''
    const frag = doc.createDocumentFragment()
    let last = 0
    for (const m of s.matchAll(CITE_RE)) {
      const n = Number(m[1])
      if (!known.has(n)) continue
      frag.appendChild(doc.createTextNode(s.slice(last, m.index)))
      const a = mk(doc, 'a', 'md-cite', `[${n}]`)
      a.setAttribute('href', `#ref-${n}`)
      a.setAttribute('title', '跳到参考链接')
      frag.appendChild(a)
      last = (m.index ?? 0) + m[0].length
    }
    if (last === 0) continue
    frag.appendChild(doc.createTextNode(s.slice(last)))
    t.replaceWith(frag)
  }
}
const DISCLAIMER_RE = /^\s*⚠️?\s*风险提示[：:]/
/** 后端 Markdown 里的风险标签写法：〔账号风险〕〔违法高危〕 */
const RISK_BRACKET_RE = new RegExp(`〔(${RISK_LABELS.join('|')})〕`, 'g')

/** 文本节点里的〔风险标签〕→ 徽标（跳过代码和链接） */
function bracketRisks(doc: Document, root: DocumentFragment): void {
  const walker = doc.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode: (n) => (n.parentElement?.closest('code,pre,a') ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  })
  const targets: Text[] = []
  for (let n = walker.nextNode(); n; n = walker.nextNode()) if ((n.nodeValue ?? '').includes('〔')) targets.push(n as Text)
  for (const t of targets) {
    const s = t.nodeValue ?? ''
    const frag = doc.createDocumentFragment()
    let last = 0
    for (const m of s.matchAll(RISK_BRACKET_RE)) {
      frag.appendChild(doc.createTextNode(s.slice(last, m.index)))
      frag.appendChild(mk(doc, 'span', `risk-chip${isSevereRisk(m[1]!) ? ' severe' : ''}`, m[1]!))
      last = (m.index ?? 0) + m[0].length
    }
    if (last === 0) continue
    frag.appendChild(doc.createTextNode(s.slice(last)))
    t.replaceWith(frag)
  }
}

function overviewTidy(root: DocumentFragment): void {
  for (const el of [...root.children]) {
    if (el.tagName === 'P' && /^\s*数据卡[：:]/.test(el.textContent ?? '')) el.remove()
  }
  const kids = [...root.children]
  const i = kids.findIndex((e) => /^H[2-4]$/.test(e.tagName) && /今日\s*\d+\s*篇专题/.test(e.textContent ?? ''))
  if (i >= 0) {
    kids[i]!.remove()
    const next = kids[i + 1]
    if (next && (next.tagName === 'OL' || next.tagName === 'UL' || next.tagName === 'P')) next.remove()
  }
  ;[...root.children].filter((e) => e.tagName === 'H3').forEach((h) => {
    const h2 = h.ownerDocument.createElement('h2')
    h2.textContent = h.textContent
    h.replaceWith(h2)
  })
}

export function enhanceMarkdown(src: string | null | undefined, opt: EnhanceOptions = {}): Enhanced {
  if (!src) return { html: '', toc: [] }
  // 参考列表：正文里的「参考：」块总是切掉，统一重建；有 research_refs 时以它为准
  const split = splitRefs(src)
  const refs = opt.refs?.length ? opt.refs : split.refs
  const clean = renderMarkdown(split.body)
  if (!clean) return { html: '', toc: [] }
  const tpl = document.createElement('template')
  tpl.innerHTML = clean
  const root = tpl.content
  const doc = tpl.content.ownerDocument

  // DocumentFragment 上 :scope 不匹配任何元素，直接遍历顶层子节点
  if (opt.dropTitle) [...root.children].find((e) => e.tagName === 'H1')?.remove()
  if (opt.dropMeta) {
    const bq = [...root.children].slice(0, 3).find((e) => e.tagName === 'BLOCKQUOTE')
    if (bq && /分类[：:]|来源[：:]/.test(bq.textContent ?? '')) bq.remove()
  }

  if (opt.appendDisclaimer) root.appendChild(mk(doc, 'p', 'md-disclaimer', opt.appendDisclaimer))
  if (refs.length) {
    root.appendChild(mk(doc, 'hr'))
    root.appendChild(buildRefList(doc, refs))
    linkCitations(doc, root, new Set(refs.map((r) => r.n)))
  }

  if (opt.overview) overviewTidy(root)

  // 行内风险标签 → 徽标：`⚠ 账号风险` 与〔账号风险〕两种写法
  bracketRisks(doc, root)
  root.querySelectorAll('code').forEach((c) => {
    if (c.closest('pre')) return
    const m = RISK_CODE_RE.exec(c.textContent ?? '')
    if (!m) return
    c.replaceWith(mk(doc, 'span', `risk-chip${isSevereRisk(m[1]!) ? ' severe' : ''}`, m[1]!))
  })

  // 免责声明、「一句话」
  root.querySelectorAll('blockquote, p').forEach((el) => {
    if (DISCLAIMER_RE.test(el.textContent ?? '') && !el.parentElement?.closest('blockquote')) el.classList.add('md-disclaimer')
  })
  const hook = [...root.children].find((e) => e.tagName === 'P' && e.firstElementChild?.tagName === 'STRONG'
    && /^\s*一句话\s*[：:]?/.test(e.textContent ?? ''))
  hook?.classList.add('md-hook')

  // 代码块：工具条 + 复制；长的折叠
  const foldOn = opt.fold !== false
  root.querySelectorAll('pre').forEach((pre) => {
    const code = pre.querySelector('code')
    const text = (code ?? pre).textContent ?? ''
    const lang = /language-([\w+-]+)/.exec(code?.className ?? '')?.[1]
    const box = mk(doc, 'div', 'md-code')
    pre.parentNode!.insertBefore(box, pre)
    const bar = mk(doc, 'div', 'md-code-bar')
    bar.appendChild(mk(doc, 'span', 'lang', lang && lang !== 'text' ? lang : '原文'))
    bar.appendChild(mk(doc, 'span', 'len', `${text.replace(/\s/g, '').length} 字`))
    const btn = mk(doc, 'button', 'md-copy', '复制')
    btn.setAttribute('type', 'button')
    btn.setAttribute('data-act', 'copy')
    bar.appendChild(btn)
    box.appendChild(bar)
    box.appendChild(pre)
    const lines = text.split('\n').length
    if (foldOn && lines > FOLD_CODE_LINES) fold(doc, box, `展开全部 ${lines} 行`)
  })
  if (foldOn) {
    root.querySelectorAll('blockquote').forEach((bq) => {
      if (bq.classList.contains('md-disclaimer') || bq.parentElement?.closest('blockquote')) return
      if ((bq.textContent ?? '').length > FOLD_QUOTE_CHARS) fold(doc, bq, '展开全部原话')
    })
    root.querySelectorAll('.md-table').forEach((t) => {
      const rows = t.querySelectorAll('tbody tr').length
      if (rows > FOLD_TABLE_ROWS) fold(doc, t, `展开全部 ${rows} 行`)
    })
  }

  // 目录
  const toc: TocEntry[] = []
  root.querySelectorAll('h2, h3').forEach((h) => {
    const i = toc.length
    h.setAttribute('data-toc', String(i))
    toc.push({ i, level: h.tagName === 'H2' ? 2 : 3, text: (h.textContent ?? '').trim() })
  })
  return { html: tpl.innerHTML, toc }
}

