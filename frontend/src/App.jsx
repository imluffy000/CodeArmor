import React, { Suspense, lazy, useCallback, useEffect, useState } from 'react'
import ConsoleSkeleton from './components/ConsoleSkeleton'
import Header from './components/Header'
import Landing from './components/Landing'
import RepoConnect from './components/RepoConnect'
import RepoList from './components/RepoList'
import ReviewHistory from './components/ReviewHistory'
import Sidebar from './components/Sidebar'
import { Banner, LoadingPanel } from './components/primitives'
import { useAuth } from './context/AuthContext'

// Code-split: the landing page should not ship the review console, its
// motion features or its markdown renderer before anyone has signed in.
const ReviewConsole = lazy(() => import('./components/ReviewConsole'))

const AUTH_ERRORS = {
  state: 'That sign-in attempt expired or did not match. Please try again.',
  1: 'GitHub sign-in failed. Please try again.',
}

// Only rendered on the landing page, where these anchors exist.
const FOOTER_LINKS = [
  ['#product', 'The product'],
  ['#capabilities', 'What it checks'],
  ['#uses', 'Where it fits'],
  ['#platform', 'Architecture'],
  ['#policies', 'Security and data'],
  ['#contact', 'Contact'],
]

// The session check is a single GET, but it is the first request the browser
// makes - so on a free instance that has gone to sleep it absorbs the whole
// 30-90s cold start. A bare spinner for a minute reads as a hung app, so after
// six seconds the wait says why it is waiting.
function SessionCheck() {
  const [slow, setSlow] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setSlow(true), 6000)
    return () => clearTimeout(id)
  }, [])

  return (
    <LoadingPanel
      label="Checking your session"
      note={
        slow
          ? 'The API may be waking up. An instance that has been idle takes up to a minute to answer its first request.'
          : undefined
      }
    />
  )
}

export default function App() {
  const { user, loading, returning, error, login } = useAuth()
  const [repoRefreshKey, setRepoRefreshKey] = useState(0)
  const [activeReview, setActiveReview] = useState(null)
  const [notice, setNotice] = useState(null)
  // Lifted so the sidebar and the list render the same data from one request.
  // null means "not loaded yet", which the sidebar shows as skeleton rows
  // rather than as an empty list.
  const [repos, setRepos] = useState(null)
  const [expandRequest, setExpandRequest] = useState(null)

  // Stable, so RepoList can keep it in a ref without re-fetching.
  const handleRepos = useCallback((list) => setRepos(list), [])
  const openRepo = useCallback((id) => setExpandRequest({ id, at: Date.now() }), [])

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
      <Suspense fallback={<ConsoleSkeleton />}>
        <ReviewConsole review={activeReview} onExit={() => setActiveReview(null)} />
      </Suspense>
    )
  }

  // The landing page is static and needs no session, so it paints immediately
  // for anyone who was not signed in last time. Only a returning visitor waits
  // on /auth/me, and only they would be jarred by seeing the marketing page
  // for a moment before their dashboard replaces it.
  const onLanding = !user && (!loading || !returning)
  const checkingSession = loading && returning

  const banners = (
    <>
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
    </>
  )

  return (
    <div className="shell">
      <Header />

      {/* Banners sit inside whichever main is rendered, so they stay within
          the content column rather than spanning the sidebar. */}
      {user ? (
        <div className="workspace">
          <Sidebar repos={repos} onSelectRepo={openRepo} />

          <main className="page page--app">
            {banners}

            <section id="repositories">
              <div className="section-title">
                <h2>Repositories</h2>
                <span className="legend">expand one to review its pull requests</span>
              </div>
              <div className="stack">
                <RepoConnect onConnected={() => setRepoRefreshKey((k) => k + 1)} />
                <RepoList
                  refreshKey={repoRefreshKey}
                  onReviewStart={setActiveReview}
                  onLoaded={handleRepos}
                  expandRequest={expandRequest}
                />
              </div>
            </section>

            <section id="reviews">
              <div className="section-title">
                <h2>Recent reviews</h2>
                <span className="legend">saved, so closing a report does not lose it</span>
              </div>
              <ReviewHistory onOpen={setActiveReview} refreshKey={repoRefreshKey} />
            </section>
          </main>
        </div>
      ) : (
        <main className="page">
          {banners}
          {onLanding && <Landing onLogin={login} />}
          {checkingSession && <SessionCheck />}
        </main>
      )}

      <footer className="footer">
        {onLanding && (
          <nav className="footer__nav" aria-label="Page sections">
            {FOOTER_LINKS.map(([href, label]) => (
              <a key={href} href={href}>
                {label}
              </a>
            ))}
          </nav>
        )}
        <p className="footer__line">CodeArmor - automated analysis, not an approval</p>
      </footer>
    </div>
  )
}
