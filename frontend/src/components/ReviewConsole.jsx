import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AnimatePresence, MotionProvider, m, useVariants } from '../lib/motion.jsx'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  Copy,
  FileCode2,
  Send,
  Sparkles,
  X,
} from 'lucide-react'
import { GithubMark } from './BrandIcons'
import { api, API_BASE } from '../api'
import MergeGate from './MergeGate'
import TracePanel from './TracePanel'
import { formatMessageText } from '../lib/markdown.jsx'
import {
  Banner,
  Empty,
  Readout,
  SeverityTag,
  StatusIcon,
  Tag,
  formatCost,
  formatDuration,
  statusMeta,
  verdictMeta,
} from './primitives'

const STAGES = [
  { id: 'fetch_diff', label: 'Fetch diff and GitHub facts' },
  { id: 'security', label: 'Security' },
  { id: 'quality', label: 'Code quality' },
  { id: 'performance', label: 'Performance' },
  { id: 'testing', label: 'Testing' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'integration', label: 'Integration and merge readiness' },
  { id: 'summary', label: 'Reconcile, gate and summarise' },
]

const PENDING = Object.fromEntries(STAGES.map((s) => [s.id, 'pending']))

// Nothing has arrived for this long: the stream is dead rather than slow.
const WATCHDOG_MS = 180000

const TABS = [
  { id: 'findings', label: 'Findings' },
  { id: 'summary', label: 'Summary' },
  { id: 'trace', label: 'Trace' },
  { id: 'ask', label: 'Ask' },
]

export default function ReviewConsole(props) {
  // The provider lives here rather than at the root: this is the only surface
  // that animates, and it is lazy-loaded.
  return (
    <MotionProvider>
      <Console {...props} />
    </MotionProvider>
  )
}

