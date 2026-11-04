// 开发自查：用 Edge/Chrome 无头模式打开各路由，收集控制台错误、检查大屏溢出并截图。
// 用法：node scripts/check.mjs [/,/reports,...]   环境变量：BASE OUT W H WAIT BROWSER ACTION=run PRE EVAL ACT ACT_WAIT FULL CLIP
import { spawn } from 'node:child_process'
import { mkdirSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const BASE = process.env.BASE ?? 'http://127.0.0.1:5180'
const routes = (process.argv[2] ?? '/,/reports,/sources,/schedules,/channels,/agents,/system').split(',')
const OUT = process.env.OUT ?? join(tmpdir(), 'ib-shots')
const W = Number(process.env.W ?? 1920), H = Number(process.env.H ?? 1080)
const WAIT = Number(process.env.WAIT ?? 4500)
const BROWSER = process.env.BROWSER ?? 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'
const PORT = 9333
const prof = join(tmpdir(), `ib-check-${Date.now()}`)
mkdirSync(OUT, { recursive: true })

const proc = spawn(BROWSER, ['--headless=new', `--remote-debugging-port=${PORT}`, `--user-data-dir=${prof}`, `--window-size=${W},${H}`,
  '--hide-scrollbars', '--force-device-scale-factor=1', '--no-first-run', '--disable-extensions', 'about:blank'], { stdio: 'ignore' })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function targets() {
  for (let i = 0; i < 60; i++) {
    try { return await (await fetch(`http://127.0.0.1:${PORT}/json`)).json() } catch { await sleep(250) }
  }
  throw new Error('浏览器调试端口没有响应')
}

const problems = []
try {
  const page = (await targets()).find((t) => t.type === 'page')
  const ws = new WebSocket(page.webSocketDebuggerUrl)
  await new Promise((r, j) => { ws.onopen = r; ws.onerror = j })
  let seq = 0
  const pending = new Map()
  let current = ''
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data)
    if (m.id && pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); return }
    if (m.method === 'Runtime.exceptionThrown') problems.push(`[${current}] 异常：${m.params.exceptionDetails.exception?.description ?? m.params.exceptionDetails.text}`)
    if (m.method === 'Runtime.consoleAPICalled' && (m.params.type === 'error' || m.params.type === 'warning')) {
      problems.push(`[${current}] console.${m.params.type}：${m.params.args.map((a) => a.value ?? a.description ?? '').join(' ').slice(0, 400)}`)
    }
    if (m.method === 'Log.entryAdded' && m.params.entry.level === 'error') problems.push(`[${current}] ${m.params.entry.source}：${m.params.entry.text} ${m.params.entry.url ?? ''}`)
  }
  const send = (method, params = {}) => new Promise((r) => { const id = ++seq; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })) })
  const evaluate = async (expr) => (await send('Runtime.evaluate', { expression: expr, returnByValue: true, awaitPromise: true })).result?.result?.value
  const shot = async (name) => {
    // CLIP="x,y,w,h;x,y,w,h"：额外截取局部（原尺寸），方便细看
    for (const [i, c] of (process.env.CLIP ?? '').split(';').filter(Boolean).entries()) {
      const [x, y, width, height] = c.split(',').map(Number)
      const rc = await send('Page.captureScreenshot', { format: 'png', clip: { x, y, width, height, scale: 1 } })
      writeFileSync(join(OUT, `${name}-clip${i}.png`), Buffer.from(rc.result.data, 'base64'))
    }
    const r = await send('Page.captureScreenshot', { format: 'png' })
    const file = join(OUT, `${name}.png`)
    writeFileSync(file, Buffer.from(r.result.data, 'base64'))
    console.log('截图', file)
  }
  await send('Runtime.enable'); await send('Log.enable'); await send('Page.enable')
  await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false })

  // PRE="js"：先打开首页执行一段脚本（如写 localStorage），再逐个检查路由
  if (process.env.PRE) {
    await send('Page.navigate', { url: BASE + '/' })
    await sleep(1500)
    await evaluate(process.env.PRE)
  }
  for (const route of routes) {
    current = route
    await send('Page.navigate', { url: BASE + route })
    await sleep(WAIT)
    const name = route === '/' ? 'screen' : route.slice(1).replace(/[\/?&=#:*"<>|\\]+/g, '_').replace(/_+$/, '')
    const info = await evaluate(`(() => {
      const de = document.documentElement
      const res = { title: document.title, docOverflow: de.scrollWidth > innerWidth + 1 || de.scrollHeight > innerHeight + 1, bodies: [] }
      for (const b of document.querySelectorAll('.stage .hud-body')) {
        if (b.scrollHeight > b.clientHeight + 1 || b.scrollWidth > b.clientWidth + 1) {
          const t = b.parentElement.querySelector('.ttl')?.textContent
          res.bodies.push((t ?? '?') + ' ' + b.scrollWidth + 'x' + b.scrollHeight + ' > ' + b.clientWidth + 'x' + b.clientHeight)
        }
      }
      for (const el of document.querySelectorAll('.stage *')) {
        const cs = getComputedStyle(el)
        if ((cs.overflowY === 'auto' || cs.overflowY === 'scroll') && el.scrollHeight > el.clientHeight + 1 && !el.closest('.term') && !el.closest('.d-mask'))
          res.bodies.push('滚动条：' + el.className)
      }
      const st = document.querySelector('.stage')
      if (st) res.stage = st.offsetWidth + 'x' + st.offsetHeight
      return res
    })()`)
    console.log(route, JSON.stringify(info))
    if (process.env.EVAL) console.log('EVAL', JSON.stringify(await evaluate(process.env.EVAL), null, 1))
    if (info?.docOverflow) problems.push(`[${route}] 页面出现滚动条`)
    for (const b of info?.bodies ?? []) problems.push(`[${route}] 面板溢出：${b}`)
    await shot(name)
    // ACT="名字::js;;名字::js"：依次执行一段脚本（点击、切标签、滚动），等 ACT_WAIT 毫秒后截图为 <路由>-<名字>.png
    for (const step of (process.env.ACT ?? '').split(';;').filter(Boolean)) {
      const i = step.indexOf('::')
      const [tag, js] = i < 0 ? ['act', step] : [step.slice(0, i), step.slice(i + 2)]
      const r = await evaluate(js)
      if (r !== undefined) console.log('ACT', tag, JSON.stringify(r))
      await sleep(Number(process.env.ACT_WAIT ?? 1200))
      await shot(`${name}-${tag}`)
    }
    // FULL=1：把视口拉高到内容高度，截一张长图（只用于普通页面；大屏是固定画布）
    if (process.env.FULL && route !== '/') {
      const extra = await evaluate(`Math.max(0, ...[...document.querySelectorAll('*')].filter((e) => { const o = getComputedStyle(e).overflowY; return (o === 'auto' || o === 'scroll') && e.clientHeight > 200 }).map((e) => e.scrollHeight - e.clientHeight))`)
      const fullH = Math.min(8000, H + (extra ?? 0))
      await send('Emulation.setDeviceMetricsOverride', { width: W, height: fullH, deviceScaleFactor: 1, mobile: false })
      await sleep(900)
      await shot(`${name}-full`)
      await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: false })
    }
    if (route === '/' && process.env.ACTION === 'run') {
      await evaluate(`document.querySelector('.run')?.click()`)
      let at = 0
      for (const t of (process.env.RUN_AT ?? '2500,7000,12000,24000').split(',').map(Number)) {
        await sleep(t - at)
        at = t
        await shot(`screen-run-${t}`)
      }
    }
  }
  ws.close()
} finally {
  proc.kill()
  await sleep(500)
  try { rmSync(prof, { recursive: true, force: true }) } catch { /* Edge 可能还占着文件 */ }
}
console.log(problems.length ? `\n发现 ${problems.length} 个问题：\n` + problems.join('\n') : '\n未发现控制台错误或溢出')
