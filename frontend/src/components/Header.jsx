import React, { useEffect, useRef, useState } from 'react'
import { ChevronDown, LogOut, Trash2, UserCog } from 'lucide-react'
import { GithubMark } from './BrandIcons'
import { useAuth } from '../context/AuthContext'

const SIGNED_IN_NAV = [
  ['repositories', 'Repositories'],
  ['reviews', 'Reviews'],
]

const LANDING_NAV = [
  ['product', 'Product'],
  ['uses', 'Uses'],
  ['policies', 'Policies'],
  ['contact', 'Contact'],
]

export default function Header() {
  const { user, loading, returning, login, logout, switchAccount, deleteAccount } = useAuth()
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const menuRef = useRef(null)

  // The same condition App uses to decide the landing page is showing. The bar
  // has to agree with it, or the page paints with its nav and its sign-in
  // button missing while the session check is still outstanding.
  const anonymous = !user && (!loading || !returning)

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

  // Which landing section the reader is actually in. A nav that never shows
  // where you are is a list of links; this is what makes it read as product
  // navigation. Landing only - the signed-in surfaces have two anchors and no
  // need for it.
  const [active, setActive] = useState(null)
  const onscreen = useRef(new Set())

  useEffect(() => {
    if (!anonymous || typeof IntersectionObserver === 'undefined') return undefined

    const ids = LANDING_NAV.map(([id]) => id)
    const nodes = ids.map((id) => document.getElementById(id)).filter(Boolean)
    if (nodes.length === 0) return undefined

    const bar = document.querySelector('.topbar')
    const barOffset = Math.round(bar ? bar.getBoundingClientRect().height : 64) + 8

    const observer = new IntersectionObserver(
      (entries) => {
        // The callback only reports sections whose visibility CHANGED, so the
        // set has to be kept across calls - deciding from `entries` alone
        // picks whichever section happened to cross the line last.
        entries.forEach((entry) => {
          if (entry.isIntersecting) onscreen.current.add(entry.target.id)
          else onscreen.current.delete(entry.target.id)
        })
        // `ids` is in document order, so the first hit is the topmost one.
        const current = ids.find((id) => onscreen.current.has(id))
        if (current) setActive(current)
      },
      // Measured rather than hardcoded: this has to clear the sticky bar, and
      // a constant here silently goes wrong the next time the bar is resized.
      { rootMargin: `-${barOffset}px 0px -55% 0px` }
    )

    nodes.forEach((node) => observer.observe(node))
    return () => {
      observer.disconnect()
      onscreen.current.clear()
    }
  }, [anonymous])

  const jump = (id) => (event) => {
    event.preventDefault()
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <header className="topbar">
      <div className="brand">
        {/* alt is empty on purpose: the wordmark next to it already says
            CodeArmor, and a screen reader announcing it twice is noise. */}
        <img className="brand__mark" src="/logo.png" width="22" height="22" alt="" />
        CodeArmor
      </div>

      {/* Two different navs, because the two states have nothing in common:
          signed in, the only places worth going are the work surfaces; signed
          out, they are the sections that explain the product. */}
      {user ? (
        <nav className="topbar__nav" aria-label="Main">
          {SIGNED_IN_NAV.map(([id, label]) => (
            <a key={id} href={`#${id}`} onClick={jump(id)}>
              {label}
            </a>
          ))}
        </nav>
      ) : (
        anonymous && (
          <nav className="topbar__nav" aria-label="Main">
            {LANDING_NAV.map(([id, label]) => (
              <a
                key={id}
                href={`#${id}`}
                aria-current={active === id ? 'true' : undefined}
                onClick={jump(id)}
              >
                {label}
              </a>
            ))}
          </nav>
        )
      )}

      <div className="topbar__spacer" />

      {user ? (
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
      ) : anonymous ? (
        <button type="button" className="btn btn--primary" onClick={login}>
          <GithubMark size={14} />
          {/* The tail is dropped on a phone, where the full label pushed the
              button off the right edge. The accessible name stays meaningful
              either way. */}
          {/* One span, not a bare text node plus a span: a text node inside a
              flex container becomes its own flex item, so the two picked up
              the button gap between them and rendered a double space. */}
          <span>
            Sign in<span className="topbar__cta-tail"> with GitHub</span>
          </span>
        </button>
      ) : null}
    </header>
  )
}
