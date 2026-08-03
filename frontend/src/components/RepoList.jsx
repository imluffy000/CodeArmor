import React, { useEffect, useRef, useState } from 'react'
import { api } from '../api'
import PullRequestList from './PullRequestList'

const STATUS_META = {
  pending: { label: 'Queued', cls: 'badge-pending' },
  syncing: { label: 'Syncing…', cls: 'badge-syncing' },
  synced: { label: 'Synced', cls: 'badge-synced' },
  failed: { label: 'Sync failed', cls: 'badge-failed' },
}

export default function RepoList({ refreshKey, onReviewSuccess, onReviewStart }) {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [expandedId, setExpandedId] = useState(null)
  const pollRef = useRef(null)

  const load = async () => {
    try {
      const data = await api('/repos')
      setRepos(data.repos)
      return data.repos
    } catch (_) {
      return []
    } finally {
      setLoading(false)
    }
  }

  // Load on mount and whenever a new repo is connected
  useEffect(() => { load() }, [refreshKey])

  // Poll while any repo is pending/syncing
  useEffect(() => {
    const hasActive = repos.some(r => r.sync_status === 'pending' || r.sync_status === 'syncing')
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(load, 2000)
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [repos])

  const disconnect = async (id) => {
    if (!window.confirm('Disconnect this repository?')) return
    try {
      await api(`/repos/${id}`, { method: 'DELETE' })
      setRepos(rs => rs.filter(r => r.id !== id))
      if (expandedId === id) setExpandedId(null)
    } catch (err) {
      alert('Failed to disconnect: ' + err.message)
    }
  }

  if (loading) return <p className="muted-text">Loading connected repositories…</p>
  if (repos.length === 0) return <p className="muted-text">No repositories connected yet. Connect one above to get started.</p>

  return (
    <ul className="repo-list">
      {repos.map(repo => {
        const meta = STATUS_META[repo.sync_status] || STATUS_META.pending
        const expanded = expandedId === repo.id
        return (
          <li key={repo.id} className={`repo-card glass-card ${expanded ? 'repo-card-expanded' : ''}`}>
            <div
              className="repo-card-main repo-card-clickable"
              onClick={() => setExpandedId(expanded ? null : repo.id)}
            >
              <span className="repo-card-name">
                <span className="repo-card-chevron">{expanded ? '▾' : '▸'}</span> {repo.full_name}
              </span>
              <span className={`badge ${meta.cls}`}>{meta.label}</span>
            </div>
            <div className="repo-card-meta">
              {repo.language && <span>{repo.language}</span>}
              <span>⭐ {repo.stars}</span>
              {repo.sync_status === 'synced' && <span>{repo.open_prs} open PR{repo.open_prs === 1 ? '' : 's'}</span>}
              {repo.private && <span>🔒 private</span>}
            </div>
            {repo.description && <p className="repo-card-desc">{repo.description}</p>}

            {expanded && (
              <div className="repo-card-pulls">
                <h4 className="pr-list-title">Open pull requests</h4>
                <PullRequestList repo={repo} onReviewSuccess={onReviewSuccess} onReviewStart={onReviewStart} />
              </div>
            )}

            <div className="row">
              <a className="btn secondary btn-small" href={repo.html_url} target="_blank" rel="noreferrer">
                View on GitHub
              </a>
              <button className="btn secondary btn-small" onClick={() => disconnect(repo.id)}>Disconnect</button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
