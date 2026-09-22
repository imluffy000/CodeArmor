import React, { useEffect, useState } from 'react'
import { api } from '../api'

const STATES = [
  { id: 'open', label: 'Open' },
  { id: 'closed', label: 'Closed' },
  { id: 'all', label: 'All' },
]

export default function PullRequestList({ repo, onReviewStart }) {
  const [pulls, setPulls] = useState(null)
  const [state, setState] = useState('open')
  const [page, setPage] = useState(1)
  const [hasMore, setHasMore] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // Posting the review to GitHub writes to the repository under the user's
  // identity, so it is an explicit choice and starts off.
  const [postToGitHub, setPostToGitHub] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    if (page === 1) setPulls(null)

    api(`/repos/${repo.id}/pulls?state=${state}&page=${page}`)
      .then((data) => {
        if (cancelled) return
        setPulls((prev) => (page === 1 ? data.pulls : [...(prev || []), ...data.pulls]))
        setHasMore(data.has_more)
      })
      .catch((err) => { if (!cancelled) setError(err.message) })
      .finally(() => { if (!cancelled) setLoading(false) })

    return () => { cancelled = true }
  }, [repo.id, state, page])

  const changeState = (next) => {
    setState(next)
    setPage(1)
  }

  return (
    <>
      <div className="pr-list-header">
        <h4 className="pr-list-title">Pull requests</h4>
        <div className="row" role="group" aria-label="Filter pull requests by state">
          {STATES.map((option) => (
            <button
              key={option.id}
              className={`btn toggle btn-small ${state === option.id ? 'active' : ''}`}
              aria-pressed={state === option.id}
              onClick={() => changeState(option.id)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <label className="pr-post-toggle">
        <input
          type="checkbox"
          checked={postToGitHub}
          onChange={(e) => setPostToGitHub(e.target.checked)}
        />
        <span>
          Post the finished review to the pull request as a comment
          <small className="muted-text"> — off by default; you can also publish it afterwards</small>
        </span>
      </label>

      {error && <div className="error-banner" role="alert">{error}</div>}

      {pulls === null && loading && <p className="muted-text">Loading pull requests…</p>}

      {pulls !== null && pulls.length === 0 && !loading && (
        <p className="muted-text">No {state === 'all' ? '' : state} pull requests in this repository.</p>
      )}

      {pulls !== null && pulls.length > 0 && (
        <ul className="pr-list">
          {pulls.map((pr) => (
            <li key={pr.number} className="pr-item">
              <div className="pr-item-main">
                {pr.user_avatar && <img className="pr-avatar" src={pr.user_avatar} alt="" />}
                <div className="pr-item-info">
                  <a className="pr-title" href={pr.html_url} target="_blank" rel="noreferrer">
                    #{pr.number} {pr.title}
                  </a>
                  <span className="pr-meta">
                    {pr.draft && <span className="badge badge-pending">draft</span>}{' '}
                    {pr.head} → {pr.base} · by {pr.user}
                  </span>
                </div>
                <button
                  className="btn primary btn-small"
                  onClick={() =>
                    onReviewStart({
                      repoId: repo.id,
                      repoFullName: repo.full_name,
                      prNumber: pr.number,
                      prTitle: pr.title,
                      postToGitHub,
                    })
                  }
                >
                  AI Review
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {hasMore && (
        <button
          className="btn secondary btn-small"
          disabled={loading}
          onClick={() => setPage((p) => p + 1)}
        >
          {loading ? 'Loading…' : 'Load more'}
        </button>
      )}
    </>
  )
}
