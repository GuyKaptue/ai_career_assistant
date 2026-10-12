# Core — Security

## Purpose

Authentication and authorization: JWT validation,
identity derivation, and cross-user isolation.

## Responsibilities

- Validate Supabase-issued JWTs (legacy HS256 shared secret; modern
  ES256/RS256 via the Supabase JWKS with strict `iss`/`aud` checks)
- Derive `user_id` from the JWT `sub` claim
- Reject tokens with weak signing secrets
- Enforce ownership at the API layer

## Architecture

```
core/security/
├── __init__.py
├── auth.py          # validate_bearer_token()
└── dependencies.py  # get_current_user (FastAPI dependency)
```

## Public API

- `validate_bearer_token(token) -> dict` (returns JWT claims)
- `get_current_user` — FastAPI dependency (HTTPBearer)

## Configuration

- `SUPABASE_JWT_SECRET` — legacy HS256 signing secret (min 32 bytes
  for HS256; shorter secrets raise `RuntimeError`)
- `SUPABASE_URL` — issuer (`{SUPABASE_URL}/auth/v1`) and JWKS base
  (`{SUPABASE_URL}/auth/v1/.well-known/jwks.json` for ES256/RS256)

## Security

- Identity is **never** taken from the request body
- Cross-user access returns 404 (not 403) to avoid leaking
  resource existence
- RLS (Supabase) enforces ownership at the database layer

## Error Handling

- `AuthenticationError` — missing/invalid token (401)
- `ConfigurationError` — auth not configured (500)
- `ValueError` — invalid/expired token

## Testing

- `tests/test_auth.py` — token validation
- `tests/test_authorization.py` — cross-user isolation

## Related Modules

- `app.core.config` — settings
- `app.core.errors` — error mapping
