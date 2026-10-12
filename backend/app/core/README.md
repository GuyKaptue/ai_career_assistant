# Core — Cross-Cutting Infrastructure

## Purpose

Configuration, error model, observability, and
persistence primitives shared by every layer.
No business logic lives here.

## Responsibilities

- Typed settings with runtime validation
- Centralized error taxonomy → HTTP mapping
- Structured JSON logging with correlation ids
- Security headers, request logging, rate limiting
- In-process metrics registry
- Repository abstraction (Supabase + in-memory)

## Architecture

```
core/
├── __init__.py
├── config.py        # AppSettings + validate_runtime_environment()
├── errors.py        # 9 typed errors + exception handlers
├── metrics.py       # MetricsRegistry (counters/gauges/summaries)
├── middleware.py    # rate limit, request logging, security headers
├── observability.py # configure_logging() (JSON logs)
├── persistence.py   # SupabaseRepository + InMemoryRepository
└── security/        # JWT auth (see security/README.md)
```

## Key Modules

- `config.py` — `AppSettings` (env-bound), `settings` singleton,
  `validate_runtime_environment()` (fail-fast 503 when required
  config is missing)
- `errors.py` — `ValidationError`, `AuthenticationError`,
  `AuthorizationError`, `NotFoundError`, `ExternalServiceError`,
  `AIProviderError`, `DatabaseError`, `ExportError`,
  `ConfigurationError`; `register_exception_handlers()` maps them to
  the unified `{detail, category}` envelope; internal details are
  logged server-side, never returned
- `observability.py` — `configure_logging()`: structured JSON logs
  with sanitized correlation id and whitelisted fields (no secrets)
- `middleware.py` — `RateLimitMiddleware` (per-IP fixed window,
  429 + `Retry-After` + `X-RateLimit-*`), `RequestLoggingMiddleware`
  (duration + correlation id), `SecurityHeadersMiddleware`
  (nosniff/DENY/referrer/COOP/permissions/CSP/HSTS-prod)
- `metrics.py` — thread-safe `MetricsRegistry` with Prometheus-style
  labeled keys; in-process only (no external backend is faked)
- `persistence.py` — `SupabaseRepository` (PostgREST with
  `Prefer: return=representation`, UUID ids) and
  `InMemoryRepository` (hermetic tests); backend selected at call
  time from settings

## Configuration

- `SUPABASE_JWT_SECRET` — HS256 signing secret (min 32 bytes)
- `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` — persistence
- `RATE_LIMIT_PER_MINUTE` — 0 disables rate limiting
- `LOG_LEVEL` — structured log verbosity

## Security

- Errors never leak stack traces or internal details to clients
- Secrets are never logged (whitelist-only log fields)
- Rate limiting sits innermost so 429s still get security headers

## Testing

- `tests/test_error_model.py` — error envelope
- `tests/security/test_observability.py` — logging, middleware,
  rate limiting
- `tests/test_supabase_crud.py` — live persistence proof

## Related Modules

- `app.api.routes` — HTTP endpoints
- `app.application.services` — use cases
- `app.core.security` — authentication
