import { defineConfig } from 'vite'

export default defineConfig({
  server: {
    // Serve on 127.0.0.1 (not just localhost/::1) so the app and the backend
    // share the same host and session cookies are sent by the browser.
    host: '127.0.0.1',
    port: 5173,
  },
})
