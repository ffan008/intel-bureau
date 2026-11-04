/**
 * REST 客户端：取 session token → 自动带 X-Bureau-Token → 错误转中文 toast。
 * 令牌只放内存（模块变量），不写 localStorage / sessionStorage / cookie。
 */
import { notify } from '@/stores/toast'
import type { ApiErrorBody, SessionDTO } from './types'

export type Query = Record<string, string | number | boolean | undefined | null>

export interface MockRequest { method: string; path: string; query: URLSearchParams; body: unknown }
export interface MockTransport {
  handle(req: MockRequest): Promise<{ status: number; body: unknown; filename?: string; contentType?: string }>
  openEvents(): EventSourceLike
}
/** EventSource 与 mock 事件源的共同子集 */
export interface EventSourceLike {
  addEventListener(type: string, fn: (ev: MessageEvent) => void): void
  close(): void
  onerror: ((ev: Event) => void) | null
  readonly readyState: number
}

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public hint?: string) {
    super(message)
    this.name = 'ApiError'
  }
}

let mock: MockTransport | null = null
let token: string | null = null
let tokenPromise: Promise<string> | null = null
let session: SessionDTO | null = null

export function installMock(t: MockTransport): void { mock = t; token = null; tokenPromise = null }
export function mockTransport(): MockTransport | null { return mock }
export function currentSession(): SessionDTO | null { return session }
/** 当前令牌（同步读取；拼 <img src> 这类不能带请求头的地址时用）。任何 API 请求成功后都已就绪。 */
export function currentToken(): string | null { return token }

const STATUS_TEXT: Record<number, string> = {
  0: '无法连接后端服务', 400: '请求参数有误', 401: '访问令牌已失效', 403: '没有权限执行此操作',
  404: '请求的资源不存在', 409: '操作冲突', 413: '上传内容过大', 422: '提交的数据未通过校验',
  429: '请求过于频繁，请稍后再试', 500: '后端内部错误', 502: '后端服务不可达', 503: '后端服务暂不可用', 504: '后端响应超时',
}

