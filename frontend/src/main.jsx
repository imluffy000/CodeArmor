import React from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import ErrorBoundary from './components/ErrorBoundary'
import { AuthProvider } from './context/AuthContext'
import './styles.css'

// Local development only. The backend's OAuth callback lands on 127.0.0.1, and
// localhost is a separate origin with its own cookie jar, so opening the app on
// localhost would leave the session cookie unreachable. In production the
// cookie is SameSite=None + Secure and this does not apply, so the redirect
// must not ship: on a deployed domain it is dead code at best, and it breaks
// `npm run preview` (port 4173) at worst.
if (import.meta.env.DEV && window.location.hostname === 'localhost') {
  window.location.replace(window.location.href.replace('//localhost', '//127.0.0.1'))
}

createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <ErrorBoundary>
      <AuthProvider>
        <App />
      </AuthProvider>
    </ErrorBoundary>
  </React.StrictMode>
)
