import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function RepoConnect({ onConnected }) {
  const [tab, setTab] = useState('list') // 'list' | 'url'
  const [repos, setRepos] = useState([])
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(null)
  const [error, setError] = useState('')

  const loadRepos = async (p = page, s = search) => {
    setLoading(true)
    setError('')
    try {
      const data = await api(`/repos/available?page=${p}&search=${encodeURIComponent(s)}`)
      setRepos(data.repos)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { loadRepos(1, '') }, [])

  const connect = async (payload) => {
    setError('')
    setConnecting(payload.full_name || payload.url)
    try {
      const data = await api('/repos/connect', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setUrl('')
      setRepos(rs => rs.map(r => r.full_name === data.repo.full_name ? { ...r, connected: true } : r))
      onConnected && onConnected(data.repo)
    } catch (err) {
      setError(err.message)
    } finally {
      setConnecting(null)
    }
  }

  return (
    <div className="repo-connect">
      <div className="row">
        <button className={`btn toggle ${tab === 'list' ? 'active' : ''}`} onClick={() => setTab('list')}>
          My repositories
        </button>
        <button className={`btn toggle ${tab === 'url' ? 'active' : ''}`} onClick={() => setTab('url')}>
          Paste a URL
        </button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {tab === 'list' && (
        <div className="repo-picker">
          <div className="input-group">
            <input
              placeholder="Filter repositories…"
              value={search}
              onChange={e => setSearch(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && loadRepos(1, search)}
            />
            <button className="input-action" onClick={() => { setPage(1); loadRepos(1, search) }}>Search</button>
          </div>

          {loading ? (
            <p className="muted-text">Loading repositories…</p>
          ) : (
            <ul className="repo-options">
              {repos.map(r => (
                <li key={r.full_name} className="repo-option">
                  <div className="repo-option-info">
                    <span className="repo-option-name">{r.full_name}</span>
                    <span className="repo-option-meta">
                      {r.private ? '🔒 private' : 'public'}{r.language ? ` · ${r.language}` : ''}
                    </span>
                  </div>
                  {r.connected ? (
                    <span className="badge badge-synced">Connected</span>
                  ) : (
                    <button
                      className="btn secondary btn-small"
                      disabled={connecting === r.full_name}
                      onClick={() => connect({ full_name: r.full_name })}
                    >
                      {connecting === r.full_name ? 'Connecting…' : 'Connect'}
                    </button>
                  )}
                </li>
              ))}
              {repos.length === 0 && <p className="muted-text">No repositories found.</p>}
            </ul>
          )}

          <div className="row">
            <button className="btn toggle" disabled={page === 1 || loading}
              onClick={() => { const p = page - 1; setPage(p); loadRepos(p, search) }}>← Prev</button>
            <span className="muted-text">Page {page}</span>
            <button className="btn toggle" disabled={loading || repos.length < 30}
              onClick={() => { const p = page + 1; setPage(p); loadRepos(p, search) }}>Next →</button>
          </div>
        </div>
      )}

      {tab === 'url' && (
        <div className="input-group" style={{ marginTop: 16 }}>
          <input
            placeholder="https://github.com/owner/repo or owner/repo"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && url && connect({ url })}
          />
          <button
            className="input-action"
            disabled={!url || connecting === url}
            onClick={() => connect({ url })}
          >
            {connecting === url ? 'Connecting…' : 'Connect'}
          </button>
        </div>
      )}
    </div>
  )
}