function parseError(status: number, body: unknown): ApiError {
  const e = (body as ApiErrorBody | null)?.error
  if (e && typeof e.message === 'string') return new ApiError(status, e.code || String(status), e.message, e.hint)
  // FastAPI 默认校验错误 {detail:[{loc,msg}]} 或 {detail:"..."}
  const detail = (body as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') return new ApiError(status, String(status), detail)
  if (Array.isArray(detail) && detail.length) {
    const d = detail[0] as { loc?: unknown[]; msg?: string }
    const loc = Array.isArray(d.loc) ? d.loc.filter((x) => x !== 'body').join('.') : ''
    return new ApiError(status, 'validation', `${STATUS_TEXT[422]}：${loc ? loc + ' ' : ''}${d.msg ?? ''}`.trim())
  }
  return new ApiError(status, String(status), STATUS_TEXT[status] ?? `请求失败（HTTP ${status}）`)
}

async function readBody(res: Response): Promise<unknown> {
  const text = await res.text()
  if (!text) return null
  try { return JSON.parse(text) } catch { return text }
}

/** 取访问令牌（并发调用共用同一个请求） */
export async function getToken(force = false): Promise<string> {
  if (token && !force) return token
  if (!tokenPromise || force) {
    tokenPromise = (async () => {
      const s = await request<SessionDTO>('GET', '/session', { auth: false, silent: true })
      session = s
      token = s.token
      return s.token
    })().finally(() => { tokenPromise = null })
  }
  return tokenPromise
}

export interface RequestOptions {
  query?: Query
  body?: unknown
  form?: FormData
  /** 出错时不弹 toast（调用方自己处理） */
  silent?: boolean
  auth?: boolean
  signal?: AbortSignal
  timeoutMs?: number
}

function buildQuery(q?: Query): URLSearchParams {
  const p = new URLSearchParams()
  if (q) for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  return p
}

async function rawFetch(method: string, path: string, opt: RequestOptions, retried = false): Promise<Response> {
  const qs = buildQuery(opt.query).toString()
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (opt.auth !== false) headers['X-Bureau-Token'] = await getToken()
  let body: BodyInit | undefined
  if (opt.form) body = opt.form
  else if (opt.body !== undefined) { body = JSON.stringify(opt.body); headers['Content-Type'] = 'application/json' }
  const ctrl = new AbortController()
  const tm = setTimeout(() => ctrl.abort(), opt.timeoutMs ?? 30000)
  opt.signal?.addEventListener('abort', () => ctrl.abort(), { once: true })
  try {
    const res = await fetch(`/api${path}${qs ? '?' + qs : ''}`, { method, headers, body, signal: ctrl.signal, credentials: 'same-origin' })
    if (res.status === 401 && opt.auth !== false && !retried) {
      await getToken(true)
      return rawFetch(method, path, opt, true)
    }
    return res
  } finally { clearTimeout(tm) }
}
function toApiError(err: unknown): ApiError {
  if (err instanceof ApiError) return err
  if (err instanceof DOMException && err.name === 'AbortError') return new ApiError(0, 'timeout', '请求超时，后端没有及时响应')
  return new ApiError(0, 'network', STATUS_TEXT[0]!, '确认后端已启动：.venv\\Scripts\\python.exe -m bureau serve')
}

export function reportError(e: ApiError): void {
  const title = e.status === 401 ? '访问令牌已失效，请刷新页面' : e.message
  const label = STATUS_TEXT[e.status]
  notify.error(title, { detail: label && label !== title ? `${label}${e.status ? `（${e.status}）` : ''}` : undefined, hint: e.hint })
}

export async function request<T>(method: string, path: string, opt: RequestOptions = {}): Promise<T> {
  try {
    if (mock) {
      // 和真实网络一样只传 JSON 值：避免把组件里的响应式对象直接塞进 mock 状态
      const body = opt.form ?? (opt.body === undefined ? undefined : JSON.parse(JSON.stringify(opt.body)))
      const res = await mock.handle({ method, path, query: buildQuery(opt.query), body })
      if (res.status >= 400) throw parseError(res.status, res.body)
      return res.body as T
    }
    const res = await rawFetch(method, path, opt)
    const body = await readBody(res)
    if (!res.ok) throw parseError(res.status, body)
    return body as T
  } catch (err) {
    const e = toApiError(err)
    if (!opt.silent) reportError(e)
    throw e
  }
}

/** 下载文件（导出报告）。需要鉴权头，所以不能直接用 <a href>。 */
export async function download(path: string, query?: Query): Promise<{ blob: Blob; filename: string }> {
  try {
    if (mock) {
      const res = await mock.handle({ method: 'GET', path, query: buildQuery(query), body: undefined })
      if (res.status >= 400) throw parseError(res.status, res.body)
      const text = typeof res.body === 'string' ? res.body : JSON.stringify(res.body, null, 2)
      return { blob: new Blob([text], { type: res.contentType ?? 'text/plain;charset=utf-8' }), filename: res.filename ?? 'download.txt' }
    }
    const res = await rawFetch('GET', path, { query, timeoutMs: 60000 })
    if (!res.ok) throw parseError(res.status, await readBody(res))
    const cd = res.headers.get('content-disposition') ?? ''
    const m = /filename\*=UTF-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd)
    const filename = m ? decodeURIComponent((m[1] ?? m[2] ?? '').trim()) : path.split('/').pop() || 'download'
    return { blob: await res.blob(), filename }
  } catch (err) {
    const e = toApiError(err)
    reportError(e)
    throw e
  }
}

export type ProbeResult = { ok: true; session: SessionDTO } | { ok: false; reachable: boolean; reason: string }

/** 探测后端：用于决定是否切到演示数据。 */
export async function probeBackend(timeoutMs = 3500): Promise<ProbeResult> {
  const ctrl = new AbortController()
  const tm = setTimeout(() => ctrl.abort(), timeoutMs)
  try {
    const res = await fetch('/api/session', { headers: { Accept: 'application/json' }, signal: ctrl.signal })
    const body = await readBody(res)
    if (res.ok && body && typeof (body as SessionDTO).token === 'string') {
      session = body as SessionDTO
      token = session.token
      return { ok: true, session }
    }
    const code = (body as ApiErrorBody | null)?.error?.code
    if (code === 'backend_unreachable' || res.status === 502 || res.status === 504) {
      return { ok: false, reachable: false, reason: '后端未启动（127.0.0.1:8765 不可达）' }
    }
    if (typeof body === 'string' || body === null) {
      return { ok: false, reachable: false, reason: '/api 没有返回 JSON（后端未托管或代理未生效）' }
    }
    return { ok: false, reachable: true, reason: `后端返回错误：${parseError(res.status, body).message}` }
  } catch {
    return { ok: false, reachable: false, reason: '无法连接后端服务（127.0.0.1:8765）' }
  } finally {
    clearTimeout(tm)
  }
}

/** 构造 SSE 地址（EventSource 不能带自定义头，令牌走 ?token=） */
export async function eventsUrl(forceToken = false): Promise<string> {
  const t = await getToken(forceToken)
  return `/api/events?token=${encodeURIComponent(t)}`
}
