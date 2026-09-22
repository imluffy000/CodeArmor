import React from 'react'

// The "before merging" panel: one row per gate, so a blocked pull request says
// *why* rather than showing an opaque colour. The previous dashboard rendered a
// hardcoded green "Review Complete" chip regardless of what happened.

const VERDICT = {
  blocked: { label: 'Not ready to merge', cls: 'gate-blocked' },
  caution: { label: 'Merge with care', cls: 'gate-caution' },
  clear: { label: 'Nothing blocking found', cls: 'gate-clear' },
}

const GATE_LABELS = {
  conflicts: 'Merge conflicts',
  ci: 'CI checks',
  base_drift: 'Base branch drift',
  schema: 'Database schema',
  contracts: 'API contracts',
  dependencies: 'Dependencies',
  config: 'Configuration',
  findings: 'Review findings',
  coverage: 'Diff coverage',
  pipeline: 'Reviewer health',
}

const STATUS_ICON = { pass: '✓', warn: '!', fail: '✕', unknown: '?' }

export default function MergeGate({ readiness, coverage, agentErrors }) {
  if (!readiness || !readiness.verdict) return null

  const verdict = VERDICT[readiness.verdict] || VERDICT.clear
  const gates = readiness.gates || {}

  return (
    <section className={`merge-gate ${verdict.cls}`} aria-labelledby="merge-gate-heading">
      <header className="merge-gate-header">
        <h3 id="merge-gate-heading">{verdict.label}</h3>
        <p className="muted-text">{readiness.headline}</p>
      </header>

      {readiness.blockers?.length > 0 && (
        <div className="merge-gate-list merge-gate-blockers">
          <h4>Blocking before merge</h4>
          <ul>
            {readiness.blockers.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}

      {readiness.warnings?.length > 0 && (
        <div className="merge-gate-list merge-gate-warnings">
          <h4>Worth checking</h4>
          <ul>
            {readiness.warnings.map((item, i) => <li key={i}>{item}</li>)}
          </ul>
        </div>
      )}

      <div className="merge-gate-grid">
        {Object.entries(GATE_LABELS).map(([key, label]) => {
          const gate = gates[key]
          if (!gate) return null
          return (
            <div key={key} className={`merge-gate-item gate-${gate.status}`}>
              <span className="merge-gate-icon" aria-hidden="true">{STATUS_ICON[gate.status]}</span>
              <span className="merge-gate-name">{label}</span>
              <span className="merge-gate-detail">{gate.detail}</span>
            </div>
          )
        })}
      </div>

      {/* An incomplete review must never be mistaken for a clean one. */}
      {(coverage?.truncated || agentErrors?.length > 0) && (
        <p className="merge-gate-caveat">
          {coverage?.truncated && (
            <>About {coverage.reviewed_percent}% of the diff was reviewed
              {coverage.files_not_reviewed?.length > 0 &&
                ` (${coverage.files_not_reviewed.length} file(s) not read)`}. </>
          )}
          {agentErrors?.length > 0 && (
            <>These reviewers did not complete:{' '}
              {[...new Set(agentErrors.map((e) => e.agent))].join(', ')}. </>
          )}
          Treat absence of a finding in those areas as unknown, not safe.
        </p>
      )}
    </section>
  )
}
