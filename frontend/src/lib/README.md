# Lib

## Purpose

Infrastructure clients shared by the frontend.

## Modules

- `supabase.js` — Supabase client (auth, RLS).
  Fails fast when `VITE_SUPABASE_URL` or
  `VITE_SUPABASE_ANON_KEY` is missing.
- `api.js` — API client: `apiBase` resolution from
  `VITE_API_URL`, bearer-token injection from the
  session, and `apiRequest()` with error detail
  extraction from backend error responses. `apiUpload()`
  posts multipart `FormData` (CV PDFs) without forcing a
  JSON content type. Every request/failure is traced via
  `[ACA:api]` debug lines (see `debug.js`).
- `debug.js` — print-debugging helper: `debugLog(scope, message, data)`
  prints `[ACA:<scope>]` lines and keeps a 200-entry ring buffer exposed
  as `window.__ACA_DEBUG__`; `installGlobalErrorCollector()` records
  `window.onerror` / unhandled rejections for fatal boot errors.
  See `docs/debugging/react-not-defined.md`.

## Key Exports

- `supabase`, `getSupabaseClient()`
- `getApiBase()`, `authHeaders(session, extra)`, `apiRequest(path, options)`, `apiUpload(path, options)`
- `debugLog(scope, message, data)`, `getDebugBuffer()`, `installGlobalErrorCollector()`
