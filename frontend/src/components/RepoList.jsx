import React, { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronRight, ExternalLink, Lock, RefreshCw, Star, Unplug } from 'lucide-react'
import { api } from '../api'
import PullRequestList from './PullRequestList'
import { Banner, Empty, Spinner, StatusIcon } from './primitives'

const SYNC = {
  pending: { label: 'Queued', status: 'pending' },
  syncing: { label: 'Syncing', status: 'active' },
  synced: { label: 'Synced', status: 'pass' },
  failed: { label: 'Sync failed', status: 'fail' },
}

const POLL_MS = 2000
// A sync that never reaches a terminal state used to poll forever, keeping the
// instance awake and showing "Syncing" with no way out.
const MAX_POLLS = 60

export default function RepoList({ refreshKey, onReviewStart }) {
  const [repos, setRepos] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [expandedId, setExpandedId] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const polls = useRef(0)

  const load = useCallback(async () => {
    try {
      const data = await api('/repos')
      setRepos(data.repos)
      setError(null)
      return data.repos
    } catch (err) {
      // Swallowing this rendered "no repositories connected" to a signed-in
      // user with ten of them. Empty and broken are different states.
      setError(err.message)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    polls.current = 0
    load()
  }, [refreshKey, load])

  // Depend on the boolean, not on `repos`: each response is a new array
  // identity, so depending on the array restarted the interval every tick and
  // made the ref guard dead code.
  const syncing = repos.some((r) => r.sync_status === 'pending' || r.sync_status === 'syncing')

  useEffect(() => {
    if (!syncing) return undefined
    const id = setInterval(() => {
      polls.current += 1
      if (polls.current > MAX_POLLS) {
        clearInterval(id)
        setError('A sync is taking unusually long. Try re-syncing the repository.')
        return
      }
      load()
    }, POLL_MS)
    return () => clearInterval(id)
  }, [syncing, load])

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
      polls.current = 0
      await load()
    } catch (err) {
      setError(`Could not re-sync ${repo.full_name}: ${err.message}`)
    } finally {
      setBusyId(null)
    }
  }

  if (loading) return <Spinner label="Loading connected repositories" />

  return (
    <div className="stack">
      {error && (
        <Banner
          tone="fail"
          actions={
            <button className="btn btn--sm" onClick={() => { setError(null); load() }}>
              Retry
            </button>
          }
        >
          {error}
        </Banner>
      )}

      {repos.length === 0 && !error ? (
        <Empty>No repositories connected yet. Add one above to start reviewing.</Empty>
      ) : (
        <div className="rows">
          {repos.map((repo) => {
            const meta = SYNC[repo.sync_status] || SYNC.pending
            const expanded = expandedId === repo.id
            const panelId = `pulls-${repo.id}`
            return (
              <div key={repo.id} className="row">
                {/* A button, not a div with onClick: expanding is a required
                    step to reach the pull requests, so it has to be keyboard
                    reachable. */}
                <button
                  type="button"
                  className="row__main"
                  aria-expanded={expanded}
                  aria-controls={panelId}
                  onClick={() => setExpandedId(expanded ? null : repo.id)}
                >
                  <ChevronRight
                    size={13}
                    strokeWidth={2.25}
                    className="row__chevron"
                    aria-hidden="true"
                  />
                  <span className="row__name">{repo.full_name}</span>
                  <span className="row__meta">
                    {repo.private && <Lock size={11} strokeWidth={2} aria-hidden="true" />}
                    {repo.language && <span>{repo.language}</span>}
                    <span className="cluster" style={{ gap: 3 }}>
                      <Star size={11} strokeWidth={2} aria-hidden="true" />
                      {repo.stars}
                    </span>
                    {repo.sync_status === 'synced' && (
                      <span title="As of the last sync">{repo.open_prs} open</span>
                    )}
                    <span className="cluster" style={{ gap: 4 }}>
                      <StatusIcon status={meta.status} size={12} />
                      {meta.label}
                    </span>
                  </span>
                </button>

                {expanded && (
                  <>
                    <div className="row__body" id={panelId}>
                      <PullRequestList repo={repo} onReviewStart={onReviewStart} />
                    </div>
                    <div className="row__actions">
                      <a
                        className="btn btn--sm"
                        href={repo.html_url}
                        target="_blank"
                        rel="noreferrer"
                      >
                        <ExternalLink size={12} strokeWidth={2} aria-hidden="true" />
                        GitHub
                      </a>
                      <button
                        className="btn btn--sm"
                        disabled={busyId === repo.id}
                        onClick={() => resync(repo)}
                      >
                        <RefreshCw size={12} strokeWidth={2} aria-hidden="true" />
                        {busyId === repo.id ? 'Working' : 'Re-sync'}
                      </button>
                      <button
                        className="btn btn--sm btn--danger"
                        disabled={busyId === repo.id}
                        onClick={() => disconnect(repo)}
                      >
                        <Unplug size={12} strokeWidth={2} aria-hidden="true" />
                        Disconnect
                      </button>
                    </div>
                  </>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
