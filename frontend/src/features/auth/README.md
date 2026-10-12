# Auth Feature

## Purpose

Supabase authentication panel (FE-02, FE-03 auth states).

## Behavior

- Signed out: email / password / mode form with
  sign-in and sign-up modes.
- Signed in: shows the account email and a sign-out
  button.
- Outcomes are reported to the status channel
  (`status.authenticationFailed`, `summary.checkEmail`, …).

## Key Exports

- `AuthPanel({ session, authLoading })`

## Security

- Passwords are only sent to Supabase Auth, never
  to the application API.
- `autoComplete` attributes guide password managers.

## Testing

- `AuthPanel.test.jsx` — form rendering, signed-in
  state, loading state
