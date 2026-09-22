import React, { useEffect, useState } from 'react'
import { api } from '../api'

const VERDICT_LABEL = {
  blocked: { text: 'Not ready', cls: 'badge-failed' },
  caution: { text: 'Check first', cls: 'badge-pending' },
  clear: { text: 'Nothing blocking', cls: 'badge-synced' },
}

// Reviews used to live only in React state, so closing the report destroyed a
// result that cost six model calls and minutes of waiting. They are stored
// server-side now, and this is how you get back to them.
export default function ReviewHistory({ onOpen, refreshKey }) {
  const [reviews, setReviews] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api('/reviews?limit=15')
      .then((data) => { if (!cancelled) { setReviews(data); setError(null) } })
      .catch((err) => { if (!cancelled) setError(err.message) })
    return () => { cancelled = true }
  }, [refreshKey])

  if (error) return <div className="error-banner" role="alert">Could not load your reviews: {error}</div>
  if (reviews === null) return <p className="muted-text">Loading your reviews…</p>
  if (reviews.length === 0) {
    return <p className="muted-text">No reviews yet. Run one from a pull request above.</p>
  }

  return (
    <ul className="review-history">
      {reviews.map((review) => {
        const verdict = VERDICT_LABEL[review.verdict] || VERDICT_LABEL.clear
        return (
          <li key={review.review_id} className="review-history-item">
            <button
              type="button"
              className="review-history-button"
              onClick={() =>
                onOpen({
                  repoId: null,
                  repoFullName: review.repo_full_name,
                  prNumber: review.pr_number,
                  prTitle: review.pr_title,
                  reviewId: review.review_id,
                  postToGitHub: false,
                })
              }
            >
              <span className="review-history-title">
                {review.repo_full_name} #{review.pr_number}
                {review.pr_title ? ` — ${review.pr_title}` : ''}
              </span>
              <span className="review-history-meta">
                <span className={`badge ${verdict.cls}`}>{verdict.text}</span>
                <span>{review.total_issues} finding(s)</span>
                {review.score != null && <span>score {review.score}</span>}
                <span>{new Date(review.created_at).toLocaleDateString()}</span>
                {review.posted_to_github && <span>posted</span>}
              </span>
            </button>
          </li>
        )
      })}
    </ul>
  )
}
