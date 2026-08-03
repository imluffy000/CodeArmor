import React from 'react'
import LoginButton from './LoginButton'
import { useAuth } from '../context/AuthContext'

export default function Header(){
  const { user } = useAuth()
  return (
    <header className="site-header">
      <div className="brand-row">
        <div className="brand-mark" style={{ gap: '0px' }}>
          <div>
            <div className="brand-name" style={{ fontSize: '1.4rem', fontWeight: 800 }}>CodeArmor</div>
            <div className="brand-subtitle">Ship smarter, review faster.</div>
          </div>
        </div>

        <nav className="nav">
          <a href="#connect-repos" onClick={(e) => {
            e.preventDefault()
            document.getElementById('connect-repos')?.scrollIntoView({ behavior: 'smooth' })
          }}>Repositories</a>
          {!user && (
            <a href="#features" onClick={(e) => {
              e.preventDefault()
              document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })
            }}>Features</a>
          )}
          <a href="#contact" onClick={(e) => {
            e.preventDefault()
            document.getElementById('contact')?.scrollIntoView({ behavior: 'smooth' })
          }}>Contact</a>
        </nav>
      </div>

      <LoginButton />
    </header>
  )
}
