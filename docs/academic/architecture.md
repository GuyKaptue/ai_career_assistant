# Architecture

## 1. Layered design

The backend follows a four-layer architecture. Each layer depends only
on layers below it (and the domain models it needs); no layer imports
HTTP concerns from the layer above.

```
┌─────────────────────────────────────────────────────────────┐
│ api/routes/          HTTP endpoints (FastAPI routers)        │
│                      - parse request, derive identity        │
│                      - map domain errors → HTTP status       │
├─────────────────────────────────────────────────────────────┤
│ application/services/ Use-case orchestration                │
│                      - stateless, testable, no HTTP          │
├─────────────────────────────────────────────────────────────┤
│ domain/              Models (jobs, documents, users,        │
│                      templates, applications)                │
├─────────────────────────────────────────────────────────────┤
│ infrastructure/      Prompts, document export               │
├─────────────────────────────────────────────────────────────┤
│ core/                config, errors, persistence,           │
│                      security, observability, middleware     │
└─────────────────────────────────────────────────────────────┘
```

## 2. Separation of concerns

| Layer | Responsibility | Forbidden |
|-------|---------------|-----------|
| `api/routes` | HTTP, auth, validation, error mapping | Business logic |
| `application/services` | Use cases, orchestration | HTTP objects |
| `domain` | Models, rules, normalization | I/O, HTTP |
| `infrastructure` | External adapters (prompts, export) | Business rules |
| `core` | Cross-cutting (config, errors, persistence) | Use-case logic |

## 3. Persistence

Two backends, selected by configuration:

- **Supabase** (Postgres via REST): production. Uses `SupabaseRepository`
  with `Prefer: return=representation`, RLS, and fallback to in-memory
  when the table is missing (for hermetic tests).
- **In-memory**: tests and local dev. Deterministic, no I/O.

Both implement the same interface: `create`, `get`, `list_for_user`,
`update`, `delete`.

## 4. Authorization

- Identity comes from the JWT `sub` claim (`validate_bearer_token`).
- Every route (except `/health`) requires a Bearer token.
- Cross-user access returns 404 (not 403).
- RLS enforces ownership at the database layer.

## 5. Error model (§BE-06)

Nine typed error classes, mapped to HTTP status codes:

| Error | Status |
|-------|--------|
| `ValidationError` | 422 |
| `AuthenticationError` | 401 |
| `AuthorizationError` | 404 |
| `NotFoundError` | 404 |
| `ConfigurationError` | 500 |
| `DatabaseError` | 500 |
| `ExternalError` | 502 |
| `AIProviderError` | 502 |
| `ExportError` | 500 |

All errors return a unified `{detail, category}` envelope. Internal
details are logged server-side but never returned to the client.

## 6. Extension points

- **New job provider:** subclass `JobProvider` in `domain/jobs/`.
- **New template:** add to `TemplateRegistry` in `domain/templates/`.
- **New AI provider:** subclass `LanguageModelAdapter`.
- **New document format:** add a renderer in `infrastructure/document_export/`.

## 7. Observability

- Structured JSON logs with sanitized correlation IDs.
- Metrics (Prometheus-style): requests, latency, fallbacks, health.
- Security headers, CORS allowlist, per-IP rate limiting.

## Related documents

- [system.md](system.md)
- [mathematical.md](mathematical.md)
- [../architecture/template-system.md](../architecture/template-system.md)