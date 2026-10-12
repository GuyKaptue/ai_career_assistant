# Components

## Purpose

Shared UI primitives (FE-03 loading/empty/error/
auth states).

## Components

| Component | Purpose |
| --- | --- |
| `StatusBanner` | Renders the global status channel in an `aria-live` region |
| `AsyncStates` | `LoadingState` (`role="status"`), `EmptyState`, `ErrorState` (`role="alert"` + retry) |
| `AuthGuard` | Sign-in prompt when no session exists |

## Accessibility

- Loading states use `role="status"`.
- Error states use `role="alert"` and offer a
  retry action.
- `AuthGuard` accepts an optional `session` prop
  for testability; it falls back to the global
  session hook.

## Testing

- `AsyncStates.test.jsx` — roles, retry wiring