function Console({ review, onExit }) {
  const { repoId, repoFullName, prNumber, prTitle, postToGitHub, reviewId } = review
  const { fade, popIn } = useVariants()

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [stages, setStages] = useState(PENDING)
  const [coverageNotice, setCoverageNotice] = useState(null)
  const [attempt, setAttempt] = useState(0)

  const [tab, setTab] = useState('findings')
  const [fileIndex, setFileIndex] = useState(0)
  const [copied, setCopied] = useState(null)
  const [publish, setPublish] = useState({ busy: false, error: null })

  const [question, setQuestion] = useState('')
  const [chat, setChat] = useState([
    { sender: 'ai', text: 'Ask why a finding matters, or how to apply one of the fixes.' },
  ])
  const chatRef = useRef(null)

  useEffect(() => {
    if (chatRef.current) chatRef.current.scrollTop = chatRef.current.scrollHeight
  }, [chat])

  // --- load a stored review ----------------------------------------------
  useEffect(() => {
    if (!reviewId || attempt > 0) return undefined
    let cancelled = false
    setLoading(true)
    setError(null)
    api(`/reviews/${reviewId}`)
      .then((stored) => {
        if (cancelled) return
        setData(stored)
        setStages(Object.fromEntries(STAGES.map((s) => [s.id, 'done'])))
        setLoading(false)
      })
      .catch((err) => {
        if (cancelled) return
        setError(err.message)
        setLoading(false)
      })
    return () => { cancelled = true }
  }, [reviewId, attempt])

  // --- run a new review ---------------------------------------------------
  useEffect(() => {
    // A stored review is fetched above; only re-stream when the user asked
    // for a fresh run.
    if (reviewId && attempt === 0) return undefined
    if (!repoId) {
      setError('This review is not linked to a connected repository, so it cannot be re-run.')
      setLoading(false)
      return undefined
    }

    let closed = false
    setLoading(true)
    setError(null)
    setCoverageNotice(null)
    setStages({ ...PENDING, fetch_diff: 'active' })

    const source = new EventSource(
      `${API_BASE}/reviews/stream?repo_id=${repoId}&pr_number=${prNumber}` +
        (attempt > 0 ? '&refresh=true' : ''),
      { withCredentials: true }
    )

    let watchdog
    const kick = () => {
      clearTimeout(watchdog)
      watchdog = setTimeout(() => {
        if (closed) return
        closed = true
        source.close()
        setError('The review stopped responding. Nothing has arrived for a few minutes.')
        setLoading(false)
      }, WATCHDOG_MS)
    }
    kick()

    const on = (name, handler) =>
      source.addEventListener(name, (event) => {
        kick()
        handler(event)
      })

    on('step', (event) => {
      if (event.data === 'fetch_diff_done') {
        setStages((prev) => {
          const next = { ...prev, fetch_diff: 'done' }
          STAGES.slice(1, -1).forEach((s) => { next[s.id] = 'active' })
          return next
        })
      } else if (event.data === 'summary_done') {
        setStages((prev) => ({ ...prev, summary: 'done' }))
      }
    })

    on('coverage', (event) => {
      try {
        setCoverageNotice(JSON.parse(event.data))
      } catch { /* a malformed coverage frame is not worth failing over */ }
    })

    // Only touch a stage this build knows about, so adding an agent on the
    // backend cannot silently desynchronise the progress count.
    on('agent_done', (e) =>
      setStages((prev) => (e.data in prev ? { ...prev, [e.data]: 'done' } : prev))
    )
    on('agent_failed', (e) =>
      setStages((prev) => (e.data in prev ? { ...prev, [e.data]: 'failed' } : prev))
    )
    on('cached', () => setStages(Object.fromEntries(STAGES.map((s) => [s.id, 'done']))))

    on('complete', (event) => {
      clearTimeout(watchdog)
      closed = true
      try {
        setData(JSON.parse(event.data))
        setStages((prev) => {
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

    // A server-sent `error` frame and a transport failure arrive as the same
    // event type. Only the former carries data, which is how they are told
    // apart - otherwise a dropped connection masks the real message.
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
  }, [repoId, prNumber, attempt, reviewId])

  const publishToGitHub = useCallback(async (reviewId) => {
    setPublish({ busy: true, error: null })
    try {
      await api(`/reviews/${reviewId}/publish`, { method: 'POST' })
      setData((prev) => (prev ? { ...prev, posted_to_github: true, github_error: null } : prev))
      setPublish({ busy: false, error: null })
    } catch (err) {
      setPublish({ busy: false, error: err.message })
    }
  }, [])

  const published = useRef(false)
  useEffect(() => {
    if (postToGitHub && data?.review_id && !data.posted_to_github && !published.current) {
      published.current = true
      publishToGitHub(data.review_id)
    }
  }, [postToGitHub, data, publishToGitHub])

  useEffect(() => { setFileIndex(0) }, [data?.review_id])

  const files = data?.files_with_issues || []
  const activeFile = files[fileIndex] || null
  const stats = data?.stats
  const severity = stats?.by_severity || {}
  const readiness = data?.merge_readiness || {}
  const done = STAGES.filter((s) => stages[s.id] === 'done').length

  const copy = async (text, key) => {
    try {
      await navigator.clipboard.writeText(text ?? '')
      setCopied(key)
    } catch {
      setCopied(`${key}:failed`)
    }
    setTimeout(() => setCopied(null), 1800)
  }

  const ask = async (event) => {
    event.preventDefault()
    const text = question.trim()
    if (!text || !data?.review_id) return

    const history = chat.slice(1).map((m) => ({ sender: m.sender, text: m.text }))
    setChat((prev) => [...prev, { sender: 'user', text }])
    setQuestion('')
    setChat((prev) => [...prev, { sender: 'ai', text: 'Thinking', loading: true }])

    try {
      const response = await api('/reviews/chat', {
        method: 'POST',
        body: JSON.stringify({ review_id: data.review_id, message: text, history }),
      })
      setChat((prev) => [...prev.filter((m) => !m.loading), { sender: 'ai', text: response.response }])
    } catch (err) {
      setChat((prev) => [...prev.filter((m) => !m.loading), { sender: 'ai', text: `Sorry - ${err.message}` }])
    }
  }

  const summary = useMemo(() => {
    const raw = (data?.summary || '').trim()
    if (!raw) return null
    const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean)
    return {
      verdict: lines.find((l) => !l.startsWith('- ') && !l.startsWith('• ') && !/^recommendation:/i.test(l)),
      points: lines.filter((l) => l.startsWith('- ') || l.startsWith('• ')),
      recommendation: lines.find((l) => /^recommendation:/i.test(l)),
    }
  }, [data?.summary])

  // ---------------------------------------------------------------- running
  if (loading || error) {
    return (
      <div className="console">
        <aside className="console__rail">
          <div className="console__rail-head">
            <button className="btn btn--ghost btn--sm" onClick={onExit}>
              <ArrowLeft size={13} strokeWidth={2} aria-hidden="true" />
              Repositories
            </button>
          </div>
          <div className="console__rail-section">
            <span className="legend">target</span>
            <p className="mono" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg)', marginTop: 4, wordBreak: 'break-all' }}>
              {repoFullName}#{prNumber}
            </p>
          </div>
        </aside>

        <div className="console__main">
          <header className="console__head">
            <div className="crumbs">
              <span>{repoFullName}</span>
              <span className="crumbs__sep">/</span>
              <strong>#{prNumber}</strong>
            </div>
            <div className="console__head-actions">
              <Tag tone={error ? 'fail' : 'warn'}>{error ? 'stopped' : 'running'}</Tag>
            </div>
          </header>

          <div className="console__body">
            {error ? (
              <Banner
                tone="fail"
                actions={
                  <>
                    <button className="btn btn--sm btn--primary" onClick={() => setAttempt((n) => n + 1)}>
                      Try again
                    </button>
                    <button className="btn btn--sm" onClick={onExit}>Back</button>
                  </>
                }
              >
                <strong style={{ display: 'block', marginBottom: 2 }}>The review did not finish</strong>
                {error}
              </Banner>
            ) : (
              <div className="progress" role="status" aria-live="polite">
                <div>
                  <div className="cluster" style={{ justifyContent: 'space-between', marginBottom: 'var(--sp-2)' }}>
                    <span className="legend">
                      {prTitle ? prTitle.slice(0, 64) : 'six reviewers reading in parallel'}
                    </span>
                    <span className="legend">
                      {done} / {STAGES.length}
                    </span>
                  </div>
                  <div
                    className="meter"
                    role="progressbar"
                    aria-valuenow={done}
                    aria-valuemin={0}
                    aria-valuemax={STAGES.length}
                    aria-label="Review progress"
                  >
                    <div className="meter__fill" style={{ width: `${(done / STAGES.length) * 100}%` }} />
                  </div>
                </div>

                {coverageNotice && (
                  <Banner tone="warn">
                    Large pull request: about {coverageNotice.reviewed_percent}% of the diff fits in
                    this review. {coverageNotice.files_not_reviewed?.length || 0} file(s) will not be
                    read.
                  </Banner>
                )}

                <div className="stages">
                  {STAGES.map((stage) => {
                    const status = stages[stage.id] || 'pending'
                    const meta = statusMeta(status)
                    return (
                      <m.div
                        key={stage.id}
                        className={`stage stage--${status}`}
                        {...(status === 'done' || status === 'failed' ? popIn : {})}
                      >
                        <span className="stage__icon">
                          <StatusIcon status={status} size={14} />
                        </span>
                        <span className="stage__name">{stage.label}</span>
                        <span className="stage__state">{meta.label}</span>
                      </m.div>
                    )
                  })}
                </div>

                <div className="cluster">
                  <button className="btn btn--sm" onClick={onExit}>Stop watching</button>
                  <span className="legend">
                    the review keeps running and is saved when it finishes
                  </span>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ----------------------------------------------------------------- report
  const { label: verdictLabel } = verdictMeta(readiness.verdict)

  return (
    <div className="console">
      <aside className="console__rail">
        <div className="console__rail-head">
          <button className="btn btn--ghost btn--sm" onClick={onExit}>
            <ArrowLeft size={13} strokeWidth={2} aria-hidden="true" />
            Repositories
          </button>
        </div>

        <div className="console__rail-section">
          <span className="legend">verdict</span>
          <p style={{ fontSize: 'var(--text-sm)', color: 'var(--fg)', marginTop: 4 }}>
            {verdictLabel}
          </p>
        </div>

        <div className="console__rail-section">
          <span className="legend">severity</span>
          <div style={{ marginTop: 6, display: 'flex', flexDirection: 'column', gap: 4 }}>
            {[
              ['CRITICAL', 'critical'],
              ['HIGH', 'high'],
              ['MEDIUM', 'medium'],
              ['LOW', 'low'],
            ].map(([key, tone]) => (
              <div key={key} className="cluster" style={{ justifyContent: 'space-between' }}>
                <SeverityTag severity={key} />
                <span className="mono" style={{ fontSize: 'var(--text-xs)', color: 'var(--fg)' }}>
                  {severity[key] ?? 0}
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="console__rail-foot">
          {repoFullName}#{prNumber}
          <br />
          {data?.head_sha && <>sha {data.head_sha.slice(0, 7)}<br /></>}
          {data?.cached ? 'saved result' : 'fresh run'}
        </div>
      </aside>

      <div className="console__main">
        <header className="console__head">
          <div className="crumbs">
            <span>{repoFullName}</span>
            <span className="crumbs__sep">/</span>
            <strong>#{prNumber}</strong>
          </div>

          <div className="console__head-actions">
            {!data?.posted_to_github ? (
              <button
                className="btn btn--sm"
                disabled={publish.busy}
                onClick={() => publishToGitHub(data.review_id)}
              >
                <GithubMark size={12} />
                {publish.busy ? 'Posting' : 'Post to GitHub'}
              </button>
            ) : (
              <Tag tone="pass">posted</Tag>
            )}
            <button className="btn btn--sm" onClick={() => copy(data?.summary, 'summary')}>
              {copied === 'summary' ? <Check size={12} strokeWidth={2.5} /> : <Copy size={12} strokeWidth={2} />}
              {copied === 'summary' ? 'Copied' : copied === 'summary:failed' ? 'Copy failed' : 'Copy'}
            </button>
            <button className="btn btn--sm btn--ghost" onClick={onExit} aria-label="Close report">
              <X size={14} strokeWidth={2} aria-hidden="true" />
            </button>
          </div>
        </header>

        <div className="console__body">
          <MergeGate
            readiness={readiness}
            coverage={data?.coverage}
            agentErrors={data?.agent_errors}
          />

          <div className="readout-strip">
            <Readout label="score" value={stats?.score ?? '-'} hint={stats?.score_label} />
            <Readout
              label="findings"
              value={stats?.total_issues ?? 0}
              tone={stats?.blocking_issues ? 'fail' : undefined}
              hint={`${stats?.blocking_issues ?? 0} blocking`}
            />
            <Readout label="files" value={stats?.files_affected ?? 0} hint="with findings" />
            <Readout
              label="diff read"
              value={`${data?.coverage?.reviewed_percent ?? 100}%`}
              tone={data?.coverage?.truncated ? 'warn' : undefined}
            />
          </div>

          {publish.error && <Banner tone="fail">Could not post to GitHub: {publish.error}</Banner>}
          {data?.github_error && <Banner tone="fail">Could not post to GitHub: {data.github_error}</Banner>}

          <div className="segment" role="tablist" aria-label="Report sections">
            {TABS.map((item) => (
              <button
                key={item.id}
                role="tab"
                aria-selected={tab === item.id}
                aria-pressed={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}
                {item.id === 'findings' && stats?.total_issues ? ` (${stats.total_issues})` : ''}
              </button>
            ))}
          </div>

          <AnimatePresence mode="wait">
            <m.div key={tab} {...fade}>
              {tab === 'findings' && (
                <div className="stack">
                  {files.length === 0 ? (
                    <Empty icon={FileCode2}>
                      No findings in the reviewed files. That is not an approval - see the gate above.
                    </Empty>
                  ) : (
                    <>
                      <div className="files" role="tablist" aria-label="Files with findings">
                        {files.map((file, index) => (
                          <button
                            key={file.path}
                            role="tab"
                            aria-selected={index === fileIndex}
                            className="file-tab"
                            onClick={() => setFileIndex(index)}
                            title={file.path}
                          >
                            {file.path.split('/').pop()}
                            <span className="file-tab__count">{file.issue_count}</span>
                          </button>
                        ))}
                      </div>

                      {activeFile && (
                        <div className="stack">
                          <p className="legend mono" style={{ wordBreak: 'break-all' }}>
                            {activeFile.path}
                          </p>
                          {activeFile.issues.map((issue, index) => {
                            const level = String(issue.severity || '').toLowerCase()
                            return (
                              <article key={index} className={`finding finding--${level}`}>
                                <header className="finding__head">
                                  <SeverityTag severity={issue.severity} />
                                  <Tag>{issue.category}</Tag>
                                  {issue.agreement > 1 && (
                                    <Tag>{issue.agreement} agents agreed</Tag>
                                  )}
                                  {issue.line ? (
                                    <span className="finding__loc">line {issue.line}</span>
                                  ) : null}
                                </header>

                                <div className="finding__block">
                                  <h4>Problem</h4>
                                  <p className="finding__text">{issue.problem}</p>
                                </div>

                                {issue.code_snippet && (
                                  <div className="finding__block">
                                    <h4>Current</h4>
                                    <div className="code-well code-well--del">
                                      <pre>{issue.code_snippet}</pre>
                                    </div>
                                  </div>
                                )}

                                {issue.recommendation && (
                                  <div className="finding__block">
                                    <h4>Recommendation</h4>
                                    {/* Prose renders as prose. The old check was
                                        `A || B || (C && D)` by precedence, so any
                                        recommendation over 50 characters with a
                                        space rendered as a code block. */}
                                    <div className="finding__text">
                                      {formatMessageText(issue.recommendation)}
                                    </div>
                                  </div>
                                )}

                                {issue.suggestion_snippet && (
                                  <div className="finding__block">
                                    <h4>Suggested fix</h4>
                                    <div className="code-well code-well--add">
                                      <pre>{issue.suggestion_snippet}</pre>
                                    </div>
                                  </div>
                                )}

                                {issue.suggestion_snippet && (
                                  <div className="finding__actions">
                                    <button
                                      className="btn btn--sm"
                                      onClick={() => copy(issue.suggestion_snippet, `fix-${index}`)}
                                    >
                                      {copied === `fix-${index}` ? (
                                        <Check size={12} strokeWidth={2.5} aria-hidden="true" />
                                      ) : (
                                        <Copy size={12} strokeWidth={2} aria-hidden="true" />
                                      )}
                                      {copied === `fix-${index}`
                                        ? 'Copied'
                                        : copied === `fix-${index}:failed`
                                        ? 'Copy failed'
                                        : 'Copy fix'}
                                    </button>
                                  </div>
                                )}
                              </article>
                            )
                          })}
                        </div>
                      )}
                    </>
                  )}
                </div>
              )}

              {tab === 'summary' && (
                <div className="panel">
                  <div className="panel__body">
                    {!summary ? (
                      <Empty>No summary was produced.</Empty>
                    ) : (
                      <>
                        {summary.verdict && <p className="summary__verdict">{summary.verdict}</p>}
                        {summary.points.length > 0 && (
                          <ul className="summary__points">
                            {summary.points.map((point, i) => (
                              <li key={i}>{point.replace(/^[-•]\s*/, '')}</li>
                            ))}
                          </ul>
                        )}
                        {summary.recommendation && (
                          <div className="summary__rec">
                            <ArrowRight size={14} strokeWidth={2} aria-hidden="true" />
                            <span>{summary.recommendation.replace(/^recommendation:\s*/i, '')}</span>
                          </div>
                        )}
                      </>
                    )}
                  </div>
                </div>
              )}

              {tab === 'trace' && <TracePanel reviewId={data?.review_id} />}

              {tab === 'ask' && (
                <div className="panel">
                  <div className="panel__head">
                    <div className="cluster">
                      <Sparkles size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--accent)' }} />
                      <h3 style={{ fontSize: 'var(--text-sm)' }}>Ask about this review</h3>
                    </div>
                  </div>
                  <div className="panel__body chat">
                    <div className="chat__log" ref={chatRef} role="log" aria-live="polite">
                      {chat.map((message, index) => (
                        <div
                          key={index}
                          className={`chat__msg chat__msg--${message.sender}${
                            message.loading ? ' chat__msg--loading' : ''
                          }`}
                        >
                          {formatMessageText(message.text)}
                        </div>
                      ))}
                    </div>

                    <form className="chat__form" onSubmit={ask}>
                      <label htmlFor="ask" className="u-hidden">
                        Ask a question about this review
                      </label>
                      <textarea
                        id="ask"
                        className="input"
                        rows={2}
                        placeholder="Why does this finding matter?"
                        value={question}
                        onChange={(e) => setQuestion(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter' && !e.shiftKey) {
                            e.preventDefault()
                            ask(e)
                          }
                        }}
                      />
                      <button className="btn btn--primary" type="submit" aria-label="Send question">
                        <Send size={13} strokeWidth={2} aria-hidden="true" />
                      </button>
                    </form>
                  </div>
                </div>
              )}
            </m.div>
          </AnimatePresence>

          {data?.created_at && (
            <p className="legend">
              reviewed {new Date(data.created_at).toLocaleString()}
              {data.cached ? ' · served from the saved result' : ''}
              {data.stats ? ` · ${formatDuration(data.duration_ms)}` : ''}
              {data.cost_usd != null ? ` · ${formatCost(data.cost_usd)}` : ''}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
