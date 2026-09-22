import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, API_BASE, API_CONFIGURED, rememberCsrfToken } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // An unreachable backend and a signed-out user look identical if you only
  // track `user`. They need different messages, so they get different state.
  const [error, setError] = useState(null)

  const refresh = useCallback(async () => {
    if (!API_CONFIGURED) {
      setError('This app is not configured with a backend URL.')
      setLoading(false)
      return
    }
    try {
      const me = await api('/auth/me')
      rememberCsrfToken(me.csrf_token)
      setUser(me)
      setError(null)
    } catch (err) {
      setUser(null)
      // 401 just means signed out, which is not an error worth showing.
      setError(err.isAuthError ? null : err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const login = () => {
    window.location.href = `${API_BASE}/auth/github/login`
  }

  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } catch {
      /* the cookie is cleared server-side either way */
    } finally {
      setUser(null)
    }
  }

  const switchAccount = async () => {
    // Revokes the GitHub grant server-side so the authorize screen appears
    // again, then re-enters the login flow to pick an account.
    try {
      await api('/auth/switch', { method: 'POST' })
    } catch {
      /* worst case GitHub reuses the current account */
    }
    setUser(null)
    window.location.href = `${API_BASE}/auth/github/login?prompt=select_account`
  }

  const deleteAccount = async () => {
    await api('/auth/account', { method: 'DELETE' })
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, error, login, logout, switchAccount, deleteAccount, refresh }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
