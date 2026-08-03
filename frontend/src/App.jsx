import React, { useEffect, useState } from 'react'
import Header from './components/Header'
import ReviewForm from './components/ReviewForm'
import RepoConnect from './components/RepoConnect'
import RepoList from './components/RepoList'
import ReviewDashboard from './components/ReviewDashboard'
import { useAuth } from './context/AuthContext'

export default function App() {
  const { user, loading, login } = useAuth()
  const [repoRefreshKey, setRepoRefreshKey] = useState(0)
  const [activeReview, setActiveReview] = useState(null)

  // Context-level handler to trigger detailed reports
  const handleReviewCompleted = (repoFullName, prNumber, data) => {
    setActiveReview({ repo: repoFullName, prNumber, data })
  }

  const handleReviewStart = (repoFullName, prNumber) => {
    setActiveReview({ repo: repoFullName, prNumber })
  }

  // Define quickReviewFlow inside component to access state setter
  const quickReviewFlow = async () => {
    const pr = window.prompt(
      'Enter full PR URL (https://github.com/owner/repo/pull/123) or owner/repo and PR number separated by a space (owner/repo 123)'
    )
    if (!pr) return

    let pr_url = ''
    let repoName = 'unknown'
    let prNum = 'PR'

    if (/https?:\/\/github\.com\/.+\/pull\/\d+/.test(pr.trim())) {
      pr_url = pr.trim()
      const match = pr_url.match(/github\.com\/([^\/]+\/[^\/]+)\/pull\/(\d+)/)
      if (match) {
        repoName = match[1]
        prNum = match[2]
      }
    } else {
      const parts = pr.trim().split(/\s+/)
      if (parts.length === 2) {
        const repo = parts[0].startsWith('http') ? parts[0].replace(/\/$/, '') : `https://github.com/${parts[0].replace(/\/$/, '')}`
        pr_url = `${repo}/pull/${parts[1]}`
        repoName = parts[0]
        prNum = parts[1]
      } else {
        alert('Unrecognized input format')
        return
      }
    }

    setActiveReview({ repo: repoName, prNumber: prNum })
  }

  useEffect(() => {
    window.quickReviewFlow = quickReviewFlow
    return () => {
      delete window.quickReviewFlow
    }
  }, [])

  useEffect(() => {
    // Surface OAuth failures from the callback redirect (?auth_error=1)
    const params = new URLSearchParams(window.location.search)
    if (params.get('auth_error')) {
      alert('GitHub sign-in failed. Please try again.')
      window.history.replaceState({}, '', window.location.pathname)
    }
  }, [])

  // If a review report is active, render the full-screen dashboard workspace
  if (activeReview) {
    return (
      <ReviewDashboard
        repo={activeReview.repo}
        prNumber={activeReview.prNumber}
        reviewData={activeReview.data}
        onReset={() => setActiveReview(null)}
      />
    )
  }

  return (
    <div className="app-root">
      <Header />
      <main className="page-shell">
        <section className="hero-section">
          <div className="hero-copy">
            <div className="hero-badge">AI-Powered Review Engine</div>
            <h1 className="hero-title">
              Review every PR <br /> Help You <span className="font-calligraphy">ship</span> <span className="font-editorial-italic">safer</span> <br /> code <span className="font-editorial-italic">faster</span>
            </h1>
            <p className="hero-text">
              Analyze pull requests instantly with a polished multi-agent review workflow. Catch bugs, security issues, and architecture drift before code lands.
            </p>
            <div className="hero-actions">
              <button className="btn primary" onClick={() => {
                const element = document.getElementById('connect-repos')
                element?.scrollIntoView({ behavior: 'smooth' })
              }}>
                Connect Repository
              </button>
              <button className="btn secondary" onClick={quickReviewFlow}>
                Quick Review Prompt
              </button>
            </div>
          </div>

          <div className="hero-visual">
            <div className="hero-visual-header">
              <div className="window-dots">
                <span />
                <span />
                <span />
              </div>
              <div className="hero-score">Score: 92%</div>
            </div>
            <div className="code-panel">
              <div className="code-line muted">12  | async function handleLogin(req: Request) {'{'}</div>
              <div className="code-line removed">- 13  |   const user = await db.find(req.body.email);</div>
              <div className="code-line added">+ 13  |   const user = await db.users.findUnique({'{'}</div>
              <div className="code-line added">+ 14  |     where: {'{'} email: sanitize(req.body.email) {'}'}</div>
              <div className="code-line added">+ 15  |   {'}'});</div>
              <div className="analysis-card">
                <div className="analysis-pill">Insight</div>
                <p style={{ margin: 0, fontSize: '0.9rem', lineHeight: 1.5 }}>
                  Detected possible injection risk in line 13. Use input sanitization and parameterized access.
                </p>
              </div>
              <div className="code-line muted">16  |   if (!user) return unauthorized();</div>
            </div>
          </div>
        </section>
        <section className="review-section" id="connect-repos">
          {loading ? (
            <div className="review-panel">
              <p className="muted-text">Checking session…</p>
            </div>
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
              <RepoList refreshKey={repoRefreshKey} onReviewSuccess={handleReviewCompleted} onReviewStart={handleReviewStart} />
            </div>
          ) : (
            <div className="repo-split-container">
              <div className="demo-video-card">
                <h3>Demo video</h3>
                <div className="video-placeholder">
                  <div className="play-button-wrapper">
                    <svg className="play-icon" viewBox="0 0 24 24" fill="currentColor">
                      <path d="M8 5v14l11-7z" />
                    </svg>
                  </div>
                </div>
              </div>
              
              <div className="repo-login-col">
                <div className="repo-login-card">
                  <div className="login-card-header">
                    <div className="github-icon-wrapper">
                      <svg className="github-icon" viewBox="0 0 24 24" width="40" height="40">
                        <path fill="currentColor" d="M12 2A10 10 0 0 0 2 12c0 4.42 2.87 8.17 6.84 9.5.5.08.66-.23.66-.5v-1.69c-2.77.6-3.36-1.34-3.36-1.34-.46-1.16-1.11-1.47-1.11-1.47-.9-.62.07-.6.07-.6 1 .07 1.53 1.03 1.53 1.03.9 1.52 2.34 1.07 2.91.83.09-.65.35-1.09.63-1.34-2.22-.25-4.55-1.11-4.55-4.92 0-1.11.38-2 1.03-2.71-.1-.25-.45-1.29.1-2.64 0 0 .84-.27 2.75 1.02.79-.22 1.65-.33 2.5-.33.85 0 1.71.11 2.5.33 1.91-1.29 2.75-1.02 2.75-1.02.55 1.35.2 2.39.1 2.64.65.71 1.03 1.6 1.03 2.71 0 3.82-2.34 4.66-4.57 4.91.36.31.69.92.69 1.85V21c0 .27.16.59.67.5C19.14 20.16 22 16.42 22 12A10 10 0 0 0 12 2z"/>
                      </svg>
                    </div>
                    <h3>GitHub Integration</h3>
                    <p className="card-subtitle">Connect your workspace securely</p>
                  </div>
                  <div className="login-card-features">
                    <div className="login-feature-item">
                      <span className="bullet">✓</span>
                      <span>Fetch and analyze branches</span>
                    </div>
                    <div className="login-feature-item">
                      <span className="bullet">✓</span>
                      <span>Identify bugs & security gaps</span>
                    </div>
                    <div className="login-feature-item">
                      <span className="bullet">✓</span>
                      <span>Real-time code review suggestions</span>
                    </div>
                  </div>
                  <button className="btn primary login-btn" onClick={login}>Sign in with GitHub</button>
                </div>
              </div>
            </div>
          )}
        </section>
        {!user && (
          <section className="features-grid" id="features">
            <div className="feature-card">
              <h3>Bug Detection</h3>
              <p>Spot edge cases, regressions, and logical gaps before they reach production.</p>
            </div>
            <div className="feature-card">
              <h3>Security Scan</h3>
              <p>Catch injection patterns, leaked secrets, and insecure defaults automatically.</p>
            </div>
            <div className="feature-card">
              <h3>Performance</h3>
              <p>Surface N+1 risks and heavy code paths that can slow down your release.</p>
            </div>
            <div className="feature-card">
              <h3>AI Suggestions</h3>
              <p>Get practical improvement ideas for structure, readability, and maintainability.</p>
            </div>
          </section>
        )}

        <section className="review-section" id="contact">
          <div className="contact-split-container">
            <div className="contact-card">
              <div className="contact-card-header">
                <p className="eyebrow">Contact Us</p>
                <h2>Have questions? Let's connect.</h2>
              </div>
              <form className="contact-form" onSubmit={(e) => { e.preventDefault(); alert('Message sent successfully! We will get back to you shortly.'); e.target.reset(); }}>
                <label>
                  Name
                  <input type="text" placeholder="John Doe" required />
                </label>
                <label>
                  Email Address
                  <input type="email" placeholder="john@example.com" required />
                </label>
                <button className="btn primary contact-submit-btn" type="submit">Send Message</button>
              </form>
            </div>
            <div className="contact-placeholder-card"></div>
          </div>
        </section>
      </main>

      <footer className="footer">© {new Date().getFullYear()} CodeArmor</footer>
    </div>
  )
}
