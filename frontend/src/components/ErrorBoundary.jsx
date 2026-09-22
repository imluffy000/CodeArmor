import React from 'react'

// Without this, a render error in the dashboard unmounts the whole app to a
// blank page, and a finished review that cost real money goes with it.
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
      <div className="app-root" role="alert" style={{ padding: '48px 24px', maxWidth: 640, margin: '0 auto' }}>
        <h1 style={{ fontSize: '1.5rem', marginBottom: 12 }}>Something broke on this page</h1>
        <p className="muted-text" style={{ marginBottom: 20 }}>
          Your reviews are saved on the server, so nothing is lost. Reload to get back to them.
        </p>
        <pre
          style={{
            background: 'rgba(0,0,0,0.2)',
            padding: 12,
            borderRadius: 8,
            fontSize: '0.8rem',
            overflowX: 'auto',
            marginBottom: 20,
          }}
        >
          {String(this.state.error?.message || this.state.error)}
        </pre>
        <button className="btn primary" onClick={() => window.location.reload()}>
          Reload
        </button>
      </div>
    )
  }
}
