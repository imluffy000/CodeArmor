// The one place that talks to the backend.
//
// Three things it has to get right, because getting them wrong is invisible:
// the session cookie must be sent cross-site, every state-changing request
// needs a CSRF header, and a request that never returns must eventually give up
// rather than leaving a spinner on screen forever.

const configured = import.meta.env.VITE_API_URL?.replace(/\/+$/, '')

// No silent production fallback. A hardcoded backend URL means a preview build
// that forgot VITE_API_URL quietly talks to production, and nothing in the UI
// reveals which backend it hit.
export const API_BASE =
  configured || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')

export const API_CONFIGURED = Boolean(API_BASE)

const DEFAULT_TIMEOUT_MS = 30000
// A review runs six model calls, and a sleeping free-tier instance has to wake
// up first, so these two get a much longer leash.
const SLOW_PATHS = [/^\/reviews\b/, /^\/repos\/\d+\/sync$/]

export const CSRF_COOKIE = 'csrf_token'
export const CSRF_HEADER = 'X-CSRF-Token'

export function readCookie(name) {
  const match = document.cookie.match(
    new RegExp('(?:^|;\\s*)' + name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '=([^;]*)')
  )
  return match ? decodeURIComponent(match[1]) : null
}

// The backend echoes the CSRF token on /auth/me for clients whose cookie jar
// the browser will not expose to script.
let csrfFallback = null
export function rememberCsrfToken(token) {
  if (token) csrfFallback = token
}
function csrfToken() {
  return readCookie(CSRF_COOKIE) || csrfFallback
}

export class ApiError extends Error {
  constructor(message, { status, requestId, isNetwork = false } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.requestId = requestId
    this.isNetwork = isNetwork
    this.isAuthError = status === 401
  }
}

function timeoutFor(path, override) {
  if (override) return override
  return SLOW_PATHS.some((pattern) => pattern.test(path)) ? 300000 : DEFAULT_TIMEOUT_MS
}

export async function api(path, options = {}) {
  if (!API_CONFIGURED) {
    throw new ApiError(
      'This deployment is missing its VITE_API_URL setting, so it does not know which backend to use.',
      { status: 0 }
    )
  }

  const { timeout, signal, ...rest } = options
  const method = (rest.method || 'GET').toUpperCase()

  const headers = { 'Content-Type': 'application/json', ...(rest.headers || {}) }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = csrfToken()
    if (token) headers[CSRF_HEADER] = token
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutFor(path, timeout))
  if (signal) signal.addEventListener('abort', () => controller.abort(), { once: true })

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      credentials: 'include',
      ...rest,
      headers,
      signal: controller.signal,
    })
  } catch (err) {
    if (err.name === 'AbortError') {
      throw new ApiError('That request took too long. The server may be waking up — try again.', {
        isNetwork: true,
      })
    }
    throw new ApiError('Could not reach the server. Check your connection and try again.', {
      isNetwork: true,
    })
  } finally {
    clearTimeout(timer)
  }

  const requestId = response.headers.get('X-Request-ID')

  if (!response.ok) {
    let detail = response.statusText || `Request failed (${response.status})`
    try {
      const body = await response.json()
      if (body?.detail) detail = body.detail
    } catch {
      /* the error body was not JSON */
    }
    throw new ApiError(detail, { status: response.status, requestId })
  }

  if (response.status === 204) return null
  return response.json()
}
