/** mock 图片：用 SVG 画的「截图」，转成 data: URL（CSP img-src 允许 data:）。只放纯文本和图形，没有脚本 */
const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
const FONT = `font-family="Microsoft YaHei, PingFang SC, sans-serif"`
const W = 960, H = 600

function wrap(body: string, title: string, accent = '#22e4ff'): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" ${FONT}>`
    + `<defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#0d1a33"/><stop offset="1" stop-color="#060b18"/></linearGradient></defs>`
    + `<rect width="${W}" height="${H}" fill="url(#g)"/><rect x="0" y="0" width="${W}" height="56" fill="#0b1630"/>`
    + `<rect x="0" y="54" width="${W}" height="2" fill="${accent}" opacity="0.7"/>`
    + `<text x="28" y="36" font-size="22" fill="#eaf6ff" font-weight="700">${esc(title)}</text>${body}</svg>`
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`
}

/** 聊天截图：左右气泡 */
export function chatShot(title: string, msgs: { who: string; text: string; me?: boolean }[]): string {
  let y = 92
  const body = msgs.map((m) => {
    const w = Math.min(640, 40 + m.text.length * 21)
    const x = m.me ? W - 40 - w : 96
    const out = `${m.me ? '' : `<circle cx="60" cy="${y + 18}" r="20" fill="#1d3a66"/><text x="60" y="${y + 25}" font-size="16" fill="#a9c4dd" text-anchor="middle">${esc(m.who.slice(0, 1))}</text>`}`
      + `<text x="${m.me ? W - 40 : x}" y="${y - 6}" font-size="13" fill="#6c86a3" text-anchor="${m.me ? 'end' : 'start'}">${esc(m.who)}</text>`
      + `<rect x="${x}" y="${y}" width="${w}" height="40" rx="8" fill="${m.me ? '#1f6b4a' : '#1a2b4a'}"/>`
      + `<text x="${x + 18}" y="${y + 26}" font-size="18" fill="#eaf6ff">${esc(m.text)}</text>`
    y += 78
    return out
  }).join('')
  return wrap(body, title, '#2bd96b')
}

/** 柱状图 */
export function barChart(title: string, bars: { label: string; value: number; color?: string }[], unit = ''): string {
  const max = Math.max(...bars.map((b) => b.value)) * 1.15
  const bw = Math.min(160, (W - 160) / bars.length - 40)
  const body = bars.map((b, i) => {
    const h = (b.value / max) * 400, x = 110 + i * (bw + 60), y = 530 - h
    return `<rect x="${x}" y="${y}" width="${bw}" height="${h}" fill="${b.color ?? '#22e4ff'}" opacity="0.85"/>`
      + `<text x="${x + bw / 2}" y="${y - 12}" font-size="26" fill="#eaf6ff" text-anchor="middle" font-weight="700">${b.value}${esc(unit)}</text>`
      + `<text x="${x + bw / 2}" y="566" font-size="17" fill="#a9c4dd" text-anchor="middle">${esc(b.label)}</text>`
  }).join('')
  return wrap(`<line x1="80" y1="530" x2="${W - 40}" y2="530" stroke="#2a4a74"/>${body}`, title, '#ffb020')
}

/** 流程图：一行方框 + 箭头 */
export function flow(title: string, steps: string[], sub?: string): string {
  const n = steps.length, bw = (W - 80 - (n - 1) * 36) / n
  const body = steps.map((s, i) => {
    const x = 40 + i * (bw + 36)
    const lines = s.match(/.{1,7}/g) ?? [s]
    return `<rect x="${x}" y="230" width="${bw}" height="120" rx="6" fill="#10224a" stroke="#22e4ff" stroke-opacity="0.6"/>`
      + `<text x="${x + 14}" y="256" font-size="14" fill="#22e4ff">STEP ${i + 1}</text>`
      + lines.map((l, j) => `<text x="${x + bw / 2}" y="${292 + j * 26}" font-size="19" fill="#eaf6ff" text-anchor="middle">${esc(l)}</text>`).join('')
      + (i < n - 1 ? `<path d="M${x + bw + 6} 290 h24 m-8 -8 l8 8 -8 8" stroke="#8b5cff" stroke-width="2.5" fill="none"/>` : '')
  }).join('')
  return wrap(body + (sub ? `<text x="${W / 2}" y="440" font-size="17" fill="#a9c4dd" text-anchor="middle">${esc(sub)}</text>` : ''), title, '#8b5cff')
}

/** 表格截图 */
export function table(title: string, head: string[], rows: string[][]): string {
  const cw = (W - 80) / head.length
  const cell = (t: string, x: number, y: number, c: string, b = false) => `<text x="${x + 14}" y="${y}" font-size="17" fill="${c}"${b ? ' font-weight="700"' : ''}>${esc(t)}</text>`
  let body = `<rect x="40" y="90" width="${W - 80}" height="48" fill="#13284f"/>` + head.map((h, i) => cell(h, 40 + i * cw, 121, '#22e4ff', true)).join('')
  rows.forEach((r, j) => {
    const y = 138 + j * 52
    body += `<rect x="40" y="${y}" width="${W - 80}" height="52" fill="${j % 2 ? '#0c1a36' : '#0a1530'}"/>` + r.map((t, i) => cell(t, 40 + i * cw, y + 33, '#d7e8f7')).join('')
  })
  return wrap(body, title)
}

/** 折线图 */
export function line(title: string, values: number[], note: string): string {
  const max = Math.max(...values) * 1.1, step = (W - 160) / (values.length - 1)
  const pts = values.map((v, i) => `${100 + i * step},${520 - (v / max) * 380}`).join(' ')
  const last = values[values.length - 1]!
  return wrap(`<line x1="90" y1="520" x2="${W - 40}" y2="520" stroke="#2a4a74"/>`
    + `<polyline points="${pts}" fill="none" stroke="#ff3db8" stroke-width="3"/>`
    + `<text x="${W - 60}" y="${520 - (last / max) * 380 - 16}" font-size="24" fill="#eaf6ff" text-anchor="end" font-weight="700">${last}</text>`
    + `<text x="100" y="566" font-size="16" fill="#a9c4dd">${esc(note)}</text>`, title, '#ff3db8')
}

/** 三张卡并排（多图融合示意） */
export function cards(title: string, items: { label: string; color: string }[], result: string): string {
  const body = items.map((it, i) => {
    const x = 60 + i * 230
    return `<rect x="${x}" y="110" width="200" height="260" rx="6" fill="${it.color}" opacity="0.28"/><rect x="${x}" y="110" width="200" height="260" rx="6" fill="none" stroke="${it.color}"/>`
      + `<text x="${x + 100}" y="250" font-size="22" fill="#eaf6ff" text-anchor="middle">${esc(it.label)}</text>`
  }).join('')
  return wrap(body + `<path d="M760 240 h40 m-10 -10 l10 10 -10 10" stroke="#22e4ff" stroke-width="3" fill="none"/>`
    + `<rect x="812" y="110" width="120" height="260" rx="6" fill="#22e4ff" opacity="0.2"/><text x="872" y="250" font-size="18" fill="#eaf6ff" text-anchor="middle">${esc(result)}</text>`
    + `<text x="60" y="430" font-size="18" fill="#a9c4dd">提示词：「图1 的人物穿上图2 的服装，站在图3 的场景里」</text>`, title, '#ff3db8')
}
