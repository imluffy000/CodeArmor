import React, { createContext, useContext, useEffect, useState } from 'react'
import { api, API_BASE } from '../api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api('/auth/me')
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setLoading(false))
  }, [])

  const login = () => {
    window.location.href = `${API_BASE}/auth/github/login`
  }

  const logout = async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } finally {
      setUser(null)
    }
  }

  const switchAccount = async () => {
    // Revokes the GitHub grant server-side so the authorize screen appears
    // again, then goes straight back into the login flow to pick an account.
    try {
      await api('/auth/switch', { method: 'POST' })
    } catch {
      // fall through — worst case GitHub reuses the current account
    }
    setUser(null)
    window.location.href = `${API_BASE}/auth/github/login?prompt=select_account`
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, switchAccount }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  return useContext(AuthContext)
}
