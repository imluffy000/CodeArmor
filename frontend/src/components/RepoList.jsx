import React, { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import PullRequestList from './PullRequestList'

const STATUS_META = {
  pending: { label: 'Queued', cls: 'badge-pending' },
  syncing: { label: 'Syncing…', cls: 'badge-syncing' },
  synced: { label: 'Synced', cls: 'badge-synced' },
  failed: { label: 'Sync failed', cls: 'badge-failed' },
}

const POLL_INTERVAL_MS = 2000
// A sync that never reaches a terminal state used to poll forever, keeping the
// instance awake and showing "Syncing…" with no way out.
const MAX_POLLS = 60

export default function RepoList({ refreshKey, onReviewStart }) {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const pollCount = useRef(0)

  const load = useCallback(async () => {
    try {
      const data = await api('/repos')
      setRepos(data.repos)
      setError(null)
      return data.repos
    } catch (err) {
      // Swallowing this rendered "No repositories connected yet" to a signed-in
      // user with ten of them — empty and broken are different states.
      setError(err.message)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    pollCount.current = 0
    load()
  }, [refreshKey, load])

  // Depend on the boolean, not on `repos`. Depending on the array restarted the
  // interval on every tick (each response is a new array identity), which made
  // the ref guard dead code and the cadence drift.
  const hasActiveSync = repos.some(
    (r) => r.sync_status === 'pending' || r.sync_status === 'syncing'
  )

  useEffect(() => {
    if (!hasActiveSync) return undefined
    const id = setInterval(() => {
      pollCount.current += 1
      if (pollCount.current > MAX_POLLS) {
        clearInterval(id)
        setError('A repository sync is taking unusually long. Try re-syncing it.')
        return
      }
      load()
    }, POLL_INTERVAL_MS)
    return () => clearInterval(id)
  }, [hasActiveSync, load])

  const disconnect = async (repo) => {
    if (!window.confirm(`Disconnect ${repo.full_name}? Its stored reviews are deleted too.`)) return
    setBusyId(repo.id)
    try {
      await api(`/repos/${repo.id}`, { method: 'DELETE' })
      setRepos((rs) => rs.filter((r) => r.id !== repo.id))
      if (expandedId === repo.id) setExpandedId(null)
    } catch (err) {
      setError(`Could not disconnect ${repo.full_name}: ${err.message}`)
    } finally {
      setBusyId(null)
    }
  }

  const resync = async (repo) => {
    setBusyId(repo.id)
    try {
      await api(`/repos/${repo.id}/sync`, { method: 'POST' })
      pollCount.current = 0
      await load()
    } catch (err) {
      setError(`Could not re-sync ${repo.full_name}: ${err.message}`)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <p className="muted-text">Loading connected repositories…</p>

  return (
    <>
      {error && (
        <div className="error-banner" role="alert">
          {error}{' '}
          <button className="btn secondary btn-small" onClick={() => { setError(null); load() }}>
            Retry
          </button>
        </div>
      )}

      {repos.length === 0 && !error ? (
        <p className="muted-text">
          No repositories connected yet. Connect one above to get started.
        </p>
      ) : (
        <ul className="repo-list">
          {repos.map((repo) => {
            const meta = STATUS_META[repo.sync_status] || STATUS_META.pending
            const expanded = expandedId === repo.id
            const panelId = `pulls-${repo.id}`
            return (
              <li key={repo.id} className={`repo-card glass-card ${expanded ? 'repo-card-expanded' : ''}`}>
                {/* A button, not a div: expanding is a required step to reach
                    the PR list, so it has to be keyboard reachable. */}
                <button
                  type="button"
                  className="repo-card-main repo-card-clickable"
                  aria-expanded={expanded}
                  aria-controls={panelId}
                  onClick={() => setExpandedId(expanded ? null : repo.id)}
                >
                  <span className="repo-card-name">
                    <span className="repo-card-chevron" aria-hidden="true">{expanded ? '▾' : '▸'}</span>{' '}
                    {repo.full_name}
                  </span>
                  <span className={`badge ${meta.cls}`}>{meta.label}</span>
                </button>

                <div className="repo-card-meta">
                  {repo.language && <span>{repo.language}</span>}
                  <span>⭐ {repo.stars}</span>
                  {repo.sync_status === 'synced' && (
                    <span title="As of the last sync">
                      {repo.open_prs} open PR{repo.open_prs === 1 ? '' : 's'}
                    </span>
                  )}
                  {repo.private && <span>🔒 private</span>}
                </div>
                {repo.description && <p className="repo-card-desc">{repo.description}</p>}

                {expanded && (
                  <div className="repo-card-pulls" id={panelId}>
                    <PullRequestList repo={repo} onReviewStart={onReviewStart} />
                  </div>
                )}

                <div className="row">
                  <a className="btn secondary btn-small" href={repo.html_url} target="_blank" rel="noreferrer">
                    View on GitHub
                  </a>
                  <button
                    className="btn secondary btn-small"
                    disabled={busyId === repo.id}
                    onClick={() => resync(repo)}
                  >
                    {busyId === repo.id ? 'Working…' : 'Re-sync'}
                  </button>
                  <button
                    className="btn secondary btn-small"
                    disabled={busyId === repo.id}
                    onClick={() => disconnect(repo)}
                  >
                    Disconnect
                  </button>
                </div>
              </li>
            )
          })}
        </ul>
      )}
    </>
  )
}
