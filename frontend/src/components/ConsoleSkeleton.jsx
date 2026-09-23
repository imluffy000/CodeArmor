import React from 'react'
import { Skeleton } from './primitives'

// The console is a lazy-loaded 111 kB chunk, so on a cold cache there is a
// real gap between pressing Review and the console existing. A one-line
// "Opening..." message replaced the entire screen with a sentence and then
// snapped the full layout in; this holds the console geometry - rail, header,
// gate, readouts, body - so only the content arrives, not the layout.
export default function ConsoleSkeleton({ label = 'Opening the review console' }) {
  return (
    <div className="console" role="status" aria-busy="true">
      <aside className="console__rail">
        <div className="console__rail-head">
          <Skeleton width={104} height={22} radius="var(--radius)" />
        </div>
        {[0, 1, 2].map((i) => (
          <div key={i} className="console__rail-section">
            <Skeleton width={52} height={8} />
            <div className="skeleton-stack">
              <Skeleton width="78%" />
              <Skeleton width="54%" />
            </div>
          </div>
        ))}
      </aside>

      <div className="console__main">
        <header className="console__head">
          <Skeleton width={190} height={12} />
        </header>

        <div className="console__body">
          <Skeleton width="100%" height={96} radius="var(--radius)" />

          <div className="readout-strip">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="readout">
                <Skeleton width={42} height={20} />
                <Skeleton width={36} height={8} style={{ marginTop: 6 }} />
              </div>
            ))}
          </div>

          <Skeleton width="100%" height={188} radius="var(--radius)" />
        </div>
      </div>

      <span className="u-hidden">{label}</span>
    </div>
  )
}
