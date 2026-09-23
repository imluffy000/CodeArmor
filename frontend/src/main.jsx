import React, { useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './context/AuthContext'
import './styles/tokens.css'
import './styles/base.css'
import './styles/app.css'

// Local development only. The OAuth callback lands on 127.0.0.1, and localhost
// is a separate origin with its own cookie jar, so opening the app on localhost
// would leave the session cookie unreachable. In production the cookie is
// SameSite=None + Secure and this does not apply, so the redirect must not
// ship: on a deployed domain it is dead code, and it breaks `npm run preview`.
if (import.meta.env.DEV && window.location.hostname === 'localhost') {
  window.location.replace(window.location.href.replace('//localhost', '//127.0.0.1'))
}

// The splash in index.html covers the window this bundle takes to download
// and parse. It is torn down here rather than from a script in the page,
// because an effect runs after React has committed its first paint - a
// requestAnimationFrame or a timeout would be guessing at that moment, and
// guessing early uncovers an empty root.
function Boot({ children }) {
  useEffect(() => {
    const splash = document.getElementById('splash')
    if (!splash) return
    splash.dataset.done = 'true'
    const remove = () => splash.remove()
    splash.addEventListener('transitionend', remove, { once: true })
    // transitionend never fires under prefers-reduced-motion, where the
    // transition is suppressed, so this is the guarantee rather than a backstop.
    setTimeout(remove, 500)
  }, [])

  return children
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <Boot>
      <ErrorBoundary>
        <AuthProvider>
          <App />
        </AuthProvider>
      </ErrorBoundary>
    </Boot>
  </React.StrictMode>
)
