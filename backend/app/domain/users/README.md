# Domain — Users

## Purpose

User profile model and identity. The profile is owned by the
authenticated Supabase user and is scoped by `user_id`.

## Responsibilities

- Profile model (name, target role, location, summary)
- Identity derived from the JWT `sub` claim
- Cross-user isolation (404 on foreign access)

## Architecture

```
domain/users/
├── __init__.py
└── models.py     # UserProfile
```

## Data Contracts

`profiles` table (Supabase):
`user_id (PK, FK → auth.users), email (unique), full_name,
target_role, location, summary, created_at, updated_at`

## Security

- `user_id` comes from `auth.uid()`, never from the request body
- RLS policies enforce ownership for select/insert/update
- Cross-user reads return 404 (not 403) to avoid leaking existence

## Testing

- `tests/test_authorization.py` — identity + cross-user isolation
- `tests/test_migrations.py` — RLS policy structure

## Related Modules

- `app.core.security` — JWT validation
- `app.api.routes.profiles` — HTTP endpoints
