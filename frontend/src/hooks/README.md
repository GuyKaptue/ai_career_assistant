# Hooks

## Purpose

Shared state and data access (FE-02 services/hooks).

## Hooks

| Hook | Purpose |
| --- | --- |
| `useSession` | Supabase session + auth listener |
| `useAsync` | `idle/loading/success/error` state machine with `retry` |
| `useStatus` | Global status channel (`StatusProvider` + `useStatus`) |
| `useTemplates` | Template catalog with reload |
| `useApplications` | Application CRUD: `create`, `move`, `remove`, `reload` |

## Conventions

- Hooks never read cross-feature state directly;
  they receive dependencies as arguments.
- `useAsync.run(operation)` returns the data or
  `null` on error; the error is kept for retry
  messaging.

## Testing

- `useAsync.test.js` — phase transitions, retry
- `i18n/index.test.jsx` — provider behavior
