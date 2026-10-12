# API — Schemas

## Purpose

Typed request/response contracts for every endpoint
with a body. Pydantic models keep the API surface
explicit and OpenAPI-documented.

## Responsibilities

- Request validation (loose payloads: optional fields,
  `exclude_unset` forwarding to services)
- Response envelopes (`Health`, `Ready`, `ErrorResponse`)
- Shared error responses (`COMMON_ERROR_RESPONSES`,
  `GENERATION_ERROR_RESPONSES`)

## Architecture

```
api/
├── __init__.py
├── schemas.py      # request/response models (this module)
└── routes/         # endpoint implementations (see routes/README.md)
```

## Request Models

- `ProfilePayload` — `PUT /api/v1/profiles/me`
- `DocumentPayload` — `POST/PATCH /api/v1/documents[...]`
- `ApplicationPayload` — application tracker CRUD
- `CVGenerationPayload` / `CoverLetterGenerationPayload` /
  `ResignationPayload` — generation endpoints (`use_ai` flag)
- `ResumeCheckPayload` — `POST /api/v1/resume/check`
- `KnowledgeSearchPayload` / knowledge ingest — knowledge base
- `TemplatePreviewPayload` — `POST /api/v1/templates/preview`

All payloads extend `_LoosePayload` (extra fields ignored),
so forward-compatible clients never break the API.

## Response Models

- `Health` / `Ready` — probe responses
- `ErrorResponse` — unified `{detail, category}` envelope
  (categories: validation, authentication, authorization,
  not_found, ai_provider, external_service, database, export,
  configuration, rate_limited, unavailable, internal)

## Security

- Schemas never carry identity — user id comes from the
  JWT `sub` claim via `get_current_user`
- `exclude_unset=True` prevents clients from overwriting
  fields they did not send

## Testing

- `tests/test_error_model.py` — error envelope contracts
- `tests/api/` — endpoint-level request/response tests

## Related Modules

- `app.api.routes` — endpoints using these schemas
- `app.domain.documents.schemas` — domain-level generation
  contracts (`CVGenerationResult` etc.)
- `app.core.errors` — error taxonomy behind `ErrorResponse`
