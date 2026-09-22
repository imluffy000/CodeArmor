import React from 'react'
import { AlertTriangle, XCircle } from 'lucide-react'
import { StatusIcon, statusMeta, verdictMeta } from './primitives'

// The verdict panel: the answer to "can this merge?", with a row per gate so
// a blocked pull request says *why* instead of showing an opaque colour.

const GATE_LABELS = {
  conflicts: 'conflicts',
  ci: 'ci checks',
  base_drift: 'base drift',
  schema: 'db schema',
  contracts: 'api contracts',
  dependencies: 'dependencies',
  config: 'configuration',
  findings: 'findings',
  coverage: 'diff coverage',
  pipeline: 'reviewers',
}

// Worst first, so scanning the grid top-left finds the problem.
const GATE_ORDER = [
  'conflicts', 'ci', 'schema', 'contracts', 'dependencies',
  'base_drift', 'config', 'findings', 'coverage', 'pipeline',
]

export default function MergeGate({ readiness, coverage, agentErrors }) {
  if (!readiness?.verdict) return null

  const { Icon, label } = verdictMeta(readiness.verdict)
  const gates = readiness.gates || {}
  const blockers = readiness.blockers || []
  const warnings = readiness.warnings || []

  const present = GATE_ORDER.filter((key) => gates[key])
  const failing = present.filter((key) => gates[key].status === 'fail').length

  return (
    <section className={`verdict verdict--${readiness.verdict}`} aria-labelledby="verdict-title">
      <div className="verdict__head">
        <Icon size={18} strokeWidth={2} className="verdict__icon" aria-hidden="true" />
        <div style={{ minWidth: 0 }}>
          <h2 id="verdict-title" className="verdict__title">{label}</h2>
          <p className="verdict__sub">{readiness.headline}</p>
        </div>
        <div className="cluster" style={{ marginLeft: 'auto', flexShrink: 0 }}>
          <span className="legend">
            {failing > 0
              ? `${failing} of ${present.length} gates failing`
              : `${present.length} gates checked`}
          </span>
        </div>
      </div>

      {(blockers.length > 0 || warnings.length > 0) && (
        <div className="verdict__lists">
          {blockers.length > 0 && (
            <div className="verdict__list verdict__list--blockers">
              <h4>Blocking before merge</h4>
              <ul>
                {blockers.map((item, i) => (
                  <li key={i}>
                    <XCircle size={13} strokeWidth={2} aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {warnings.length > 0 && (
            <div className="verdict__list verdict__list--warnings">
              <h4>Worth checking</h4>
              <ul>
                {warnings.map((item, i) => (
                  <li key={i}>
                    <AlertTriangle size={13} strokeWidth={2} aria-hidden="true" />
                    <span>{item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="gates">
        {present.map((key) => {
          const gate = gates[key]
          const meta = statusMeta(gate.status)
          return (
            <div key={key} className={`gate gate--${gate.status}`}>
              <span className="gate__icon">
                <StatusIcon status={gate.status} size={14} />
              </span>
              <span className="gate__name">
                {GATE_LABELS[key] || key}
                {/* The status word, so the icon and colour are not the only
                    channels carrying it. */}
                <span className="u-hidden">: {meta.label}</span>
              </span>
              <span className="gate__detail">{gate.detail}</span>
            </div>
          )
        })}
      </div>

      {/* An incomplete review must never be mistaken for a clean one. */}
      {(coverage?.truncated || agentErrors?.length > 0) && (
        <div style={{ padding: 'var(--sp-3) var(--sp-4)', borderTop: '1px solid var(--line)' }}>
          <p className="gate__detail">
            {coverage?.truncated && (
              <>
                About {coverage.reviewed_percent}% of the diff was reviewed
                {coverage.files_not_reviewed?.length > 0 &&
                  ` (${coverage.files_not_reviewed.length} file${
                    coverage.files_not_reviewed.length === 1 ? '' : 's'
                  } not read)`}
                .{' '}
              </>
            )}
            {agentErrors?.length > 0 && (
              <>
                These reviewers did not complete:{' '}
                <span className="mono">
                  {[...new Set(agentErrors.map((e) => e.agent))].join(', ')}
                </span>
                .{' '}
              </>
            )}
            Treat the absence of a finding in those areas as unknown, not safe.
          </p>
        </div>
      )}
    </section>
  )
}
