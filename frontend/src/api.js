// Use the same hostname as the page so the session cookie (host-scoped,
// SameSite=lax) is always sent. localhost and 127.0.0.1 are different sites
// to the browser; main.jsx normalizes the app onto 127.0.0.1.
export const API_BASE = `http://${window.location.hostname}:8000`

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
