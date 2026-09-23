import React from 'react'
import {
  AlertTriangle,
  CheckCircle2,
  CircleDashed,
  HelpCircle,
  Loader2,
  SearchX,
  ShieldCheck,
  XCircle,
} from 'lucide-react'

// Shared vocabulary for status. Every status is rendered as icon + text, never
// as colour alone - a red dot on its own fails for a colourblind reader, and
// the icon is what survives a greyscale print or a screenshot in a ticket.

const STATUS = {
  pass: { Icon: CheckCircle2, label: 'Pass', tone: 'pass' },
  warn: { Icon: AlertTriangle, label: 'Check', tone: 'warn' },
  fail: { Icon: XCircle, label: 'Fail', tone: 'fail' },
  unknown: { Icon: HelpCircle, label: 'Unknown', tone: 'idle' },
  pending: { Icon: CircleDashed, label: 'Queued', tone: 'idle' },
  active: { Icon: Loader2, label: 'Running', tone: 'accent' },
  done: { Icon: CheckCircle2, label: 'Done', tone: 'pass' },
  failed: { Icon: XCircle, label: 'Failed', tone: 'fail' },
  skipped: { Icon: CircleDashed, label: 'Skipped', tone: 'idle' },
  timeout: { Icon: AlertTriangle, label: 'Timed out', tone: 'fail' },
  ok: { Icon: CheckCircle2, label: 'OK', tone: 'pass' },
}

export function statusMeta(status) {
  return STATUS[status] || STATUS.unknown
}

export function StatusIcon({ status, size = 14, className = '' }) {
  const { Icon } = statusMeta(status)
  const spin = status === 'active' ? 'spin' : ''
  return <Icon size={size} strokeWidth={2} className={`${spin} ${className}`.trim()} aria-hidden="true" />
}

const VERDICT = {
  blocked: { Icon: XCircle, label: 'Not ready to merge' },
  caution: { Icon: AlertTriangle, label: 'Merge with care' },
  clear: { Icon: ShieldCheck, label: 'Nothing blocking' },
}

export function verdictMeta(verdict) {
  return VERDICT[verdict] || VERDICT.clear
}

export function Tag({ tone, children }) {
  return <span className={`tag${tone ? ` tag--${tone}` : ''}`}>{children}</span>
}

export function SeverityTag({ severity }) {
  const level = String(severity || '').toUpperCase()
  return <Tag tone={level.toLowerCase()}>{level}</Tag>
}

/** A labelled figure, as on a gauge. */
export function Readout({ label, value, tone, hint }) {
  return (
    <div className="readout">
      <span className={`readout__value${tone ? ` readout__value--${tone}` : ''}`}>{value}</span>
      <span className="legend">{label}</span>
      {hint && <span className="legend" style={{ color: 'var(--fg-dim)' }}>{hint}</span>}
    </div>
  )
}

export function Banner({ tone = 'info', icon, children, actions }) {
  const Icon = icon || (tone === 'fail' ? XCircle : tone === 'warn' ? AlertTriangle : HelpCircle)
  return (
    <div className={`banner banner--${tone}`} role={tone === 'fail' ? 'alert' : 'status'}>
      <Icon size={15} strokeWidth={2} aria-hidden="true" style={{ flexShrink: 0, marginTop: 1 }} />
      <div style={{ minWidth: 0 }}>{children}</div>
      {actions && <div className="banner__actions">{actions}</div>}
    </div>
  )
}

export function Empty({ icon: Icon = CircleDashed, children }) {
  return (
    <div className="empty">
      <Icon size={20} strokeWidth={1.75} aria-hidden="true" />
      <p>{children}</p>
    </div>
  )
}

/* --- waiting --------------------------------------------------------------
   Skeletons rather than a centred spinner for anything that resolves into a
   list of rows. A spinner discards the layout and then snaps it back, so the
   page jumps at the moment the user starts reading; a skeleton holds the
   geometry the real rows will occupy. It also says *what* is coming - "three
   repository rows" - instead of "something is happening somewhere". */

export function Skeleton({ width = '100%', height = 10, radius, style }) {
  return (
    <span
      className="skeleton"
      aria-hidden="true"
      style={{ width, height, borderRadius: radius, ...style }}
    />
  )
}

/**
 * Placeholder rows at the height the real ones will be. `bare` drops the
 * panel border for use inside a container that already draws one, which
 * otherwise reads as a box nested in a box.
 */
export function SkeletonRows({ rows = 3, label = 'Loading', bare = false }) {
  return (
    <div className={bare ? undefined : 'rows'} role="status" aria-busy="true">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton-row">
          <Skeleton width={13} height={13} radius="var(--radius-full)" />
          {/* Staggered widths: rows of identical bars read as a loading
              graphic, varied ones read as text that has not arrived. */}
          <Skeleton width={`${48 - i * 7}%`} />
          <span className="skeleton-row__meta">
            <Skeleton width={36} height={9} />
            <Skeleton width={52} height={9} />
          </span>
        </div>
      ))}
      <span className="u-hidden">{label}</span>
    </div>
  )
}

/** A centred wait with room to explain why it is taking this long. */
export function LoadingPanel({ label = 'Loading', note }) {
  return (
    <div className="loading-panel" role="status">
      <Loader2 size={20} strokeWidth={2} className="spin" aria-hidden="true" />
      <p className="loading-panel__label">{label}</p>
      {note && <p className="loading-panel__note">{note}</p>}
    </div>
  )
}

/* --- not found ------------------------------------------------------------
   A missing resource is not a failure and must not be reported as one - a red
   alert banner for "this review was deleted" trains people to ignore red.

   This screen also never offers a retry. The API answers 404 both for
   something that no longer exists and for something that belongs to another
   account, so there is nothing to retry into, and on a review in particular a
   retry would spend six model calls to fail the same way. */

export function NotFound({ code, title, icon: Icon = SearchX, children, actions }) {
  return (
    <div className="notfound" role="status">
      <Icon size={26} strokeWidth={1.5} aria-hidden="true" />
      {code && <span className="notfound__code mono">{code}</span>}
      <h2>{title}</h2>
      {children && <p>{children}</p>}
      {actions && <div className="cluster notfound__actions">{actions}</div>}
    </div>
  )
}

/** Compact duration: 840ms, 4.2s, 1m 12s. */
export function formatDuration(ms) {
  if (ms == null) return '-'
  if (ms < 1000) return `${ms}ms`
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`
  const minutes = Math.floor(ms / 60000)
  return `${minutes}m ${Math.round((ms % 60000) / 1000)}s`
}

/** Cost small enough to matter: $0.0031, not $0.00. */
export function formatCost(usd) {
  if (usd == null) return '-'
  if (usd === 0) return '$0'
  if (usd < 0.01) return `$${usd.toFixed(4)}`
  return `$${usd.toFixed(2)}`
}

export function formatTokens(count) {
  if (count == null) return '-'
  if (count < 1000) return String(count)
  return `${(count / 1000).toFixed(1)}k`
}

export function formatWhen(iso) {
  if (!iso) return '-'
  const then = new Date(iso)
  const seconds = Math.round((Date.now() - then.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  if (seconds < 604800) return `${Math.floor(seconds / 86400)}d ago`
  return then.toLocaleDateString()
}
