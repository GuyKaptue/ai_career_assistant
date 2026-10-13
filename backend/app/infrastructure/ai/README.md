# Infrastructure — AI Prompts

## Purpose

Prompt builders for AI generation and analysis.
The actual model adapters and routing live in
`app/application/services/` (see `ai_registry.py`,
`ai_discovery.py`, `shared_router.py`).

## Responsibilities

- Build deterministic prompts from user-supplied facts
- Never invent employment, education, metrics, or skills
- Omit metrics that are not provided (no fabrication)

## Architecture

```
infrastructure/ai/
├── __init__.py
└── prompts/
    ├── __init__.py
    ├── cv.py              # build_cv_prompt, build_cover_letter_prompt
    ├── resignation.py     # build_resignation_prompt
    └── resume_analysis.py # build_resume_analysis_prompt
```

## Public API

- `build_cv_prompt(...)` — CV generation prompt
- `build_cover_letter_prompt(...)` — cover-letter prompt
- `build_resume_analysis_prompt(...)` — resume analysis prompt
- `build_resignation_prompt(...)` — resignation-letter prompt

## Rules

- If a metric is not provided, omit it — do not fabricate one
- Prompts contain only user-supplied career facts
- No PII defaults, no hardcoded employer

## Data Flow

```
Backend → Ollama (local, preferred) → Hugging Face Inference API
  payload: {"inputs": prompt, "parameters": {...}}
  response: generated text (validated against Pydantic schema)
```

Only the **prompt** (user-supplied career facts) is sent.
No JWT, user_id, stored documents, or tracker data is sent.

The local-first channel lives in `backend/app/application/services/`; a
circuit breaker around Ollama fails over to the Hugging Face chain, and a
pinned non-Ollama `model_id` skips Ollama entirely. Operator guide:
[`docs/deployment/ollama.md`](../../../docs/deployment/ollama.md).

## Configuration

- `HF_TOKEN` — Hugging Face API token (fallback step of the inference chain)
- `USE_OLLAMA`, `OLLAMA_MODEL`, `OLLAMA_BASE_URL` — local inference (no credential)
- `AI_ENABLE_DISCOVERY` — enable model discovery
- `AI_DISCOVERY_QUERY` — discovery search query
- `AI_DISCOVERY_LIMIT` — max models to discover
- `AI_MAX_PARAMETERS` — max model parameters (e.g. 8B)

## Security

- `HF_TOKEN` is read from environment, never logged
- Prompts are not logged (observability uses correlation IDs only)
- Responses are validated against Pydantic schemas before use

## Error Handling

- `RuntimeError` — no `HF_TOKEN` configured
- `AIProviderError` — provider failure (mapped to 502)
- `ValidationError` — response failed schema validation

## Testing

- `tests/test_ai_router.py` — routing + discovery
- `tests/test_api.py` — endpoint tests with mocked adapter

## Related Modules

- `app.application.services.shared_router` — singleton wiring
- `app.application.services.ai_registry` — model metadata + approval
- `app.application.services.ai_discovery` — dynamic model discovery
