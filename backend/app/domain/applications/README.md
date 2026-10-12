# Domain — Applications

## Purpose

Job application tracking: the personal kanban-style board that logs
every application with status, company, position, URL, notes, and
follow-up dates.

## Responsibilities

- Application CRUD scoped to the authenticated user (`user_id`)
- Status flow: `applied → interview → offer → rejected`
- Validation of status transitions
- Ownership enforcement (RLS + API-layer checks)

## Architecture

```
domain/applications/
├── __init__.py
└── models.py     # Application dataclass + status vocabulary
```

## Public API

- `Application` model with `status` constrained to
  `applied | interview | offer | rejected`

## Data Contracts

`job_applications` table (Supabase):
`application_id, user_id, company, position, status, job_url, notes,
applied_date, follow_up_date, created_at, updated_at`

## Dependencies

- Supabase Postgres + RLS

## Security

- Every row is scoped by `user_id`
- RLS policies enforce `auth.uid() = user_id` for all operations
- API layer derives identity from the JWT `sub`, never from the request body

## Error Handling

- `ValidationError` — invalid status or missing fields
- `AuthorizationError` — cross-user access attempt (404, not 403, to avoid
  leaking existence)

## Testing

- `tests/test_api.py` — application tracking endpoint
- `tests/test_authorization.py` — cross-user isolation
- `tests/test_migrations.py` — RLS policy structure

## Related Modules

- `app.domain.jobs` — saving a discovered job to the tracker
- `app.api.routes.applications` — HTTP endpoints
