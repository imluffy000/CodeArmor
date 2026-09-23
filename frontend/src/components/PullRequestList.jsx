import React, { useEffect, useState } from 'react'
import { ArrowRight, GitPullRequest, Play, RotateCw, Unplug } from 'lucide-react'
import { api } from '../api'
import { Banner, Empty, NotFound, SkeletonRows, Tag } from './primitives'

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
  // A repository disconnected in another tab answers 404 here, which is a
  // missing resource rather than a failed request.
  const [gone, setGone] = useState(false)
  // Posting writes to the repository under the signed-in GitHub identity, so
  // it is an explicit per-review choice and starts off.
  const [post, setPost] = useState(false)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError('')
    setGone(false)
    if (page === 1) setPulls(null)

    api(`/repos/${repo.id}/pulls?state=${state}&page=${page}`)
      .then((data) => {
        if (cancelled) return
        setPulls((prev) => (page === 1 ? data.pulls : [...(prev || []), ...data.pulls]))
        setHasMore(data.has_more)
      })
      .catch((err) => {
        if (cancelled) return
        if (err.isNotFound) setGone(true)
        else setError(err.message)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => {
      cancelled = true
    }
  }, [repo.id, state, page])

  // Filters and a review button are meaningless against a repository that
  // is not there, so this replaces the panel rather than sitting above it.
  if (gone) {
    return (
      <NotFound
        code="404"
        icon={Unplug}
        title="This repository is no longer connected"
        actions={
          <button className="btn btn--sm" onClick={() => window.location.reload()}>
            <RotateCw size={12} strokeWidth={2} aria-hidden="true" />
            Refresh
          </button>
        }
      >
        It was disconnected, or the GitHub account that owns it changed. Refresh to
        bring the repository list up to date.
      </NotFound>
    )
  }

  return (
    <div className="stack">
      <div className="cluster" style={{ justifyContent: 'space-between' }}>
        <div className="segment" role="group" aria-label="Filter pull requests by state">
          {STATES.map((option) => (
            <button
              key={option.id}
              type="button"
              aria-pressed={state === option.id}
              onClick={() => {
                setState(option.id)
                setPage(1)
              }}
            >
              {option.label}
            </button>
          ))}
        </div>

        <label className="checkbox">
          <input type="checkbox" checked={post} onChange={(e) => setPost(e.target.checked)} />
          <span>
            Post the review to the pull request
            <span className="legend" style={{ display: 'block' }}>
              off by default; you can publish it afterwards
            </span>
          </span>
        </label>
      </div>

      {error && <Banner tone="fail">{error}</Banner>}
      {pulls === null && loading && <SkeletonRows rows={4} label="Loading pull requests" />}
      {pulls !== null && pulls.length === 0 && !loading && (
        <Empty icon={GitPullRequest}>
          No {state === 'all' ? '' : state} pull requests in this repository.
        </Empty>
      )}

      {pulls !== null && pulls.length > 0 && (
        <ul>
          {pulls.map((pr) => (
            <li key={pr.number} className="pr">
              <span className="pr__num">#{pr.number}</span>
              <div className="pr__info">
                <a className="pr__title" href={pr.html_url} target="_blank" rel="noreferrer">
                  {pr.title}
                </a>
                <span className="pr__branches">
                  {pr.draft && <Tag>draft</Tag>}
                  <span>{pr.head}</span>
                  <ArrowRight size={10} strokeWidth={2} aria-hidden="true" />
                  <span>{pr.base}</span>
                  <span style={{ color: 'var(--fg-dim)' }}>{pr.user}</span>
                </span>
              </div>
              <button
                className="btn btn--sm btn--primary"
                onClick={() =>
                  onReviewStart({
                    repoId: repo.id,
                    repoFullName: repo.full_name,
                    prNumber: pr.number,
                    prTitle: pr.title,
                    postToGitHub: post,
                  })
                }
              >
                <Play size={11} strokeWidth={2.5} aria-hidden="true" />
                Review
              </button>
            </li>
          ))}
        </ul>
      )}

      {hasMore && (
        <button className="btn btn--sm" disabled={loading} onClick={() => setPage((p) => p + 1)}>
          {loading ? 'Loading' : 'Load more'}
        </button>
      )}
    </div>
  )
}
