import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // One .env for the whole repo, at the root. Only VITE_* variables reach the
  // browser bundle, so the backend secrets in the same file stay server-side.
  envDir: '..',
  test: {
    environment: 'jsdom',
  },
  server: {
    // The backend's ALLOWED_ORIGINS lists this port; drifting to another one
    // when it is busy would fail CORS with a confusing error, so fail here.
    strictPort: true,
  },
})
