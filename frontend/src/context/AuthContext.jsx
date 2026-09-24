import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, API_BASE, API_CONFIGURED, rememberCsrfToken } from '../api'

const AuthContext = createContext(null)

// Did this browser have a session last time it was here?
//
// The landing page needs no authentication, so an anonymous visitor should
// never wait on /auth/me - and on a sleeping free instance that wait is
// 30-90s of spinner in front of a page that was ready immediately. But a
// signed-in visitor must NOT be shown the marketing page and then have it
// yanked away, so the two cases need telling apart before the answer arrives.
//
// This flag is the only thing that can distinguish them client-side. It is a
// hint for choosing what to render first, never an authorization signal: the
// session itself is an httpOnly cookie the server verifies, and setting this
// key by hand grants nothing.
const RETURNING_KEY = 'codearmor.returning'

function readReturning() {
  try {
    return window.localStorage.getItem(RETURNING_KEY) === '1'
  } catch {
    // Private windows and blocked site data throw rather than return null.
    return false
  }
}

function writeReturning(value) {
  try {
    if (value) window.localStorage.setItem(RETURNING_KEY, '1')
    else window.localStorage.removeItem(RETURNING_KEY)
  } catch {
    /* nothing to do - the flag is an optimisation, not state we depend on */
  }
}

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  // Read once, at mount: it decides the first paint and must not change
  // underneath that decision.
  const [returning] = useState(readReturning)
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
      writeReturning(true)
    } catch (err) {
      setUser(null)
      // 401 just means signed out, which is not an error worth showing.
      setError(err.isAuthError ? null : err.message)
      // Only a definite "you are not signed in" clears the flag. An
      // unreachable API says nothing about whether the session is still good,
      // so the hint is left alone.
      if (err.isAuthError) writeReturning(false)
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
      writeReturning(false)
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
    writeReturning(false)
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        loading,
        returning,
        error,
        login,
        logout,
        switchAccount,
        deleteAccount,
        refresh,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
