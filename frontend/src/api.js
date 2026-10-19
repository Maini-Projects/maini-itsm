// The only place the front end talks to the back end. Everything goes through the REST API,
// including sign-in, so the front end can be replaced without touching the back end.
const BASE = (import.meta.env.VITE_API_URL || '').replace(/\/$/, '')
const KEY = 'itsm.session'

function load() {
  try { return JSON.parse(localStorage.getItem(KEY)) } catch { return null }
}

let session = load()
const listeners = new Set()

export function setSession(next) {
  session = next
  try {
    if (next) localStorage.setItem(KEY, JSON.stringify(next))
    else localStorage.removeItem(KEY)
  } catch { /* storage unavailable: the session just lasts until the page is closed */ }
  listeners.forEach((fn) => fn(next))
}
export const hasSession = () => !!session
export const onSession = (fn) => { listeners.add(fn); return () => listeners.delete(fn) }

export class ApiError extends Error {
  constructor(status, code, message, fields) {
    super(message)
    this.status = status
    this.code = code
    this.fields = fields || []
  }
}

async function parseError(res) {
  let body = null
  try { body = await res.json() } catch { /* not JSON */ }
  const e = body && body.error
  if (e) {
    let message = e.message
    if (e.fields && e.fields.length) {
      message += ' ' + e.fields.map((f) => `${f.field}: ${f.problem}`).join('; ')
    }
    return new ApiError(res.status, e.code, message, e.fields)
  }
  return new ApiError(res.status, 'http_error', `Something went wrong (${res.status}).`)
}

function qs(params) {
  const p = new URLSearchParams()
  Object.entries(params || {}).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== '') p.set(k, v)
  })
  const s = p.toString()
  return s ? `?${s}` : ''
}

async function send(method, path, { body, params } = {}) {
  const headers = {}
  const isForm = typeof FormData !== 'undefined' && body instanceof FormData // a file upload: the browser sets the type
  if (body !== undefined && !isForm) headers['Content-Type'] = 'application/json'
  if (session) headers.Authorization = `Bearer ${session.access_token}`
  try {
    return await fetch(`${BASE}/api/v1${path}${qs(params)}`, {
      method, headers, body: body !== undefined ? (isForm ? body : JSON.stringify(body)) : undefined,
    })
  } catch {
    throw new ApiError(0, 'network', 'Could not reach the server. Check your connection and try again.')
  }
}

let refreshing = null
async function refreshSession() {
  if (!session) return false
  if (!refreshing) {
    refreshing = (async () => {
      const res = await send('POST', '/auth/refresh', { body: { refresh_token: session.refresh_token } }).catch(() => null)
      if (!res || !res.ok) return false
      setSession(await res.json())
      return true
    })().finally(() => { refreshing = null })
  }
  return refreshing
}

async function request(method, path, opts, raw = false) {
  let res = await send(method, path, opts)
  if (res.status === 401 && session && !path.startsWith('/auth/')) {
    if (await refreshSession()) res = await send(method, path, opts)
    if (res.status === 401) setSession(null) // session is really over: the app shows the sign-in page
  }
  if (!res.ok) throw await parseError(res)
  if (raw) return res
  return res.status === 204 ? null : res.json()
}

export const api = {
  get: (path, params) => request('GET', path, { params }),
  post: (path, body) => request('POST', path, { body: body ?? {} }),
  patch: (path, body) => request('PATCH', path, { body }),
  put: (path, body) => request('PUT', path, { body }),
  upload: (path, form) => request('POST', path, { body: form }),
  del: (path) => request('DELETE', path),
  async download(path, params, filename) {
    const res = await request('GET', path, { params }, true)
    const url = URL.createObjectURL(await res.blob())
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
  },
  async login(email, password) {
    const res = await send('POST', '/auth/login', { body: { email, password } })
    if (!res.ok) throw await parseError(res)
    setSession(await res.json())
  },
  logout: () => setSession(null),
}
