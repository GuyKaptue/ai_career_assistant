import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';

const BACKEND = process.env.VITE_DEV_BACKEND || 'http://127.0.0.1:8000';

// Dev/build config: the React plugin enables the automatic JSX runtime,
// so .jsx files using JSX (e.g. <I18nContext.Provider>) work without an
// explicit `import React`. (Vitest has its own vitest.config.js.)
export default defineConfig({
  plugins: [tailwindcss(), react()],
  server: {
    host: '0.0.0.0',
    port: 5173,
    // Proxy the API to the local backend so the browser makes same-origin
    // requests. This removes the CORS dependency on a fixed dev port —
    // Vite falls back to 5174/5175… when 5173 is taken, and an origin not in
    // the backend's explicit allowlist would otherwise be blocked.
    proxy: {
      '/api': {
        target: BACKEND,
        changeOrigin: true,
      },
      '/health': {
        target: BACKEND,
        changeOrigin: true,
      },
      '/ready': {
        target: BACKEND,
        changeOrigin: true,
      },
      '/docs': {
        target: BACKEND,
        changeOrigin: true,
      },
      '/openapi.json': {
        target: BACKEND,
        changeOrigin: true,
      },
    },
  },
});
