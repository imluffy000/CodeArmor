import React from 'react'
import LoginButton from './LoginButton'
import { useAuth } from '../context/AuthContext'

export default function Header() {
  const { user } = useAuth()

  const jump = (id) => (event) => {
    event.preventDefault()
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth' })
  }

  return (
    <header className="site-header">
      <div className="brand-row">
        <div className="brand-mark">
          <div>
            <div className="brand-name">CodeArmor</div>
            <div className="brand-subtitle">Multi-agent pull request review</div>
          </div>
        </div>

        <nav className="nav" aria-label="Main">
          <a href="#connect-repos" onClick={jump('connect-repos')}>Repositories</a>
          {!user && <a href="#features" onClick={jump('features')}>What it checks</a>}
        </nav>
      </div>

      <LoginButton />
    </header>
  )
}
