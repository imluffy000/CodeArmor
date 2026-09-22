import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, LogOut, ShieldCheck, Trash2, UserCog } from 'lucide-react'
import { GithubMark } from './BrandIcons'
import { useAuth } from '../context/AuthContext'

export default function Header() {
  const { user, loading, login, logout, switchAccount, deleteAccount } = useAuth()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const menuRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    const onPointerDown = (event) => {
      if (menuRef.current && !menuRef.current.contains(event.target)) setOpen(false)
    }
    const onKeyDown = (event) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('mousedown', onPointerDown)
      document.removeEventListener('keydown', onKeyDown)
    }
  }, [open])

  const removeAccount = async () => {
    if (
      !window.confirm(
        "Delete your CodeArmor account?\n\nThis revokes CodeArmor's access to your " +
          'GitHub repositories and erases your connected repositories and stored reviews. ' +
          'It cannot be undone.'
      )
    ) {
      return
    }
    setBusy(true)
    try {
      await deleteAccount()
    } catch (err) {
      window.alert(`Could not delete the account: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const jump = (id) => (event) => {
    event.preventDefault()
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand__mark" aria-hidden="true">
          <ShieldCheck size={13} strokeWidth={2.25} />
        </span>
        CodeArmor
      </div>

      {user && (
        <nav className="topbar__nav" aria-label="Main">
          <a href="#repositories" onClick={jump('repositories')}>Repositories</a>
          <a href="#reviews" onClick={jump('reviews')}>Reviews</a>
        </nav>
      )}

      <div className="topbar__spacer" />

      {loading ? null : user ? (
        <div className="account" ref={menuRef}>
          <button
            type="button"
            className="account__trigger"
            aria-expanded={open}
            aria-haspopup="menu"
            onClick={() => setOpen((v) => !v)}
          >
            {user.avatar_url && <img className="account__avatar" src={user.avatar_url} alt="" />}
            <span className="mono">{user.login}</span>
            <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
          </button>

          {open && (
            <div className="account__menu" role="menu">
              <div className="account__who">
                Signed in as <strong className="mono">{user.login}</strong>
              </div>
              <button
                type="button"
                role="menuitem"
                className="account__item"
                onClick={() => { setOpen(false); switchAccount() }}
              >
                <UserCog size={14} strokeWidth={2} aria-hidden="true" />
                Switch account
              </button>
              <button
                type="button"
                role="menuitem"
                className="account__item"
                onClick={() => { setOpen(false); logout() }}
              >
                <LogOut size={14} strokeWidth={2} aria-hidden="true" />
                Sign out everywhere
              </button>
              <button
                type="button"
                role="menuitem"
                className="account__item account__item--danger"
                disabled={busy}
                onClick={() => { setOpen(false); removeAccount() }}
              >
                <Trash2 size={14} strokeWidth={2} aria-hidden="true" />
                Delete account and data
              </button>
            </div>
          )}
        </div>
      ) : (
        <button type="button" className="btn btn--primary" onClick={login}>
          <GithubMark size={14} />
          Sign in with GitHub
        </button>
      )}
    </header>
  )
}
