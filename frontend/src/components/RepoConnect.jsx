import React, { useCallback, useEffect, useState } from 'react'
import { api } from '../api'

export default function RepoConnect({ onConnected }) {
  const [tab, setTab] = useState('list') // 'list' | 'url'
  const [repos, setRepos] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(null)
  const [hasMore, setHasMore] = useState(false)
  const [search, setSearch] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(null)
  const [error, setError] = useState('')

  const loadRepos = useCallback(async (nextPage, term) => {
    setLoading(true)
    setError('')
    try {
      // Search runs on GitHub's side. Filtering an already-fetched page only
      // searched 30 repositories, and shrinking the page below the page size
      // also disabled "Next" — dead-ending anyone with more than 30 repos.
      const data = await api(
        `/repos/available?page=${nextPage}&search=${encodeURIComponent(term)}`
      )
      setRepos(data.repos)
      setTotal(data.total)
      setHasMore(data.has_more)
      setPage(nextPage)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { loadRepos(1, '') }, [loadRepos])

  const connect = async (payload) => {
    setError('')
    setConnecting(payload.full_name || payload.url)
    try {
      const data = await api('/repos/connect', {
        method: 'POST',
        body: JSON.stringify(payload),
      })
      setUrl('')
      setRepos((rs) =>
        rs.map((r) => (r.full_name === data.repo.full_name ? { ...r, connected: true } : r))
      )
      onConnected?.(data.repo)
    } catch (err) {
      setError(err.message)
    } finally {
      setConnecting(null)
    }
  }

  return (
    <div className="repo-connect">
      <div className="row" role="group" aria-label="How to pick a repository">
        <button
          className={`btn toggle ${tab === 'list' ? 'active' : ''}`}
          aria-pressed={tab === 'list'}
          onClick={() => setTab('list')}
        >
          My repositories
        </button>
        <button
          className={`btn toggle ${tab === 'url' ? 'active' : ''}`}
          aria-pressed={tab === 'url'}
          onClick={() => setTab('url')}
        >
          Paste a URL
        </button>
      </div>

      {error && <div className="error-banner" role="alert">{error}</div>}

      {tab === 'list' && (
        <div className="repo-picker">
          <div className="input-group">
            <label htmlFor="repo-search" className="visually-hidden">
              Search your GitHub repositories
            </label>
            <input
              id="repo-search"
              placeholder="Search your repositories…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && loadRepos(1, search)}
            />
            <button className="input-action" onClick={() => loadRepos(1, search)}>Search</button>
          </div>

          {loading ? (
            <p className="muted-text">Loading repositories…</p>
          ) : (
            <ul className="repo-options">
              {repos.map((r) => (
                <li key={r.full_name} className="repo-option">
                  <div className="repo-option-info">
                    <span className="repo-option-name">{r.full_name}</span>
                    <span className="repo-option-meta">
                      {r.private ? '🔒 private' : 'public'}
                      {r.language ? ` · ${r.language}` : ''}
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
              {repos.length === 0 && (
                <p className="muted-text">
                  {search ? `No repositories matched "${search}".` : 'No repositories found.'}
                </p>
              )}
            </ul>
          )}

          <div className="row">
            <button
              className="btn toggle"
              disabled={page === 1 || loading}
              onClick={() => loadRepos(page - 1, search)}
            >
              ← Previous
            </button>
            <span className="muted-text">
              Page {page}
              {total != null && ` · ${total} repositor${total === 1 ? 'y' : 'ies'}`}
            </span>
            <button
              className="btn toggle"
              disabled={loading || !hasMore}
              onClick={() => loadRepos(page + 1, search)}
            >
              Next →
            </button>
          </div>
        </div>
      )}

      {tab === 'url' && (
        <div className="input-group" style={{ marginTop: 16 }}>
          <label htmlFor="repo-url" className="visually-hidden">Repository URL or owner/repo</label>
          <input
            id="repo-url"
            placeholder="https://github.com/owner/repo or owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && url && connect({ url })}
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
