import React, { useState, useEffect, useRef } from 'react'
import { api, API_BASE } from '../api'

const REVIEW_STEPS = [
  { id: 'fetch_diff', label: 'Fetching PR Diff' },
  { id: 'security', label: 'Security Analysis Agent' },
  { id: 'quality', label: 'Code Quality Agent' },
  { id: 'performance', label: 'Performance Agent' },
  { id: 'testing', label: 'Testing Agent' },
  { id: 'architecture', label: 'Architecture Agent' },
  { id: 'summary', label: 'Summary Generator' },
  { id: 'github_post', label: 'Posting comments to GitHub' }
]

export default function ReviewDashboard({ repo, prNumber, reviewData, onReset }) {
  const [selectedFileIndex, setSelectedFileIndex] = useState(0)
  const [askInput, setAskInput] = useState('')
  const [askExpanded, setAskExpanded] = useState(false)
  const [chatMessages, setChatMessages] = useState([
    {
      sender: 'ai',
      text: 'Hi, I’m the AI Review Assistant. Ask me anything about the pull request, code suggestions, or safety checks.'
    }
  ])

  const [stepsStatus, setStepsStatus] = useState({
    fetch_diff: 'pending',
    security: 'pending',
    quality: 'pending',
    performance: 'pending',
    testing: 'pending',
    architecture: 'pending',
    summary: 'pending',
    github_post: 'pending',
  })
  const [loadingReview, setLoadingReview] = useState(!reviewData)
  const [reviewError, setReviewError] = useState(null)
  const [currentReviewData, setCurrentReviewData] = useState(reviewData)

  const chatLogRef = useRef(null)

  useEffect(() => {
    if (chatLogRef.current) {
      chatLogRef.current.scrollTop = chatLogRef.current.scrollHeight
    }
  }, [chatMessages])

  useEffect(() => {
    if (reviewData) {
      setCurrentReviewData(reviewData)
      setLoadingReview(false)
      return
    }

    setLoadingReview(true)
    setReviewError(null)
    setStepsStatus({
      fetch_diff: 'active',
      security: 'pending',
      quality: 'pending',
      performance: 'pending',
      testing: 'pending',
      architecture: 'pending',
      summary: 'pending',
      github_post: 'pending',
    })

    const prUrl = `https://github.com/${repo}/pull/${prNumber}`
    const eventSource = new EventSource(
      `${API_BASE}/review/stream?pr_url=${encodeURIComponent(prUrl)}`,
      { withCredentials: true }
    )

    eventSource.addEventListener('step', (e) => {
      const stepEvent = e.data
      if (stepEvent === 'fetch_diff_done') {
        setStepsStatus(prev => ({
          ...prev,
          fetch_diff: 'done',
          security: 'active',
          quality: 'active',
          performance: 'active',
          testing: 'active',
          architecture: 'active',
        }))
      } else if (stepEvent === 'summary_start') {
        setStepsStatus(prev => ({
          ...prev,
          security: prev.security === 'active' || prev.security === 'pending' ? 'done' : prev.security,
          quality: prev.quality === 'active' || prev.quality === 'pending' ? 'done' : prev.quality,
          performance: prev.performance === 'active' || prev.performance === 'pending' ? 'done' : prev.performance,
          testing: prev.testing === 'active' || prev.testing === 'pending' ? 'done' : prev.testing,
          architecture: prev.architecture === 'active' || prev.architecture === 'pending' ? 'done' : prev.architecture,
          summary: 'active',
        }))
      } else if (stepEvent === 'summary_done') {
        setStepsStatus(prev => ({ ...prev, summary: 'done', github_post: 'active' }))
      } else if (stepEvent === 'github_post_done') {
        setStepsStatus(prev => ({ ...prev, github_post: 'done' }))
      }
    })

    eventSource.addEventListener('agent_done', (e) => {
      const agentName = e.data
      setStepsStatus(prev => ({ ...prev, [agentName]: 'done' }))
    })

    eventSource.addEventListener('agent_failed', (e) => {
      const agentName = e.data
      setStepsStatus(prev => ({ ...prev, [agentName]: 'failed' }))
    })

    eventSource.addEventListener('complete', (e) => {
      try {
        const data = JSON.parse(e.data)
        setCurrentReviewData(data)
        setLoadingReview(false)
        eventSource.close()
      } catch (err) {
        setReviewError('Failed to parse final review response.')
        eventSource.close()
      }
    })

    eventSource.addEventListener('error', (e) => {
      setReviewError(e.data || 'Review process encountered an error.')
      eventSource.close()
    })

    eventSource.onerror = (e) => {
      if (eventSource.readyState === EventSource.CLOSED) {
        return
      }
      setReviewError('Connection to review stream lost.')
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [repo, prNumber, reviewData])

  // Extract file list from currentReviewData
  const files = currentReviewData?.files_with_issues || []
  const activeFile = files[selectedFileIndex] || null

  // Calculate completed steps based on stepsStatus
  const completedSteps = REVIEW_STEPS.filter(step => stepsStatus[step.id] === 'done').length

  // Calculate severity counts (case-insensitive and summed)
  const severityMap = {}
  if (currentReviewData?.stats?.by_severity) {
    for (const [key, value] of Object.entries(currentReviewData.stats.by_severity)) {
      severityMap[key.toLowerCase()] = value
    }
  }
  const criticalCount = (severityMap.critical || 0) + (severityMap.high || 0)
  const warningCount = (severityMap.warning || 0) + (severityMap.medium || 0)
  const hintCount = (severityMap.info || 0) + (severityMap.low || 0)

  // Calculate score dynamically based on severity weights
  const totalIssues = currentReviewData?.stats?.total_issues ?? 0
  const score = Math.max(0, 100 - (criticalCount * 15 + warningCount * 8 + hintCount * 3))
  const scoreLabel = score >= 90 ? 'Excellent' : score >= 75 ? 'Good' : score >= 50 ? 'Fair' : 'Needs Work'

  // Calculate SVG circle properties
  const radius = 58
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (circumference * score) / 100

  // Helper to format response messages with basic markdown support (code blocks, inline code)
  const formatInline = (line, keyPrefix) => {
    const inlineParts = line.split(/(`[^`\n]+`|\*\*[^*\n]+\*\*)/g)
    return inlineParts.map((subPart, subIdx) => {
      if (subPart.startsWith('`') && subPart.endsWith('`')) {
        return (
          <code key={`${keyPrefix}-${subIdx}`} style={{
            backgroundColor: 'rgba(0, 0, 0, 0.05)',
            padding: '2px 4px',
            borderRadius: '4px',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.85em',
            wordBreak: 'break-all'
          }}>
            {subPart.slice(1, -1)}
          </code>
        );
      }
      if (subPart.startsWith('**') && subPart.endsWith('**')) {
        return <strong key={`${keyPrefix}-${subIdx}`}>{subPart.slice(2, -2)}</strong>;
      }
      return subPart;
    });
  };

  const formatMessageText = (text) => {
    if (!text) return '';
    const parts = text.split(/(```[\s\S]*?```)/g);
    return parts.map((part, idx) => {
      if (part.startsWith('```')) {
        const lines = part.slice(3, -3).trim().split('\n');
        let code = part.slice(3, -3).trim();
        if (lines.length > 0 && /^[a-zA-Z0-9_-]+$/.test(lines[0])) {
          code = lines.slice(1).join('\n');
        }
        return (
          <pre key={idx} style={{
            backgroundColor: 'rgba(0, 0, 0, 0.05)',
            padding: '8px',
            borderRadius: '6px',
            overflowX: 'auto',
            margin: '8px 0',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.78rem',
            borderLeft: '3px solid var(--text-dark)',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-all'
          }}>
            <code>{code}</code>
          </pre>
        );
      }

      const lines = part.split('\n');
      return (
        <span key={idx} style={{ whiteSpace: 'pre-wrap' }}>
          {lines.map((line, lineIdx) => {
            const headingMatch = line.match(/^(#{1,4})\s+(.*)$/);
            const bulletMatch = line.match(/^(\s*)[-*]\s+(.*)$/);
            let content;
            if (headingMatch) {
              content = (
                <strong style={{ display: 'inline-block', fontSize: '0.95em', marginTop: lineIdx > 0 ? 6 : 0 }}>
                  {formatInline(headingMatch[2], `${idx}-${lineIdx}`)}
                </strong>
              );
            } else if (bulletMatch) {
              content = (
                <span style={{ display: 'inline-flex', gap: 6, paddingLeft: bulletMatch[1].length * 6 }}>
                  <span style={{ flexShrink: 0 }}>•</span>
                  <span>{formatInline(bulletMatch[2], `${idx}-${lineIdx}`)}</span>
                </span>
              );
            } else {
              content = formatInline(line, `${idx}-${lineIdx}`);
            }
            return (
              <React.Fragment key={lineIdx}>
                {lineIdx > 0 && '\n'}
                {content}
              </React.Fragment>
            );
          })}
        </span>
      );
    });
  };

  // Handle Ask AI interaction using the real backend /review/chat endpoint
  const handleAskSubmit = async (e) => {
    e.preventDefault()
    if (!askInput.trim()) return

    const userMsg = askInput.trim()
    setChatMessages((prev) => [...prev, { sender: 'user', text: userMsg }])
    setAskInput('')

    // Add a loading placeholder
    setChatMessages((prev) => [...prev, { sender: 'ai', text: 'Thinking...', loading: true }])

    // Build chat history matching the format expected by the backend
    const history = chatMessages.map(msg => ({ sender: msg.sender, text: msg.text }))

    // Flatten all issues from files to pass as context
    const flatIssues = []
    if (currentReviewData && currentReviewData.files_with_issues) {
      currentReviewData.files_with_issues.forEach(file => {
        if (file.issues) {
          file.issues.forEach(issue => {
            flatIssues.push({
              file: file.path,
              severity: issue.severity,
              category: issue.category,
              problem: issue.problem,
              recommendation: issue.recommendation,
              code_snippet: issue.code_snippet,
              suggestion_snippet: issue.suggestion_snippet
            })
          })
        }
      })
    }

    try {
      const data = await api('/review/chat', {
        method: 'POST',
        body: JSON.stringify({
          message: userMsg,
          history: history,
          issues: flatIssues
        })
      })

      setChatMessages((prev) => {
        const filtered = prev.filter(msg => !msg.loading)
        return [...filtered, { sender: 'ai', text: data.response }]
      })
    } catch (err) {
      setChatMessages((prev) => {
        const filtered = prev.filter(msg => !msg.loading)
        return [...filtered, { sender: 'ai', text: `Error: ${err.message}` }]
      })
    }
  }

  // Handle suggestion copying
  const copyToClipboard = (text) => {
    navigator.clipboard.writeText(text)
    alert('Code suggestion copied to clipboard!')
  }

  if (loadingReview) {
    return (
      <div className="dashboard-shell">
        {/* Sidebar Navigation */}
        <aside className="side-nav">
          <div className="side-brand" style={{ cursor: 'pointer', gap: '0px' }} onClick={onReset}>
            <div>
              <div className="brand-title" style={{ fontSize: '1.25rem', fontWeight: 800 }}>CodeArmor</div>
              <div className="brand-label">Dashboard Workspace</div>
            </div>
          </div>

          <button className="nav-cta" onClick={onReset}>
            ← Cancel Review
          </button>

          <nav className="side-menu">
            <a className="nav-link active" href="#" onClick={(e) => e.preventDefault()}>
              <span className="material-symbols-outlined" style={{ marginRight: 8, fontSize: '1.2rem' }}>sync</span>
              Reviewing…
            </a>
          </nav>
        </aside>

        {/* Main Dashboard Space */}
        <div className="dashboard-main">
          <header className="topbar">
            <div className="topbar-left">
              <div className="topbar-title">PR #{prNumber || 'Review'}</div>
              <div className="topbar-bread">
                <span>{repo}</span>
                <span className="chevron">›</span>
                <span className="status" style={{ backgroundColor: '#fbbf24', color: '#09090c' }}>Analyzing</span>
              </div>
            </div>
            <div className="topbar-right">
              <button className="topbar-button secondary" onClick={onReset}>
                Cancel
              </button>
            </div>
          </header>

          <main className="workspace-area" style={{ padding: '40px', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
            <div style={{ width: '100%', maxWidth: '800px' }}>
              {reviewError ? (
                <div className="error-banner" style={{ padding: '24px', borderRadius: '16px' }}>
                  <h3 style={{ margin: '0 0 10px 0', color: 'var(--error-red)' }}>Analysis Pipeline Failed</h3>
                  <p style={{ margin: '0 0 20px 0', color: 'var(--text-gray)' }}>{reviewError}</p>
                  <button className="btn primary" onClick={onReset}>Back to Repositories</button>
                </div>
              ) : (
                <div className="active-review-panel">
                  <div className="active-review-header">
                    <div>
                      <h3>Active Review Progress</h3>
                      <p className="muted-text" style={{ marginTop: '4px' }}>Running test suites & static analysis for {repo}</p>
                    </div>
                    <div className="progress-bar-container">
                      <div className="progress-bar-fill" style={{ width: `${(completedSteps / REVIEW_STEPS.length) * 100}%` }}></div>
                    </div>
                  </div>

                  <div className="review-steps-grid">
                    {REVIEW_STEPS.map((step) => {
                      const status = stepsStatus[step.id] || 'pending';

                      return (
                        <div key={step.id} className={`step-card ${status}`}>
                          <div className="step-card-status">
                            <span className={`status-dot ${status}`}></span>
                          </div>
                          <div className="step-card-info">
                            <span className="step-name">{step.label}</span>
                            <span className="step-status-text">
                              {status === 'done' ? 'Completed' : status === 'active' ? 'Analyzing…' : status === 'failed' ? 'Failed' : 'Queued'}
                            </span>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div className="active-review-actions">
                    <button className="btn secondary btn-small" onClick={onReset}>
                      Cancel Review
                    </button>
                    <div className="step-counter">
                      Pipeline Step {Math.min(completedSteps + 1, REVIEW_STEPS.length)} of {REVIEW_STEPS.length}
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

  return (
    <div className="dashboard-shell">
      {/* Sidebar Navigation */}
      <aside className="side-nav">
        <div className="side-brand" style={{ cursor: 'pointer', gap: '0px' }} onClick={onReset}>
          <div>
            <div className="brand-title" style={{ fontSize: '1.25rem', fontWeight: 800 }}>CodeArmor</div>
            <div className="brand-label">Dashboard Workspace</div>
          </div>
        </div>

        <button className="nav-cta" onClick={onReset}>
          ← Back to Repos
        </button>

        <nav className="side-menu">
          <a className="nav-link active" href="#" onClick={(e) => e.preventDefault()}>
            <span className="material-symbols-outlined" style={{ marginRight: 8, fontSize: '1.2rem' }}>dashboard</span>
            Dashboard
          </a>
          <a className="nav-link" href="#" onClick={(e) => { e.preventDefault(); onReset(); }}>
            <span className="material-symbols-outlined" style={{ marginRight: 8, fontSize: '1.2rem' }}>list</span>
            Repositories
          </a>
        </nav>

        <div className="side-footer">
          <div style={{ fontSize: '0.82rem', color: 'var(--text-muted)', marginBottom: 8 }}>
            Repository:
            <div style={{ fontWeight: 'bold', color: 'var(--text-dark)', wordBreak: 'break-all' }}>{repo}</div>
          </div>
          <a className="footer-link" href="#" onClick={(e) => e.preventDefault()}>Support & Docs</a>
        </div>
      </aside>

      {/* Main Dashboard Space */}
      <div className="dashboard-main">
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-title">PR #{prNumber || 'Review'}</div>
            <div className="topbar-bread">
              <span>{repo}</span>
              <span className="chevron">›</span>
              <span className="status">AI Reviewed</span>
            </div>
          </div>

          <div className="topbar-right">
            <button className="topbar-button secondary" onClick={() => copyToClipboard(currentReviewData?.summary || '')}>
              Copy Summary
            </button>
            <button className="topbar-button primary" onClick={onReset}>
              Close Report
            </button>
          </div>
        </header>

        {/* Workspace Layout */}
        <main className="workspace-area">
          {/* Code & Issues List */}
          <section className="code-column">
            {/* PR Overview Card */}
            <div className="review-header">
              <div>
                <div className="review-tag">{repo}</div>
                <p className="review-meta">
                  Reviewed branch merges • Found <span className="mono bold">{totalIssues}</span> issues across <span className="mono bold">{currentReviewData?.stats?.files_affected || files.length}</span> file(s).
                </p>
              </div>
              <div className="review-statuses">
                <span className="status-chip success">Review Complete</span>
              </div>
            </div>

            {currentReviewData?.github_error && (
              <div className="error-banner" style={{ marginTop: '0px', marginBottom: '20px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span className="material-symbols-outlined" style={{ fontSize: '1.2rem' }}>warning</span>
                  <strong>Review Posted Locally Only</strong>
                </div>
                <div style={{ fontSize: '0.85rem', fontWeight: 'normal', color: 'var(--text-gray)' }}>
                  We couldn't write the review comments back to your GitHub Pull Request because:
                  <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem', backgroundColor: 'rgba(0, 0, 0, 0.2)', padding: '6px 10px', borderRadius: '4px', marginTop: '6px', border: '1px solid var(--border-light)', wordBreak: 'break-all' }}>
                    {currentReviewData.github_error}
                  </div>
                </div>
              </div>
            )}

            {/* File List tabs (Sage Green pastel background) */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              <div style={{ fontFamily: 'var(--font-headings)', fontSize: '1.2rem', fontWeight: 600 }}>Files with Issues</div>
              {files.length === 0 ? (
                <div className="file-header" style={{ backgroundColor: 'var(--bg-card-clay)' }}>
                  <div className="file-path">
                    <span className="material-symbols-outlined">check_circle</span>
                    <span className="mono bold">No issues found in files!</span>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                  {files.map((file, idx) => (
                    <button
                      key={file.path}
                      className={`btn toggle ${idx === selectedFileIndex ? 'active' : ''}`}
                      onClick={() => setSelectedFileIndex(idx)}
                      style={{ fontSize: '0.85rem' }}
                    >
                      <span className="material-symbols-outlined" style={{ fontSize: '1.1rem', marginRight: 4 }}>description</span>
                      {file.path.split('/').pop()} ({file.issue_count})
                    </button>
                  ))}
                </div>
              )}
            </div>

            {/* Selected File Details */}
            {activeFile && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div className="file-header">
                  <div className="file-path">
                    <span className="material-symbols-outlined">description</span>
                    <span className="mono bold">{activeFile.path}</span>
                  </div>
                  <div className="file-meta">
                    <span>{activeFile.issue_count} issue(s) detected</span>
                  </div>
                </div>

                {/* Render the list of issues for the active file */}
                {activeFile.issues?.map((issue, index) => (
                  <div key={index} className="ai-card danger">
                    <div className="ai-card-header">
                      <span className="ai-pill" style={{
                        backgroundColor: issue.severity.toLowerCase() === 'critical' || issue.severity.toLowerCase() === 'high' ? 'var(--error-red)' : 'var(--text-dark)'
                      }}>
                        {issue.severity.toUpperCase()}
                      </span>
                      <span>Category: {issue.category}</span>
                    </div>

                    <h4 style={{ fontFamily: 'var(--font-headings)', margin: '0 0 10px 0', fontSize: '1.2rem' }}>Problem</h4>
                    <p style={{ margin: '0 0 16px 0', fontSize: '0.95rem', lineHeight: 1.5 }}>{issue.problem}</p>

                    {issue.code_snippet && (
                      <div style={{ marginBottom: '20px' }}>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="material-symbols-outlined" style={{ fontSize: '1rem', color: 'var(--error-red)' }}>code</span>
                          Original Code Snippet
                        </div>
                        <div className="code-panel" style={{ borderLeft: '3px solid var(--error-red)', padding: '12px' }}>
                          <pre style={{ margin: 0, overflowX: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}><code style={{ color: '#fca5a5' }}>{issue.code_snippet}</code></pre>
                        </div>
                      </div>
                    )}

                    {issue.recommendation && (
                      <>
                        <h4 style={{ fontFamily: 'var(--font-headings)', margin: '0 0 10px 0', fontSize: '1.1rem', color: 'var(--success-green)' }}>Recommendation</h4>
                        {issue.recommendation.includes('\n') || issue.recommendation.startsWith('`') || issue.recommendation.includes(' ') && issue.recommendation.length > 50 ? (
                          <div className="code-suggestion" style={{ marginBottom: '16px' }}>
                            <pre><code>{issue.recommendation.replace(/```/g, '')}</code></pre>
                          </div>
                        ) : (
                          <p style={{ margin: '0 0 16px 0', fontSize: '0.9rem', lineHeight: 1.5 }} className="code-inline">{issue.recommendation}</p>
                        )}
                      </>
                    )}

                    {issue.suggestion_snippet && (
                      <div style={{ marginBottom: '20px', marginTop: '12px' }}>
                        <div style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '6px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span className="material-symbols-outlined" style={{ fontSize: '1rem', color: 'var(--success-green)' }}>bolt</span>
                          Suggested Fix Snippet
                        </div>
                        <div className="code-panel" style={{ borderLeft: '3px solid var(--success-green)', padding: '12px' }}>
                          <pre style={{ margin: 0, overflowX: 'auto', fontFamily: 'var(--font-mono)', fontSize: '0.82rem' }}><code style={{ color: '#a7f3d0' }}>{issue.suggestion_snippet}</code></pre>
                        </div>
                      </div>
                    )}

                    <div className="ai-actions" style={{ display: 'flex', gap: '10px', marginTop: '16px' }}>
                      {issue.suggestion_snippet && (
                        <button className="btn primary small" onClick={() => copyToClipboard(issue.suggestion_snippet)}>
                          <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>content_copy</span>
                          Copy Solution Code
                        </button>
                      )}
                      {issue.recommendation && (
                        <button className={`btn small ${issue.suggestion_snippet ? 'secondary' : 'primary'}`} onClick={() => copyToClipboard(issue.recommendation)}>
                          {!issue.suggestion_snippet && <span className="material-symbols-outlined" style={{ fontSize: '1rem' }}>content_copy</span>}
                          Copy Explanation
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </section>

          {/* Insights Panel (Clay/Beige background) */}
          <aside className="insights-column">
            {/* Score Ring Widget */}
            <div className="score-widget">
              <div className="score-ring">
                <svg viewBox="0 0 128 128">
                  <circle className="ring-bg" cx="64" cy="64" r={radius} />
                  <circle
                    className="ring-fill"
                    cx="64"
                    cy="64"
                    r={radius}
                    style={{
                      strokeDasharray: circumference,
                      strokeDashoffset: strokeDashoffset
                    }}
                  />
                </svg>
                <div className="score-label">
                  <span>{score}</span>
                  <small>{scoreLabel}</small>
                </div>
              </div>
              <h4>Review Quality Score</h4>
              <p>PR scored {score}/100. Lower scores indicate more critical recommendations.</p>
            </div>

            {/* Severity Distribution Widgets */}
            <div className="stats-grid">
              <div className="stat-card danger">
                <span>{criticalCount}</span>
                <small>Critical</small>
              </div>
              <div className="stat-card secondary">
                <span>{warningCount}</span>
                <small>Warning</small>
              </div>
              <div className="stat-card tertiary">
                <span>{hintCount}</span>
                <small>Hints/Info</small>
              </div>
            </div>

            {/* Executive Summary */}
            <div className="summary-card">
              <h4>
                <span className="material-symbols-outlined summary-icon">summarize</span>
                Executive Summary
              </h4>
              {(() => {
                const raw = (currentReviewData?.summary || '').trim()
                if (!raw) return <p>No review summary provided.</p>

                const lines = raw.split('\n').map(l => l.trim()).filter(Boolean)
                const bullets = lines.filter(l => l.startsWith('- ') || l.startsWith('• '))
                const recLine = lines.find(l => /^recommendation:/i.test(l))
                const verdict = lines.find(l => !l.startsWith('- ') && !l.startsWith('• ') && !/^recommendation:/i.test(l))

                // Fallback: unstructured summary from older reviews
                if (!bullets.length && !recLine) return <p>{raw}</p>

                return (
                  <div className="summary-body">
                    {verdict && <p className="summary-verdict">{verdict}</p>}
                    {bullets.length > 0 && (
                      <ul className="summary-points">
                        {bullets.map((b, i) => (
                          <li key={i}>{b.replace(/^[-•]\s*/, '')}</li>
                        ))}
                      </ul>
                    )}
                    {recLine && (
                      <div className="summary-recommendation">
                        <span className="material-symbols-outlined">arrow_forward</span>
                        <span>{recLine.replace(/^recommendation:\s*/i, '')}</span>
                      </div>
                    )}
                  </div>
                )
              })()}
            </div>

            {/* Analysis Timeline */}
            <div className="timeline-card">
              <h4>Analysis Timeline</h4>
              <div className="timeline-step done"><span />Fetched PR Data</div>
              <div className="timeline-step done"><span />Parsed Diff Tree</div>
              <div className="timeline-step done"><span />Ran AI Review Agents</div>
              <div className="timeline-step done"><span />Completed Audit Report</div>
            </div>

            {/* Interactive Ask AI Widget */}
            <div className={`ask-card ${askExpanded ? 'expanded' : ''}`}>
              <div className="ask-header">
                <span className="material-symbols-outlined">auto_awesome</span>
                <h4>Ask Review Assistant</h4>
                <button
                  type="button"
                  className="ask-expand-btn"
                  title={askExpanded ? 'Collapse panel' : 'Expand to full height'}
                  onClick={() => setAskExpanded(prev => !prev)}
                >
                  <span className="material-symbols-outlined">
                    {askExpanded ? 'close_fullscreen' : 'open_in_full'}
                  </span>
                </button>
              </div>

               {/* Chat log */}
              <div
                ref={chatLogRef}
                className="ask-chat-log"
                style={{
                  maxHeight: askExpanded ? 'none' : '220px',
                  flex: askExpanded ? 1 : 'none',
                  overflowY: 'auto',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  fontSize: askExpanded ? '0.88rem' : '0.82rem',
                  borderBottom: '1px solid var(--border-light)',
                  paddingBottom: 10
                }}
              >
                {chatMessages.map((msg, index) => (
                  <div key={index} style={{
                    alignSelf: msg.sender === 'user' ? 'flex-end' : 'flex-start',
                    backgroundColor: msg.sender === 'user' ? 'var(--text-dark)' : 'var(--bg-white)',
                    color: msg.sender === 'user' ? 'var(--bg-cream)' : 'var(--text-dark)',
                    padding: '6px 10px',
                    borderRadius: '8px',
                    maxWidth: '85%',
                    border: msg.sender === 'ai' ? '1px solid var(--border-light)' : 'none',
                    lineHeight: 1.4,
                    fontStyle: msg.loading ? 'italic' : 'normal',
                    opacity: msg.loading ? 0.7 : 1
                  }}>
                    {formatMessageText(msg.text)}
                  </div>
                ))}
              </div>

              <form onSubmit={handleAskSubmit} className="ask-input">
                <textarea
                  placeholder="Ask a question about this PR..."
                  rows="2"
                  value={askInput}
                  onChange={(e) => setAskInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey) {
                      e.preventDefault()
                      handleAskSubmit(e)
                    }
                  }}
                />
                <button type="submit" className="action-btn">
                  <span className="material-symbols-outlined">send</span>
                </button>
              </form>
            </div>
          </aside>
        </main>
      </div>
    </div>
  )
}
