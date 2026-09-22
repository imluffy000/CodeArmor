import React, { useEffect, useState } from 'react'
import Header from './components/Header'
import RepoConnect from './components/RepoConnect'
import RepoList from './components/RepoList'
import ReviewDashboard from './components/ReviewDashboard'
import ReviewHistory from './components/ReviewHistory'
import { useAuth } from './context/AuthContext'

const AUTH_ERRORS = {
  state: 'That sign-in attempt expired or did not match. Please try again.',
  1: 'GitHub sign-in failed. Please try again.',
}

export default function App() {
  const { user, loading, error, login } = useAuth()
  const [repoRefreshKey, setRepoRefreshKey] = useState(0)
  const [activeReview, setActiveReview] = useState(null)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const authError = params.get('auth_error')
    if (authError) {
      setNotice(AUTH_ERRORS[authError] || AUTH_ERRORS['1'])
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  if (activeReview) {
    return <ReviewDashboard review={activeReview} onReset={() => setActiveReview(null)} />
  }

  return (
    <div className="app-root">
      <Header />
      <main className="page-shell">
        {notice && (
          <div className="error-banner" role="alert">
            {notice}{' '}
            <button className="btn secondary btn-small" onClick={() => setNotice(null)}>
              Dismiss
            </button>
          </div>
        )}
        {error && (
          <div className="error-banner" role="alert">
            Cannot reach the CodeArmor API: {error}
          </div>
        )}

        <section className="hero-section">
          <div className="hero-copy">
            <div className="hero-badge">Multi-agent review engine</div>
            <h1 className="hero-title">
              Review every PR <br /> Help you <span className="font-calligraphy">ship</span>{' '}
              <span className="font-editorial-italic">safer</span> <br /> code{' '}
              <span className="font-editorial-italic">faster</span>
            </h1>
            <p className="hero-text">
              Six specialist agents read your pull request in parallel — security, quality,
              performance, testing, architecture and integration — then a deterministic gate tells
              you what has to be fixed before it merges.
            </p>
            <div className="hero-actions">
              <button
                className="btn primary"
                onClick={() =>
                  document.getElementById('connect-repos')?.scrollIntoView({ behavior: 'smooth' })
                }
              >
                {user ? 'Connect a repository' : 'Get started'}
              </button>
            </div>
          </div>

          <div className="hero-visual">
            <div className="hero-visual-header">
              <div className="window-dots"><span /><span /><span /></div>
              <div className="hero-score">Score: 92</div>
            </div>
            <div className="code-panel">
              <div className="code-line muted">12  | async function handleLogin(req) {'{'}</div>
              <div className="code-line removed">- 13  |   const user = await db.find(req.body.email);</div>
              <div className="code-line added">+ 13  |   const user = await db.users.findUnique({'{'}</div>
              <div className="code-line added">+ 14  |     where: {'{'} email: sanitize(req.body.email) {'}'}</div>
              <div className="code-line added">+ 15  |   {'}'});</div>
              <div className="analysis-card">
                <div className="analysis-pill">Security agent</div>
                <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: 1.5 }}>
                  Line 13 builds the lookup from unsanitised input. Use a parameterised query.
                </p>
              </div>
              <div className="code-line muted">16  |   if (!user) return unauthorized();</div>
            </div>
          </div>
        </section>

        <section className="review-section" id="connect-repos">
          {loading ? (
            <div className="review-panel"><p className="muted-text">Checking your session…</p></div>
          ) : user ? (
            <div className="review-panel">
              <div className="review-panel-header">
                <div>
                  <p className="eyebrow">Repositories</p>
                  <h2>Connect a repository</h2>
                </div>
              </div>
              <RepoConnect onConnected={() => setRepoRefreshKey((k) => k + 1)} />
              <h3 className="repo-section-subtitle">Connected repositories</h3>
              <RepoList refreshKey={repoRefreshKey} onReviewStart={setActiveReview} />

              <h3 className="repo-section-subtitle">Recent reviews</h3>
              <ReviewHistory onOpen={setActiveReview} refreshKey={repoRefreshKey} />
            </div>
          ) : (
            <div className="repo-login-col">
              <div className="repo-login-card">
                <div className="login-card-header">
                  <div className="github-icon-wrapper">
                    <svg className="github-icon" viewBox="0 0 24 24" width="40" height="40" aria-hidden="true">
                      <path fill="currentColor" d="M12 2A10 10 0 0 0 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z" />
                    </svg>
                  </div>
                  <h3>Sign in with GitHub</h3>
                  <p className="card-subtitle">
                    CodeArmor reads the pull requests you choose and never stores your code.
                  </p>
                </div>
                <div className="login-card-features">
                  <div className="login-feature-item"><span className="bullet" aria-hidden="true">✓</span><span>Pick which repositories it can see</span></div>
                  <div className="login-feature-item"><span className="bullet" aria-hidden="true">✓</span><span>Nothing is posted to GitHub unless you ask</span></div>
                  <div className="login-feature-item"><span className="bullet" aria-hidden="true">✓</span><span>Revoke access from your account menu at any time</span></div>
                </div>
                <button className="btn primary login-btn" onClick={login}>Sign in with GitHub</button>
                <p className="card-footnote">
                  Your pull request diffs are sent to an AI model provider for analysis. See the
                  README for what leaves the system and what is stored.
                </p>
              </div>
            </div>
          )}
        </section>

        {!user && (
          <section className="features-grid" id="features">
            <div className="feature-card">
              <h3>Security</h3>
              <p>Injection, authorization gaps, leaked secrets and unsafe deserialization.</p>
            </div>
            <div className="feature-card">
              <h3>Efficiency &amp; performance</h3>
              <p>N+1 queries, blocking I/O on async paths and unbounded memory use.</p>
            </div>
            <div className="feature-card">
              <h3>Integration</h3>
              <p>Breaking API changes, unsafe migrations, dependency drift and CI state.</p>
            </div>
            <div className="feature-card">
              <h3>Merge gate</h3>
              <p>A deterministic verdict on what must be fixed before this can merge.</p>
            </div>
          </section>
        )}
      </main>

      <footer className="footer">© {new Date().getFullYear()} CodeArmor</footer>
    </div>
  )
}
