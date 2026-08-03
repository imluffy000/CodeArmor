import React, { useEffect, useRef, useState } from 'react'
import { useAuth } from '../context/AuthContext'

export default function LoginButton() {
  const { user, loading, login, logout, switchAccount } = useAuth()
  const [menuOpen, setMenuOpen] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    const onClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setMenuOpen(false)
      }
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  if (loading) return null

  if (user) {
    return (
      <div className="user-menu" ref={menuRef}>
        <button className="user-chip" onClick={() => setMenuOpen(prev => !prev)}>
          {user.avatar_url && <img className="user-avatar" src={user.avatar_url} alt={user.login} />}
          <span className="user-login">{user.name || user.login}</span>
          <span className="material-symbols-outlined user-caret">expand_more</span>
        </button>

        {menuOpen && (
          <div className="user-dropdown">
            <div className="user-dropdown-info">
              Signed in as <strong>@{user.login}</strong>
            </div>
            <button
              className="user-dropdown-item"
              onClick={() => { setMenuOpen(false); switchAccount() }}
            >
              <span className="material-symbols-outlined">swap_horiz</span>
              Switch account
            </button>
            <button
              className="user-dropdown-item"
              onClick={() => { setMenuOpen(false); logout() }}
            >
              <span className="material-symbols-outlined">logout</span>
              Sign out
            </button>
          </div>
        )}
      </div>
    )
  }

  return (
    <button className="header-cta" onClick={login}>
      <svg height="18" width="18" viewBox="0 0 16 16" fill="currentColor" style={{ verticalAlign: 'text-bottom', marginRight: 8 }}>
        <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
      </svg>
      Sign in with GitHub
    </button>
  )
}
