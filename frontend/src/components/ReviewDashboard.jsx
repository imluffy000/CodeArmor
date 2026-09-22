import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, API_BASE } from '../api'
import MergeGate from './MergeGate'
import { formatMessageText } from '../lib/markdown.jsx'

const REVIEW_STEPS = [
  { id: 'fetch_diff', label: 'Fetching PR and GitHub facts' },
  { id: 'security', label: 'Security agent' },
  { id: 'quality', label: 'Code quality agent' },
  { id: 'performance', label: 'Performance agent' },
  { id: 'testing', label: 'Testing agent' },
  { id: 'architecture', label: 'Architecture agent' },
  { id: 'integration', label: 'Integration & merge-readiness agent' },
  { id: 'summary', label: 'Summary and merge gate' },
]

const PENDING_STEPS = Object.fromEntries(REVIEW_STEPS.map((s) => [s.id, 'pending']))

// Nothing has arrived for this long: the stream is probably dead rather than slow.
const WATCHDOG_MS = 180000

export default function ReviewDashboard({ review, onReset }) {
  const { repoId, repoFullName, prNumber, prTitle, postToGitHub } = review

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [stepsStatus, setStepsStatus] = useState(PENDING_STEPS)
  const [coverageNotice, setCoverageNotice] = useState(null)
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [publishState, setPublishState] = useState({ busy: false, error: null })
  const [copied, setCopied] = useState(null)
  const [attempt, setAttempt] = useState(0)

  const [askInput, setAskInput] = useState('')
  const [askExpanded, setAskExpanded] = useState(false)
  const [chatMessages, setChatMessages] = useState([
    {
      sender: 'ai',
      text: 'Ask me anything about these findings — why one matters, or how to apply a suggested fix.',
    },
  ])
  const chatLogRef = useRef(null)

  useEffect(() => {
    if (chatLogRef.current) chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight
  }, [chatMessages])

  // --- the review stream -------------------------------------------------
  useEffect(() => {
    let closed = false
    setLoading(true)
    setError(null)
    setCoverageNotice(null)
    setStepsStatus({ ...PENDING_STEPS, fetch_diff: 'active' })

    const url =
      `${API_BASE}/reviews/stream?repo_id=${repoId}&pr_number=${prNumber}` +
      (attempt > 0 ? '&refresh=true' : '')
    const source = new EventSource(url, { withCredentials: true })

    let watchdog
    const resetWatchdog = () => {
      clearTimeout(watchdog)
      watchdog = setTimeout(() => {
        if (closed) return
        closed = true
        source.close()
        setError('The review stopped responding. Nothing has arrived for a few minutes.')
        setLoading(false)
      }, WATCHDOG_MS)
    }
    resetWatchdog()

    const on = (name, handler) =>
      source.addEventListener(name, (event) => {
        resetWatchdog()
        handler(event)
      })

    on('step', (event) => {
      const step = event.data
      if (step === 'fetch_diff_done') {
        setStepsStatus((prev) => {
          const next = { ...prev, fetch_diff: 'done' }
          REVIEW_STEPS.slice(1, -1).forEach((s) => { next[s.id] = 'active' })
          return next
        })
      } else if (step === 'summary_done') {
        setStepsStatus((prev) => ({ ...prev, summary: 'done' }))
      }
    })

    on('coverage', (event) => {
      try {
        setCoverageNotice(JSON.parse(event.data))
      } catch { /* ignore a malformed coverage frame */ }
    })

    // Only update a step this build knows about, so a new backend agent cannot
    // silently desynchronise the progress count.
    on('agent_done', (event) => {
      const agent = event.data
      setStepsStatus((prev) => (agent in prev ? { ...prev, [agent]: 'done' } : prev))
    })
    on('agent_failed', (event) => {
      const agent = event.data
      setStepsStatus((prev) => (agent in prev ? { ...prev, [agent]: 'failed' } : prev))
    })

    on('cached', () => {
      setStepsStatus(Object.fromEntries(REVIEW_STEPS.map((s) => [s.id, 'done'])))
    })

    on('complete', (event) => {
      clearTimeout(watchdog)
      closed = true
      try {
        setData(JSON.parse(event.data))
        setStepsStatus((prev) => {
          const next = { ...prev }
          Object.keys(next).forEach((k) => { if (next[k] === 'active') next[k] = 'done' })
          return next
        })
        setLoading(false)
      } catch {
        setError('The finished review could not be read.')
        setLoading(false)
      }
      source.close()
    })

    // A server-sent `error` frame and a transport failure are both delivered as
    // an "error" event. Only the former carries data, which is how they are
    // told apart — otherwise a dropped connection masquerades as a pipeline
    // error and the real message never shows.
    source.addEventListener('error', (event) => {
      if (typeof event.data !== 'string') return
      clearTimeout(watchdog)
      closed = true
      setError(event.data)
      setLoading(false)
      source.close()
    })

    source.onerror = () => {
      if (closed || source.readyState !== EventSource.CLOSED) return
      clearTimeout(watchdog)
      closed = true
      setError('Lost the connection to the review stream.')
      setLoading(false)
    }

    return () => {
      closed = true
      clearTimeout(watchdog)
      source.close()
    }
  }, [repoId, prNumber, attempt])

  // Publish only after the review exists, and only when the user asked for it.
  const publish = useCallback(
    async (reviewId) => {
      setPublishState({ busy: true, error: null })
      try {
        await api(`/reviews/${reviewId}/publish`, { method: 'POST' })
        setData((prev) => (prev ? { ...prev, posted_to_github: true, github_error: null } : prev))
      } catch (err) {
        setPublishState({ busy: false, error: err.message })
        return
      }
      setPublishState({ busy: false, error: null })
    },
    []
  )

  const publishedRef = useRef(false)
  useEffect(() => {
    if (postToGitHub && data?.review_id && !data.posted_to_github && !publishedRef.current) {
      publishedRef.current = true
      publish(data.review_id)
    }
  }, [postToGitHub, data, publish])

  const files = data?.files_with_issues || []
  const activeFile = files[selectedFileIndex] || null
  useEffect(() => { setSelectedFileIndex(0) }, [data?.review_id])

  const stats = data?.stats
  const severity = stats?.by_severity || {}
  const score = stats?.score ?? 100
  const scoreLabel = stats?.score_label ?? ''
  const completedSteps = REVIEW_STEPS.filter((s) => stepsStatus[s.id] === 'done').length

  const radius = 58
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (circumference * score) / 100

  const copy = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text ?? '')
      setCopied(key)
      setTimeout(() => setCopied(null), 1800)
    } catch {
      setCopied(`${key}:failed`)
      setTimeout(() => setCopied(null), 2500)
    }
  }

  const handleAsk = async (event) => {
    event.preventDefault()
    const question = askInput.trim()
    if (!question || !data?.review_id) return

    const history = chatMessages.filter((m) => !m.greeting).map((m) => ({ sender: m.sender, text: m.text }))
    setChatMessages((prev) => [...prev, { sender: 'user', text: question }])
    setAskInput('')
    setChatMessages((prev) => [...prev, { sender: 'ai', text: 'Thinking…', loading: true }])

    try {
      const response = await api('/reviews/chat', {
        method: 'POST',
        body: JSON.stringify({ review_id: data.review_id, message: question, history }),
      })
      setChatMessages((prev) => [
        ...prev.filter((m) => !m.loading),
        { sender: 'ai', text: response.response },
      ])
    } catch (err) {
      setChatMessages((prev) => [
        ...prev.filter((m) => !m.loading),
        { sender: 'ai', text: `Sorry — ${err.message}` },
      ])
    }
  }

  const summaryBlocks = useMemo(() => {
    const raw = (data?.summary || '').trim()
    if (!raw) return null
    const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
    return {
      verdict: lines.find((l) => !l.startsWith('- ') && !l.startsWith('• ') && !/^recommendation:/i.test(l)),
      bullets: lines.filter((l) => l.startsWith('- ') || l.startsWith('• ')),
      recommendation: lines.find((l) => /^recommendation:/i.test(l)),
    }
  }, [data?.summary])

  // ------------------------------------------------------------------ views

  if (loading || error) {
    return (
      <div className="dashboard-shell">
        <aside className="side-nav">
          <div className="side-brand" style={{ cursor: 'pointer' }} onClick={onReset}>
            <div className="brand-title">CodeArmor</div>
            <div className="brand-label">Review workspace</div>
          </div>
          <button className="nav-cta" onClick={onReset}>← Back to repositories</button>
        </aside>

        <div className="dashboard-main">
          <header className="topbar">
            <div className="topbar-left">
              <div className="topbar-title">PR #{prNumber}</div>
              <div className="topbar-bread">
                <span>{repoFullName}</span>
                <span className="chevron">›</span>
                <span className="status" style={{ backgroundColor: '#fbbf24', color: '#09090c' }}>
                  {error ? 'Stopped' : 'Analysing'}
                </span>
              </div>
            </div>
          </header>

          <main className="workspace-area" style={{ padding: 40, justifyContent: 'center' }}>
            <div style={{ width: '100%', maxWidth: 820 }}>
              {error ? (
                <div className="error-banner" role="alert" style={{ padding: 24, borderRadius: 16 }}>
                  <h3 style={{ margin: '0 0 10px', color: 'var(--error-red)' }}>The review did not finish</h3>
                  <p style={{ margin: '0 0 20px', color: 'var(--text-gray)' }}>{error}</p>
                  <div className="row">
                    <button className="btn primary" onClick={() => setAttempt((n) => n + 1)}>
                      Try again
                    </button>
                    <button className="btn secondary" onClick={onReset}>Back to repositories</button>
                  </div>
                </div>
              ) : (
                <div className="active-review-panel" role="status" aria-live="polite">
                  <div className="active-review-header">
                    <div>
                      <h3>Reviewing {repoFullName} #{prNumber}</h3>
                      <p className="muted-text" style={{ marginTop: 4 }}>
                        {prTitle || 'Six agents are reading this pull request in parallel.'}
                      </p>
                    </div>
                    <div
                      className="progress-bar-container"
                      role="progressbar"
                      aria-valuenow={completedSteps}
                      aria-valuemin={0}
                      aria-valuemax={REVIEW_STEPS.length}
                      aria-label="Review progress"
                    >
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${(completedSteps / REVIEW_STEPS.length) * 100}%` }}
                      />
                    </div>
                  </div>

                  {coverageNotice && (
                    <p className="muted-text" style={{ marginBottom: 12 }}>
                      Large pull request: about {coverageNotice.reviewed_percent}% of the diff fits
                      in this review. {coverageNotice.files_not_reviewed?.length || 0} file(s) will
                      not be read.
                    </p>
                  )}

                  <div className="review-steps-grid">
                    {REVIEW_STEPS.map((step) => {
                      const status = stepsStatus[step.id] || 'pending'
                      return (
                        <div key={step.id} className={`step-card ${status}`}>
                          <div className="step-card-status">
                            <span className={`status-dot ${status}`} />
                          </div>
                          <div className="step-card-info">
                            <span className="step-name">{step.label}</span>
                            <span className="step-status-text">
                              {status === 'done' ? 'Done'
                                : status === 'active' ? 'Working…'
                                : status === 'failed' ? 'Failed'
                                : 'Queued'}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="active-review-actions">
                    <button className="btn secondary btn-small" onClick={onReset}>
                      Stop watching
                    </button>
                    <div className="step-counter">
                      {completedSteps} of {REVIEW_STEPS.length} complete
                    </div>
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    )
  }

  const readiness = data?.merge_readiness || {}
  const coverage = data?.coverage || {}
  const agentErrors = data?.agent_errors || []

  return (
    <div className="dashboard-shell">
      <aside className="side-nav">
        <div className="side-brand" style={{ cursor: 'pointer' }} onClick={onReset}>
          <div className="brand-title">CodeArmor</div>
          <div className="brand-label">Review workspace</div>
        </div>
        <button className="nav-cta" onClick={onReset}>← Back to repositories</button>

        <div className="side-footer">
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 8 }}>
            Repository
            <div style={{ fontWeight: 'bold', color: 'var(--text-dark)', wordBreak: 'break-all' }}>
              {repoFullName}
            </div>
          </div>
          {data?.created_at && (
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Reviewed {new Date(data.created_at).toLocaleString()}
              {data.cached && ' (saved result)'}
            </div>
          )}
        </div>
      </aside>

      <div className="dashboard-main">
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">PR #{prNumber}</div>
            <div className="topbar-bread">
              <span>{repoFullName}</span>
              <span className="chevron">›</span>
              <span className={`status status-${readiness.verdict || 'clear'}`}>
                {readiness.verdict === 'blocked' ? 'Not ready to merge'
                  : readiness.verdict === 'caution' ? 'Merge with care'
                  : 'Nothing blocking'}
              </span>
            </div>
          </div>
          <div className="topbar-right">
            <button
              className="topbar-button secondary"
              onClick={() => copy(data?.summary, 'summary')}
            >
              {copied === 'summary' ? 'Copied' : copied === 'summary:failed' ? 'Copy failed' : 'Copy summary'}
            </button>
            {!data?.posted_to_github && (
              <button
                className="topbar-button secondary"
                disabled={publishState.busy}
                onClick={() => publish(data.review_id)}
              >
                {publishState.busy ? 'Posting…' : 'Post to GitHub'}
              </button>
            )}
            <button className="topbar-button primary" onClick={onReset}>Close</button>
          </div>
        </header>

        <main className="workspace-area">
          <section className="code-column">
            <MergeGate readiness={readiness} coverage={coverage} agentErrors={agentErrors} />

            {data?.posted_to_github && (
              <p className="muted-text">Posted to the pull request as a comment.</p>
            )}
            {publishState.error && (
              <div className="error-banner" role="alert">
                Could not post to GitHub: {publishState.error}
              </div>
            )}
            {data?.github_error && (
              <div className="error-banner" role="alert">
                Could not post to GitHub: {data.github_error}
              </div>
            )}

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontFamily: 'var(--font-headings)', fontSize: '1.2rem', fontWeight: 600 }}>
                Findings by file
              </div>
              {files.length === 0 ? (
                <div className="file-header" style={{ backgroundColor: 'var(--bg-card-clay)' }}>
                  <div className="file-path">
                    <span className="material-symbols-outlined" aria-hidden="true">check_circle</span>
                    <span className="mono bold">No findings in the reviewed files</span>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }} role="tablist">
                  {files.map((file, idx) => (
                    <button
                      key={file.path}
                      role="tab"
                      aria-selected={idx === selectedFileIndex}
                      className={`btn toggle ${idx === selectedFileIndex ? 'active' : ''}`}
                      onClick={() => setSelectedFileIndex(idx)}
                      style={{ fontSize: '0.85rem' }}
                      title={file.path}
                    >
                      {file.path.split('/').pop()} ({file.issue_count})
                    </button>
                  ))}
                </div>
              )}
            </div>

            {activeFile && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="file-header">
                  <div className="file-path">
                    <span className="material-symbols-outlined" aria-hidden="true">description</span>
                    <span className="mono bold">{activeFile.path}</span>
                  </div>
                  <div className="file-meta">
                    <span>{activeFile.issue_count} finding(s)</span>
                  </div>
                </div>

                {activeFile.issues?.map((issue, index) => {
                  const level = String(issue.severity || '').toUpperCase()
                  const isBlocking = level === 'CRITICAL' || level === 'HIGH'
                  return (
                    <div key={index} className={`ai-card ${isBlocking ? 'danger' : ''}`}>
                      <div className="ai-card-header">
                        <span
                          className="ai-pill"
                          aria-label={`Severity: ${level}`}
                          style={{ backgroundColor: isBlocking ? 'var(--error-red)' : 'var(--text-dark)' }}
                        >
                          {level}
                        </span>
                        <span>{issue.category}</span>
                        {issue.line ? <span className="muted-text">line {issue.line}</span> : null}
                        {issue.agreement > 1 && (
                          <span className="muted-text">{issue.agreement} agents agreed</span>
                        )}
                      </div>

                      <h4 className="ai-card-title">Problem</h4>
                      <p className="ai-card-text">{issue.problem}</p>

                      {issue.code_snippet && (
                        <div style={{ marginBottom: 20 }}>
                          <div className="snippet-label">Current code</div>
                          <div className="code-panel" style={{ borderLeft: '3px solid var(--error-red)', padding: 12 }}>
                            <pre className="snippet"><code style={{ color: '#fca5a5' }}>{issue.code_snippet}</code></pre>
                          </div>
                        </div>
                      )}

                      {issue.recommendation && (
                        <>
                          <h4 className="ai-card-title" style={{ color: 'var(--success-green)' }}>
                            Recommendation
                          </h4>
                          {/* Prose renders as prose. The old condition was
                              `A || B || (C && D)` by operator precedence, so any
                              recommendation over 50 characters containing a space
                              — i.e. almost all of them — rendered as code. */}
                          <div className="ai-card-text">{formatMessageText(issue.recommendation)}</div>
                        </>
                      )}

                      {issue.suggestion_snippet && (
                        <div style={{ marginTop: 12, marginBottom: 20 }}>
                          <div className="snippet-label">Suggested fix</div>
                          <div className="code-panel" style={{ borderLeft: '3px solid var(--success-green)', padding: 12 }}>
                            <pre className="snippet"><code style={{ color: '#a7f3d0' }}>{issue.suggestion_snippet}</code></pre>
                          </div>
                        </div>
                      )}

                      <div className="ai-actions" style={{ display: 'flex', gap: 10, marginTop: 16 }}>
                        {issue.suggestion_snippet && (
                          <button
                            className="btn primary small"
                            onClick={() => copy(issue.suggestion_snippet, `fix-${index}`)}
                          >
                            {copied === `fix-${index}` ? 'Copied'
                              : copied === `fix-${index}:failed` ? 'Copy failed'
                              : 'Copy fix'}
                          </button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </section>

          <aside className="insights-column">
            <div className="score-widget">
              <div className="score-ring">
                <svg viewBox="0 0 128 128" role="img" aria-label={`Review score ${score} out of 100: ${scoreLabel}`}>
                  <circle className="ring-bg" cx="64" cy="64" r={radius} />
                  <circle
                    className="ring-fill"
                    cx="64"
                    cy="64"
                    r={radius}
                    style={{ strokeDasharray: circumference, strokeDashoffset }}
                  />
                </svg>
                <div className="score-label">
                  <span>{score}</span>
                  <small>{scoreLabel}</small>
                </div>
              </div>
              <h4>Review score</h4>
              <p>
                Computed from finding severity and how much of the diff was read.
                {coverage.truncated && ` Capped because only ${coverage.reviewed_percent}% was reviewed.`}
              </p>
            </div>

            {/* Four buckets matching the real vocabulary. Folding HIGH into a
                tile labelled "Critical" overstated severity in a security
                product and could not be reconciled with the per-issue pills. */}
            <div className="stats-grid stats-grid-4">
              <div className="stat-card danger"><span>{severity.CRITICAL ?? 0}</span><small>Critical</small></div>
              <div className="stat-card danger"><span>{severity.HIGH ?? 0}</span><small>High</small></div>
              <div className="stat-card secondary"><span>{severity.MEDIUM ?? 0}</span><small>Medium</small></div>
              <div className="stat-card tertiary"><span>{severity.LOW ?? 0}</span><small>Low</small></div>
            </div>

            <div className="summary-card">
              <h4>
                <span className="material-symbols-outlined summary-icon" aria-hidden="true">summarize</span>
                Summary
              </h4>
              {!summaryBlocks ? (
                <p>No summary was produced.</p>
              ) : (
                <div className="summary-body">
                  {summaryBlocks.verdict && <p className="summary-verdict">{summaryBlocks.verdict}</p>}
                  {summaryBlocks.bullets.length > 0 && (
                    <ul className="summary-points">
                      {summaryBlocks.bullets.map((b, i) => (
                        <li key={i}>{b.replace(/^[-•]\s*/, '')}</li>
                      ))}
                    </ul>
                  )}
                  {summaryBlocks.recommendation && (
                    <div className="summary-recommendation">
                      <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
                      <span>{summaryBlocks.recommendation.replace(/^recommendation:\s*/i, '')}</span>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Rendered from what actually happened. A hardcoded all-green
                timeline claimed "Completed Audit Report" even when agents failed. */}
            <div className="timeline-card">
              <h4>What ran</h4>
              {REVIEW_STEPS.map((step) => {
                const status = stepsStatus[step.id] || 'pending'
                return (
                  <div key={step.id} className={`timeline-step ${status}`}>
                    <span />
                    {step.label}
                    {status === 'failed' && <em> — failed</em>}
                  </div>
                )
              })}
            </div>

            <div className={`ask-card ${askExpanded ? 'expanded' : ''}`}>
              <div className="ask-header">
                <span className="material-symbols-outlined" aria-hidden="true">auto_awesome</span>
                <h4>Ask about this review</h4>
                <button
                  type="button"
                  className="ask-expand-btn"
                  aria-label={askExpanded ? 'Collapse the assistant panel' : 'Expand the assistant panel'}
                  onClick={() => setAskExpanded((v) => !v)}
                >
                  <span className="material-symbols-outlined" aria-hidden="true">
                    {askExpanded ? 'close_fullscreen' : 'open_in_full'}
                  </span>
                </button>
              </div>

              <div ref={chatLogRef} className="ask-chat-log" role="log" aria-live="polite">
                {chatMessages.map((msg, index) => (
                  <div key={index} className={`chat-bubble chat-${msg.sender}${msg.loading ? ' chat-loading' : ''}`}>
                    {formatMessageText(msg.text)}
                  </div>
                ))}
              </div>

              <form onSubmit={handleAsk} className="ask-input">
                <label htmlFor="ask-assistant" className="visually-hidden">
                  Ask a question about this review
                </label>
                <textarea
                  id="ask-assistant"
                  placeholder="Why does this finding matter?"
                  rows="2"
                  value={askInput}
                  onChange={(e) => setAskInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleAsk(e)
                    }
                  }}
                />
                <button type="submit" className="action-btn" aria-label="Send question">
                  <span className="material-symbols-outlined" aria-hidden="true">send</span>
                </button>
              </form>
            </div>
          </aside>
        </main>
      </div>
    </div>
  )
}
