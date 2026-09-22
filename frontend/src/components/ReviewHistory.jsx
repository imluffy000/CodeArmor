import React, { useEffect, useState } from 'react'
import { History } from 'lucide-react'
import { api } from '../api'
import { Banner, Empty, Spinner, StatusIcon, Tag, formatWhen, verdictMeta } from './primitives'

const VERDICT_STATUS = { blocked: 'fail', caution: 'warn', clear: 'pass' }

// Reviews used to live only in React state, so closing the report destroyed a
// result that cost six model calls and minutes of waiting. They are stored
// server-side now, and this is the way back to them.
export default function ReviewHistory({ onOpen, refreshKey }) {
  const [reviews, setReviews] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    let cancelled = false
    api('/reviews?limit=15')
      .then((data) => {
        if (cancelled) return
        setReviews(data)
        setError(null)
      })
      .catch((err) => {
        if (!cancelled) setError(err.message)
      })
    return () => {
      cancelled = true
    }
  }, [refreshKey])

  if (error) return <Banner tone="fail">Could not load your reviews: {error}</Banner>
  if (reviews === null) return <Spinner label="Loading reviews" />
  if (reviews.length === 0) {
    return <Empty icon={History}>No reviews yet. Run one from a pull request above.</Empty>
  }

  return (
    <div className="rows">
      {reviews.map((review) => {
        const status = VERDICT_STATUS[review.verdict] || 'unknown'
        const { label } = verdictMeta(review.verdict)
        return (
          <button
            key={review.review_id}
            type="button"
            className="history-row"
            onClick={() =>
              onOpen({
                reviewId: review.review_id,
                repoId: review.repo_id ?? null,
                repoFullName: review.repo_full_name,
                prNumber: review.pr_number,
                prTitle: review.pr_title,
                postToGitHub: false,
              })
            }
          >
            <StatusIcon status={status} size={14} />
            <span className="history-row__title">
              {review.repo_full_name}#{review.pr_number}
              {review.pr_title ? (
                <span style={{ color: 'var(--fg-muted)' }}> {review.pr_title}</span>
              ) : null}
            </span>
            <span className="history-row__meta">
              <span className="u-hidden">{label}. </span>
              {review.score != null && <span>score {review.score}</span>}
              <span>
                {review.total_issues} finding{review.total_issues === 1 ? '' : 's'}
              </span>
              {review.posted_to_github && <Tag tone="pass">posted</Tag>}
              <span>{formatWhen(review.created_at)}</span>
            </span>
          </button>
        )
      })}
    </div>
  )
}
