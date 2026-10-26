## Purpose

The application layer: the use cases that sit between the HTTP API and the
domain/infrastructure layers. Stateless, testable, and free of HTTP
concerns.

## Responsibilities

- Orchestrate the domain rules for one request
- Call the AI layer through the model router facade (never the provider
  clients directly)
- Enforce the preconditions of a use case (a CV present? a job present?)
  and answer with a clarifying turn instead of guessing
- Keep the privacy rules: the CV, the message, the job text, the prompt
  and the answer are never logged

## Packages

| Path | What it owns |
|---|---|
| `services/` | the use cases: generation, ATS, chat, job search, retrieval, the intent routing |

`app/application/services/README.md` lists every service and the public
entry points.

## Rules

- Identity is passed in as a parameter, never read from a global
- No `Request`/`Response` objects, no status codes
- A use case either returns a result or raises a typed error from
  `app.core.errors`

## Testing

- `tests/unit/` — the use cases with fake adapters
- `tests/api/` — the same use cases through the HTTP surface

## Related Modules

- `app.domain` — the models
- `app.api.routes` — the HTTP endpoints
- `app.infrastructure` — the adapters
