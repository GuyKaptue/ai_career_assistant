# Frontend — Source

## Purpose

React 18 + Vite single-page application for the
AI Career Assistant. Thin shell that composes
feature modules; all feature-local state lives
inside the feature.

## Structure

```
src/
├── App.jsx              # application shell (composition only)
├── main.jsx             # entry point + providers
├── styles.css           # global styles, Kanban, modal, a11y
├── types.js             # JSDoc contracts mirroring backend schemas
├── components/          # shared UI (StatusBanner, AsyncStates, AuthGuard)
├── features/            # feature modules (auth, documents, resume-checker, jobs, tracker)
├── hooks/               # useSession, useAsync, useStatus, useTemplates, useApplications
├── i18n/                # I18nProvider + en/de/fr locales
└── lib/                 # supabase client, API client
```

## Architecture

- **Shell owns cross-feature state** (document form, template
  selection, generation); features own their local state.
- **Providers** (`I18nProvider`, `StatusProvider`) wrap the app
  in `main.jsx`.
- **`useAsync`** is the shared loading/error/success state
  machine with `retry` support.
- **`StatusBanner`** renders the global status channel in an
  `aria-live` region.

## Testing

- `npm test` — Vitest + React Testing Library + jsdom
- 25 tests across i18n, hooks, components, and features

## Related Modules

- `backend/app/api/routes` — the API this frontend consumes
- `supabase/migrations` — auth + RLS policies
