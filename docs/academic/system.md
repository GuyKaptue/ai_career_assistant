# System description

## 1. Purpose

The AI Career Assistant is an open-source, self-hostable career platform.
It assists users in creating CVs and cover letters, reviewing resumes
against job descriptions (ATS scoring), tracking job applications, and
discovering jobs across free public APIs.

## 2. Components

```
┌─────────────────────────────────────────────────────────────┐
│  Client (React + Vite SPA)                                  │
│  - Auth via Supabase (JWT, HS256)                          │
│  - Document studio, ATS review, tracker, job search        │
└──────────────────────┬──────────────────────────────────────┘
                       │ HTTPS + Bearer JWT
                       ▼
┌─────────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                          │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ core/          config, errors, persistence,           │   │
│  │                security, observability, middleware    │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ api/routes/    HTTP endpoints (thin)                  │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ application/   services (use-case orchestration)      │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ domain/        models (jobs, documents, users,        │   │
│  │                templates, applications)               │   │
│  ├──────────────────────────────────────────────────────┤   │
│  │ infrastructure/ prompts, document export              │   │
│  └──────────────────────────────────────────────────────┘   │
│                       │                                       │
│         ┌─────────────┴──────────────┐                        │
│         ▼                            ▼                        │
│  Supabase (Postgres + Auth)    Hugging Face Inference API    │
│  (RLS, row-level ownership)    (optional, opt-in)            │
└─────────────────────────────────────────────────────────────┘
```

## 3. Data model

| Table | Key | Ownership |
|-------|-----|-----------|
| `profiles` | `user_id` (FK → `auth.users`) | `auth.uid() = user_id` |
| `documents` | `id` (UUID) | `auth.uid() = user_id` |
| `job_applications` | `application_id` (UUID) | `auth.uid() = user_id` |

Every row is scoped by `user_id`. Row-level security (RLS) enforces
ownership at the database layer; the API layer derives identity from the
JWT `sub` claim and never from the request body.

## 4. Invariants

1. **Identity:** `user_id` always equals the authenticated JWT `sub`.
   Cross-user access returns 404 (not 403) to avoid leaking existence.
2. **No fabrication:** a value that the system cannot know is `None`.
   Context windows, quality scores, and parameter counts are never
   invented (see `ModelMetadata.unknown_fields()`).
3. **Fail closed:** an unavailable AI provider raises `AIProviderError`
   (mapped to 502); the caller decides whether to fall back to local
   templates. The system never silently returns fake-valid output.
4. **No silent fallback to placeholder data:** when no job provider is
   configured, the search endpoint returns 503, not mock data.
5. **No secrets in logs:** prompts, document content, `HF_TOKEN`, and
   database credentials are never logged. Observability uses sanitized
   correlation IDs only.

## 5. Configuration surface

| Variable | Purpose |
|----------|---------|
| `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` | Database + Auth |
| `SUPABASE_JWT_SECRET` | JWT signing (min 32 bytes for HS256) |
| `HF_TOKEN` | Hugging Face inference (required for `use_ai=true`) |
| `JOB_PROVIDER` | Comma-separated job provider names |
| `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` | Adzuna credentials |
| `AI_ENABLE_DISCOVERY` | Enable dynamic model discovery |
| `ROUTING_WEIGHTS` | Weighted routing score override |

## 6. Deployment modes

- **Self-hosted:** Supabase (self-hosted or managed) + this repo.
- **Offline:** `HF_TOKEN` unset → deterministic local templates only.
- **Online:** `use_ai=true` + `HF_TOKEN` set → Hugging Face inference.

## Related documents

- [mathematical.md](mathematical.md)
- [architecture.md](architecture.md)
- [limitations.md](limitations.md)