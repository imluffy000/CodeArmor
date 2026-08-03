import React, { useEffect, useState } from 'react'
import { api } from '../api'

export default function PullRequestList({ repo, onReviewSuccess, onReviewStart }) {
  const [pulls, setPulls] = useState(null)
  const [error, setError] = useState('')
  const [reviewing, setReviewing] = useState(null)
  const [reviewResult, setReviewResult] = useState(null)

  useEffect(() => {
    let cancelled = false
    setPulls(null)
    setError('')
    api(`/repos/${repo.id}/pulls?state=open`)
      .then(data => { if (!cancelled) setPulls(data.pulls) })
      .catch(err => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [repo.id])

  const runReview = async (pr) => {
    setReviewing(pr.number)
    setReviewResult(null)
    try {
      const data = await api('/review', {
        method: 'POST',
        body: JSON.stringify({ pr_url: `https://github.com/${repo.full_name}/pull/${pr.number}` }),
      })
      setReviewResult({ number: pr.number, data })
    } catch (err) {
      setReviewResult({ number: pr.number, error: err.message })
    } finally {
      setReviewing(null)
    }
  }

  if (error) return <div className="error-banner">{error}</div>
  if (pulls === null) return <p className="muted-text">Loading pull requests…</p>
  if (pulls.length === 0) return <p className="muted-text">No open pull requests in this repository.</p>

  return (
    <ul className="pr-list">
      {pulls.map(pr => (
        <li key={pr.number} className="pr-item">
          <div className="pr-item-main">
            {pr.user_avatar && <img className="pr-avatar" src={pr.user_avatar} alt={pr.user} />}
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
              disabled={reviewing !== null}
              onClick={() => {
                if (onReviewStart) {
                  onReviewStart(repo.full_name, pr.number)
                } else {
                  runReview(pr)
                }
              }}
            >
              AI Review
            </button>
          </div>

          {reviewResult && reviewResult.number === pr.number && (
            reviewResult.error ? (
              <div className="error-banner">Review failed: {reviewResult.error}</div>
            ) : (
              <div className="result pr-review-result" style={{ fontFamily: 'var(--font-sans)', fontSize: '0.95rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, flexWrap: 'wrap', gap: 8 }}>
                  <strong>{reviewResult.data.stats?.total_issues ?? 0} issue(s) found</strong>
                  <button 
                    className="btn primary btn-small" 
                    onClick={() => onReviewSuccess && onReviewSuccess(repo.full_name, pr.number, reviewResult.data)}
                  >
                    View Detailed Report
                  </button>
                </div>
                <div style={{ color: 'var(--text-muted)', lineHeight: 1.5, whiteSpace: 'pre-line' }}>
                  {reviewResult.data.summary}
                </div>
              </div>
            )
          )}
        </li>
      ))}
    </ul>
  )
}
