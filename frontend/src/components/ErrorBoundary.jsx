import React from 'react'
import { AlertTriangle } from 'lucide-react'

// Without this, a render error in the console unmounts the whole app to a
// blank page. Reviews are stored server-side, so a reload recovers them - the
// point of this screen is to say so rather than leave a white void.
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    console.error('CodeArmor crashed while rendering:', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="page" role="alert" style={{ maxWidth: 620 }}>
        <div className="panel">
          <div className="panel__head">
            <div className="cluster">
              <AlertTriangle size={15} strokeWidth={2} style={{ color: 'var(--signal-fail)' }} aria-hidden="true" />
              <h2 style={{ fontSize: 'var(--text-base)' }}>This page stopped rendering</h2>
            </div>
          </div>
          <div className="panel__body stack">
            <p className="muted">
              Your reviews are stored on the server, so nothing is lost. Reloading returns you
              to them.
            </p>
            <div className="code-well">
              <pre>{String(this.state.error?.message || this.state.error)}</pre>
            </div>
            <div className="cluster">
              <button className="btn btn--primary" onClick={() => window.location.reload()}>
                Reload
              </button>
            </div>
          </div>
        </div>
      </div>
    )
  }
}
