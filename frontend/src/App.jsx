import React, { Suspense, lazy, useEffect, useState } from 'react'
import {
  Check,
  Gauge,
  GitMerge,
  Layers,
  ShieldAlert,
  Zap,
} from 'lucide-react'
import { GithubMark } from './components/BrandIcons'
import Header from './components/Header'
import RepoConnect from './components/RepoConnect'
import RepoList from './components/RepoList'
import ReviewHistory from './components/ReviewHistory'
import { Banner } from './components/primitives'
import { useAuth } from './context/AuthContext'

// Code-split: the landing page should not ship the review console, its
// motion features or its markdown renderer before anyone has signed in.
const ReviewConsole = lazy(() => import('./components/ReviewConsole'))

const AUTH_ERRORS = {
  state: 'That sign-in attempt expired or did not match. Please try again.',
  1: 'GitHub sign-in failed. Please try again.',
}

const CAPABILITIES = [
  {
    icon: ShieldAlert,
    title: 'Security',
    body: 'Injection, authorization gaps, leaked secrets, unsafe deserialization, weak crypto.',
  },
  {
    icon: Zap,
    title: 'Efficiency',
    body: 'N+1 queries, blocking I/O on async paths, unbounded memory, missing indexes.',
  },
  {
    icon: Layers,
    title: 'Integration',
    body: 'Removed routes, unsafe migrations, dependency drift, undocumented config.',
  },
  {
    icon: GitMerge,
    title: 'Merge gate',
    body: 'Ten deterministic gates, each reporting pass, check or fail with a reason.',
  },
]

// The hero shows the real gate panel in miniature rather than an illustration,
// so the landing page is the product.
const SPECIMEN = [
  ['pass', 'conflicts', 'clean against main'],
  ['fail', 'ci', 'unit-tests, typecheck'],
  ['fail', 'schema', 'drops users.email'],
  ['warn', 'contracts', '2 symbols removed'],
  ['warn', 'coverage', '42% of diff read'],
]

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
    return (
      <Suspense fallback={<p className="muted" style={{ padding: 'var(--sp-6)' }}>Opening the review console...</p>}>
        <ReviewConsole review={activeReview} onExit={() => setActiveReview(null)} />
      </Suspense>
    )
  }

  return (
    <div className="shell">
      <Header />

      <main className="page">
        {notice && (
          <Banner
            tone="warn"
            actions={
              <button className="btn btn--sm" onClick={() => setNotice(null)}>
                Dismiss
              </button>
            }
          >
            {notice}
          </Banner>
        )}
        {error && <Banner tone="fail">Cannot reach the CodeArmor API: {error}</Banner>}

        {!user && !loading && (
          <>
            <section className="hero">
              <div>
                <div className="hero__eyebrow">
                  <span className="dot dot--warn" aria-hidden="true" />
                  <span className="legend">six agents, one verdict</span>
                </div>
                <h1>
                  Know what breaks
                  <br />
                  <em>before</em> you merge.
                </h1>
                <p>
                  Six specialist reviewers read your pull request in parallel. Then a
                  deterministic gate tells you exactly what has to be fixed first - conflicts,
                  failing checks, unsafe migrations, removed routes, dependency drift.
                </p>
                <div className="hero__actions">
                  <button className="btn btn--primary" onClick={login}>
                    <GithubMark size={14} />
                    Sign in with GitHub
                  </button>
                  <a className="btn" href="#what-it-checks">
                    What it checks
                  </a>
                </div>
              </div>

              <div className="specimen" aria-hidden="true">
                <div className="specimen__head">
                  <span className="legend">acme/api #482</span>
                  <span className="tag tag--fail">blocked</span>
                </div>
                {SPECIMEN.map(([status, gate, detail]) => (
                  <div key={gate} className="specimen__row">
                    <span className={`dot dot--${status}`} />
                    <span>{gate}</span>
                    <span>{detail}</span>
                  </div>
                ))}
              </div>
            </section>

            <section id="what-it-checks">
              <div className="section-title">
                <h2>What it checks</h2>
                <span className="legend">and what it will not claim</span>
              </div>
              <div className="capabilities">
                {CAPABILITIES.map(({ icon: Icon, title, body }) => (
                  <div key={title} className="capability">
                    <Icon size={17} strokeWidth={1.75} className="capability__icon" aria-hidden="true" />
                    <h3>{title}</h3>
                    <p>{body}</p>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel signin">
              <div className="panel__head">
                <h2 style={{ fontSize: 'var(--text-base)' }}>Connect GitHub</h2>
                <Gauge size={14} strokeWidth={2} aria-hidden="true" style={{ color: 'var(--fg-dim)' }} />
              </div>
              <div className="panel__body">
                <div className="signin__features">
                  {[
                    'You choose which repositories it can see',
                    'Nothing is posted to GitHub unless you ask',
                    'Revoke access and erase your data from the account menu',
                  ].map((line) => (
                    <div key={line} className="signin__feature">
                      <Check size={13} strokeWidth={2.5} aria-hidden="true" />
                      <span>{line}</span>
                    </div>
                  ))}
                </div>
                <button className="btn btn--primary" onClick={login} style={{ width: '100%' }}>
                  <GithubMark size={14} />
                  Sign in with GitHub
                </button>
                <p className="signin__note">
                  Reviewing a pull request sends its diff to an AI model provider. CodeArmor does
                  not store your code, and never approves a pull request on your behalf. The README
                  states exactly what leaves the system.
                </p>
              </div>
            </section>
          </>
        )}

        {loading && <p className="muted">Checking your session...</p>}

        {user && (
          <>
            <section id="repositories">
              <div className="section-title">
                <h2>Repositories</h2>
                <span className="legend">expand one to review its pull requests</span>
              </div>
              <div className="stack">
                <RepoConnect onConnected={() => setRepoRefreshKey((k) => k + 1)} />
                <RepoList refreshKey={repoRefreshKey} onReviewStart={setActiveReview} />
              </div>
            </section>

            <section id="reviews">
              <div className="section-title">
                <h2>Recent reviews</h2>
                <span className="legend">saved, so closing a report does not lose it</span>
              </div>
              <ReviewHistory onOpen={setActiveReview} refreshKey={repoRefreshKey} />
            </section>
          </>
        )}
      </main>

      <footer className="footer">
        CodeArmor - automated analysis, not an approval
      </footer>
    </div>
  )
}
