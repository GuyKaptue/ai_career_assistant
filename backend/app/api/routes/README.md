# API — Routes

## Purpose

HTTP endpoints (FastAPI). Thin layer: parse request,
derive identity, delegate to application services,
map errors to HTTP status codes.

## Responsibilities

- Request validation (Pydantic)
- Identity derivation (JWT `sub`)
- Error mapping (domain errors → HTTP status)
- Pagination parameters

## Architecture

```
api/routes/
├── __init__.py
├── applications.py   # application tracker CRUD
├── chat.py           # chat sessions + completions (Bearer JWT)
├── documents.py      # document CRUD + export + RAG index/retrieve
├── health.py         # health check
├── knowledge.py      # career knowledge base (search / ingest)
└── profiles.py       # user profile
```

## Endpoints

- `GET /health` — health check
- `GET/PUT /api/v1/profiles/me` — profile
- `POST /api/v1/documents/cv/generate` — CV generation
- `POST /api/v1/documents/cover-letter/generate` — cover letter
- `POST /api/v1/documents/resume/analyze` — ATS analysis
- `GET /api/v1/documents` — list documents
- `GET /api/v1/documents/{id}/export` — export (HTML/PDF/DOCX)
- `GET /api/v1/jobs/search` — job search (query/location/page/limit + radius_km/published_since_days/work_time/contract_type filters + optional candidate_text re-rank)
- `GET /api/v1/knowledge/search` — career knowledge retrieval (public, attributed)
- `POST /api/v1/knowledge/ingest` — add a knowledge entry (authenticated)
- `GET/POST/PUT/DELETE /api/v1/applications` — tracker
- `GET/POST /api/v1/chat/sessions` — list / create chat sessions (Bearer JWT)
- `GET/DELETE /api/v1/chat/sessions/{id}` — get thread (with messages) / delete (Bearer JWT)
- `POST /api/v1/chat/completions` — send a message, get an AI reply with sources/artifact (Bearer JWT, optional `model_id` pin + deterministic HF fallback)
- `GET /api/v1/models` — routable models for the picker (public)

## Security

- All routes (except `/health`) require Bearer JWT
- Identity from JWT `sub`, never from request body
- Cross-user access → 404

## Error Handling

- `AuthenticationError` → 401
- `AuthorizationError` → 404
- `ValidationError` → 422
- `ConfigurationError` → 500
- `AIProviderError` → 502

## Testing

- `tests/test_api.py` — endpoint tests
- `tests/test_authorization.py` — auth + isolation

## Related Modules

- `app.application.services` — use cases
- `app.core.security` — auth
- `app.core.errors` — error mapping
