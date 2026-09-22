import React, { useCallback, useEffect, useState } from 'react'
import { Link2, Lock, Plus, Search } from 'lucide-react'
import { api } from '../api'
import { Banner, Spinner, Tag } from './primitives'

export default function RepoConnect({ onConnected }) {
  const [mode, setMode] = useState('browse')
  const [repos, setRepos] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(null)
  const [hasMore, setHasMore] = useState(false)
  const [search, setSearch] = useState('')
  const [url, setUrl] = useState('')
  const [loading, setLoading] = useState(false)
  const [connecting, setConnecting] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async (nextPage, term) => {
    setLoading(true)
    setError('')
    try {
      // Search runs on GitHub's side. Filtering an already-fetched page
      // searched only 30 repositories, and shrinking the page below the page
      // size also disabled Next, dead-ending anyone with more than 30.
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

  useEffect(() => { load(1, '') }, [load])

  const connect = async (payload) => {
    setError('')
    setConnecting(payload.full_name || payload.url)
    try {
      const data = await api('/repos/connect', { method: 'POST', body: JSON.stringify(payload) })
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
    <div className="stack">
      <div className="cluster">
        <div className="segment" role="group" aria-label="How to add a repository">
          <button type="button" aria-pressed={mode === 'browse'} onClick={() => setMode('browse')}>
            My repositories
          </button>
          <button type="button" aria-pressed={mode === 'url'} onClick={() => setMode('url')}>
            By URL
          </button>
        </div>
        {total != null && (
          <span className="legend">
            {total} accessible
          </span>
        )}
      </div>

      {error && (
        <Banner tone="fail" actions={
          <button className="btn btn--sm" onClick={() => load(page, search)}>Retry</button>
        }>
          {error}
        </Banner>
      )}

      {mode === 'browse' ? (
        <div className="picker">
          <div className="input-row">
            <label htmlFor="repo-search" className="u-hidden">
              Search your GitHub repositories
            </label>
            <input
              id="repo-search"
              className="input"
              placeholder="Search all your repositories"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && load(1, search)}
            />
            <button className="btn" onClick={() => load(1, search)} disabled={loading}>
              <Search size={13} strokeWidth={2} aria-hidden="true" />
              Search
            </button>
          </div>

          {loading ? (
            <Spinner label="Loading repositories" />
          ) : repos.length === 0 ? (
            <p className="muted" style={{ fontSize: 'var(--text-sm)' }}>
              {search ? `Nothing matched "${search}".` : 'No repositories found.'}
            </p>
          ) : (
            <ul className="picker__list">
              {repos.map((repo) => (
                <li key={repo.full_name} className="picker__item">
                  <div>
                    <span className="row__name">{repo.full_name}</span>
                    <span className="row__meta" style={{ marginLeft: 0, marginTop: 2 }}>
                      {repo.private && (
                        <span className="cluster" style={{ gap: 3 }}>
                          <Lock size={10} strokeWidth={2} aria-hidden="true" />
                          private
                        </span>
                      )}
                      {repo.language && <span>{repo.language}</span>}
                    </span>
                  </div>
                  {repo.connected ? (
                    <Tag tone="pass">Connected</Tag>
                  ) : (
                    <button
                      className="btn btn--sm"
                      disabled={connecting === repo.full_name}
                      onClick={() => connect({ full_name: repo.full_name })}
                    >
                      <Plus size={12} strokeWidth={2.25} aria-hidden="true" />
                      {connecting === repo.full_name ? 'Adding' : 'Add'}
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}

          <div className="picker__pager">
            <button
              className="btn btn--sm"
              disabled={page === 1 || loading}
              onClick={() => load(page - 1, search)}
            >
              Previous
            </button>
            <span className="legend">page {page}</span>
            <button
              className="btn btn--sm"
              disabled={loading || !hasMore}
              onClick={() => load(page + 1, search)}
            >
              Next
            </button>
          </div>
        </div>
      ) : (
        <div className="input-row">
          <label htmlFor="repo-url" className="u-hidden">Repository URL or owner/repo</label>
          <input
            id="repo-url"
            className="input mono"
            placeholder="github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && url && connect({ url })}
          />
          <button
            className="btn"
            disabled={!url || connecting === url}
            onClick={() => connect({ url })}
          >
            <Link2 size={13} strokeWidth={2} aria-hidden="true" />
            {connecting === url ? 'Adding' : 'Add'}
          </button>
        </div>
      )}
    </div>
  )
}
