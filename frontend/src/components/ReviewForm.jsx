import React, { useState } from 'react'

export default function ReviewForm({ onReviewSuccess }) {
  const [repo, setRepo] = useState('')
  const [prNumber, setPrNumber] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError(null)
    try {
      // Build pr_url expected by the backend
      let pr_url = ''
      const repoTrim = repo.trim()
      if (/https?:\/\/github\.com\/.+\/pull\/\d+/.test(repoTrim)) {
        pr_url = repoTrim
      } else if (repoTrim && prNumber) {
        const base = repoTrim.startsWith('http') ? repoTrim.replace(/\/$/, '') : `https://github.com/${repoTrim.replace(/\/$/, '')}`
        pr_url = `${base}/pull/${prNumber}`
      } else {
        throw new Error('Please provide repository and PR number, or a full PR URL')
      }

      const payload = { pr_url }
      const res = await fetch('http://127.0.0.1:8000/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      })
      
      if (!res.ok) {
        const text = await res.text()
        let detail = text
        try {
          const body = JSON.parse(text)
          detail = body.detail || text
        } catch (_) {}
        throw new Error(detail)
      }

      const data = await res.json()
      
      let displayRepo = repo.trim()
      let displayPrNumber = prNumber.trim()
      const match = pr_url.match(/github\.com\/([^\/]+\/[^\/]+)\/pull\/(\d+)/)
      if (match) {
        displayRepo = match[1]
        displayPrNumber = match[2]
      }

      if (onReviewSuccess) {
        onReviewSuccess(displayRepo, displayPrNumber, data)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function openRepo() {
    if (repo) window.open(repo.startsWith('http') ? repo : `https://github.com/${repo}`, '_blank')
  }

  return (
    <form className="review-form" onSubmit={submit}>
      <label>
        Repository URL / Path
        <div className="input-group">
          <input
            value={repo}
            onChange={e => setRepo(e.target.value)}
            placeholder="https://github.com/owner/repo or owner/repo"
          />
          <button type="button" className="btn input-action" onClick={openRepo} title="Open repository">
            Open
          </button>
        </div>
      </label>

      <label style={{ marginTop: 16 }}>
        PR Number
        <input
          value={prNumber}
          onChange={e => setPrNumber(e.target.value)}
          placeholder="e.g. 123"
          type="text"
        />
      </label>

      <div className="row" style={{ marginTop: 24 }}>
        <button className="btn primary" type="submit" disabled={loading}>
          {loading ? 'Reviewing...' : 'Review PR'}
        </button>
      </div>

      {error && (
        <div className="error-banner">
          Review failed: {error}
        </div>
      )}
    </form>
  )
}
