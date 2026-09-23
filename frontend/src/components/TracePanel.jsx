import React, { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { api } from '../api'
import {
  Banner,
  Empty,
  Readout,
  Skeleton,
  StatusIcon,
  formatCost,
  formatDuration,
  formatTokens,
} from './primitives'

// Holds the shape of the readout strip and the seven agent rows, so the tab
// does not resize under the reader when the trace lands.
function TraceSkeleton() {
  return (
    <div className="stack" role="status" aria-busy="true">
      <div className="readout-strip">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="readout">
            <Skeleton width={46} height={20} />
            <Skeleton width={38} height={8} style={{ marginTop: 6 }} />
          </div>
        ))}
      </div>
      <div className="skeleton-table">
        {Array.from({ length: 7 }, (_, i) => (
          <div key={i} className="skeleton-table__row">
            <Skeleton width="20%" />
            <Skeleton width="12%" />
            {/* The latency column is a bar chart, so its placeholder
                varies in width the way the real bars will. */}
            <Skeleton width={`${28 + ((i * 17) % 48)}%`} />
            <Skeleton width="10%" />
          </div>
        ))}
      </div>
      <span className="u-hidden">Loading the trace</span>
    </div>
  )
}

// The trace: what each agent cost, how long it took, and how its output
// parsed. This is what makes "the security agent missed this" answerable
// afterwards rather than a shrug.
export default function TracePanel({ reviewId }) {
  const [trace, setTrace] = useState(null)
  const [error, setError] = useState(null)
  // Reviews saved before tracing existed have no trace row, and the ops
  // endpoint is user-scoped, so both answer 404. Neither is a fault.
  const [missing, setMissing] = useState(false)

  useEffect(() => {
    if (!reviewId) return undefined
    let cancelled = false
    setError(null)
    setMissing(false)
    api(`/ops/reviews/${reviewId}/trace`)
      .then((data) => { if (!cancelled) setTrace(data) })
      .catch((err) => {
        if (cancelled) return
        if (err.isNotFound) setMissing(true)
        else setError(err.message)
      })
    return () => { cancelled = true }
  }, [reviewId])

  if (missing) {
    return (
      <Empty icon={Activity}>
        No trace was recorded for this review.
      </Empty>
    )
  }
  if (error) return <Banner tone="warn">Could not load the trace: {error}</Banner>
  if (!trace) return <TraceSkeleton />

  const agents = trace.agents || []
  const slowest = Math.max(1, ...agents.map((a) => a.duration_ms || 0))
  const dropped = agents.reduce((sum, a) => sum + (a.dropped || 0), 0)

  return (
    <div className="stack">
      <div className="readout-strip">
        <Readout label="wall clock" value={formatDuration(trace.duration_ms)} />
        <Readout label="cost" value={formatCost(trace.cost_usd)} />
        <Readout
          label="tokens"
          value={`${formatTokens(trace.tokens_in)} / ${formatTokens(trace.tokens_out)}`}
          hint="in / out"
        />
        <Readout
          label="dropped"
          value={dropped}
          tone={dropped > 0 ? 'warn' : undefined}
          hint="failed validation"
        />
      </div>

      <div className="trace-wrap">
        <table className="trace">
          <caption className="u-hidden">
            Per-agent latency, token use and cost for this review
          </caption>
          <thead>
            <tr>
              <th scope="col">Agent</th>
              <th scope="col">Status</th>
              <th scope="col" className="trace__bar">Latency</th>
              <th scope="col" className="num">Tokens</th>
              <th scope="col" className="num">Cost</th>
              <th scope="col" className="num">Found</th>
              <th scope="col" className="num">Dropped</th>
            </tr>
          </thead>
          <tbody>
            {agents.map((agent) => {
              const width = Math.round(((agent.duration_ms || 0) / slowest) * 72)
              const failed = agent.status !== 'ok'
              return (
                <tr key={agent.agent}>
                  <td className="agent">{agent.agent}</td>
                  <td>
                    <span className="cluster" style={{ gap: 5 }}>
                      <StatusIcon status={agent.status} size={12} />
                      {agent.status}
                    </span>
                  </td>
                  {/* A bar drawn in the cell, so scanning the column shows the
                      shape of the run without pulling in a chart library. */}
                  <td className={`trace__bar${failed ? ' trace__bar--fail' : ''}`}>
                    <span style={{ width: `${width}px` }} aria-hidden="true" />
                    <span
                      style={{
                        position: 'relative',
                        left: 80,
                        color: 'var(--fg-muted)',
                      }}
                    >
                      {formatDuration(agent.duration_ms)}
                    </span>
                  </td>
                  <td className="num">
                    {formatTokens(agent.tokens_in)} / {formatTokens(agent.tokens_out)}
                  </td>
                  <td className="num">{formatCost(agent.cost_usd)}</td>
                  <td className="num">{agent.findings ?? 0}</td>
                  <td
                    className="num"
                    style={agent.dropped ? { color: 'var(--signal-warn)' } : undefined}
                  >
                    {agent.dropped ?? 0}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {agents.some((a) => a.error) && (
        <Banner tone="warn">
          {agents
            .filter((a) => a.error)
            .map((a) => `${a.agent}: ${a.error}`)
            .join(' · ')}
        </Banner>
      )}

      <p className="legend" style={{ lineHeight: 'var(--leading-normal)' }}>
        <Activity size={11} strokeWidth={2} aria-hidden="true" style={{ display: 'inline', verticalAlign: '-1px' }} />
        {'  '}
        trace {trace.trace_id} · model {trace.model} · prompts {trace.prompt_version}
      </p>
    </div>
  )
}
