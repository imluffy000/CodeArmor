export const API_BASE =
  import.meta.env.VITE_API_URL ||
  'https://ai-pr-reviewer-nw1r.onrender.com'

export async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail || detail
    } catch (_) { /* non-JSON error body */ }
    const err = new Error(detail)
    err.status = res.status
    throw err
  }
  return res.json()
}
