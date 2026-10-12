# Frontend error log — `React is not defined` (2026-10-09)

> **Status: RESOLVED.** Missing `frontend/vite.config.js` meant `vite dev`
> ran without `@vitejs/plugin-react`, so JSX compiled to the classic runtime
> (`React.createElement`) while hook-only modules never import `React`.
> Fix: created `frontend/vite.config.js` with `plugins: [react()]`.
> Restart the dev server + hard-refresh to clear stale HMR state.
> Original console output preserved below for the record.

## Original console output (verbatim)

```text
react-dom_client.js?v=eb77ceaf:21551 Download the React DevTools for a better development experience: https://reactjs.org/link/react-devtools
index.jsx:64 Uncaught ReferenceError: React is not defined
    at I18nProvider (index.jsx:64:3)
(anonymous)	@	index.jsx:64
postMessage
(anonymous)	@	main.jsx:8
index.jsx:64 Uncaught ReferenceError: React is not defined
    at I18nProvider (index.jsx:64:3)
(anonymous)	@	index.jsx:64
postMessage
(anonymous)	@	main.jsx:8
react-dom_client.js?v=eb77ceaf:14032 The above error occurred in the <I18nProvider> component:

    at I18nProvider (http://localhost:5173/src/i18n/index.jsx:24:32)

Consider adding an error boundary to your tree to customize error handling behavior.
Visit https://reactjs.org/link/error-boundaries to learn more about error boundaries.

## Line-by-line explanation

| Log line | Meaning |
|----------|---------|
| `Download the React DevTools…` | Info hint from `react-dom` in dev mode. Not an error. |
| `Uncaught ReferenceError: React is not defined` | The crash: compiled output calls `React.createElement` with no `React` binding in the module (it only imports hooks — correct for the automatic JSX runtime). |
| `at I18nProvider (index.jsx:64:3)` | Faulting code runs inside `I18nProvider` during render. Positions refer to Vite's compiled output, not source lines. |
| `(anonymous) @ index.jsx:64` / `postMessage` / `(anonymous) @ main.jsx:8` | React dev-mode re-throw path (`postMessage` → message event) so the render error surfaces in the console. `main.jsx:8` is the `createRoot().render()` call. |
| `The above error occurred in the <I18nProvider> component` | Error-boundary warning naming the nearest component. The `localhost:5173/src/…` URL proves this came from the Vite dev server, not the production build. |
| `Consider adding an error boundary…` | Generic React advice — deliberately not applied: a boundary would hide a fatal boot misconfiguration. The build-config fix plus the `window.onerror` collector below is the right response. |

## Why Vitest passed but the browser crashed

- `vitest.config.js` loads `plugins: [react()]` → automatic JSX runtime → hooks-only imports suffice → tests green.
- `vite dev` / `vite build` had no config file → no React plugin → classic runtime → every JSX file without `import React` throws. `I18nProvider` renders first, so it crashed the whole tree.

## Debugging aids added (print/debug output)

1. `frontend/src/lib/debug.js` — `debugLog(scope, message, data)` + `getDebugBuffer()`: `[ACA:<scope>]` console.debug lines plus a capped (200-entry, timestamped) ring buffer exposed as `window.__ACA_DEBUG__`; `window.onerror` / `window.onunhandledrejection` handlers record fatal boot errors even if React never mounts.
2. `main.jsx` — boot, env-presence (never values), and mount-success lines.
3. `i18n/index.jsx` — provider init, stored-locale resolution, every locale switch.
4. `hooks/useStatus.jsx` — every `report(status, summary)` call (user-visible status trail).
5. `lib/api.js` — method + path, auth presence (boolean only), failure statuses, network-error hints pointing back here.
6. Backend `cv_pdf_extractor.py` + `POST /api/v1/resume/extract` — PDF path, page count, per-page chars, totals, empty-result warnings (bytes never logged).
7. CV upload components — file selection (name/size/type only), upload start/success/failure (never file bytes).

postMessage
(anonymous)	@	main.jsx:8
react-dom_client.js?v=eb77ceaf:19413 Uncaught ReferenceError: React is not defined
    at I18nProvider (index.jsx:64:3)
(anonymous)	@	index.jsx:64
postMessage
(anonymous)	@	main.jsx:8
```
