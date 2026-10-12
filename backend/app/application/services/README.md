# Application — Services

## Purpose

Use-case orchestration: the layer between the
API (HTTP) and the domain/infrastructure layers.
Stateless, testable, and free of HTTP concerns.

## Responsibilities

- Document generation (CV, cover letter, resignation)
- Resume analysis (ATS scoring, keyword extraction)
- Job search orchestration
- Application tracking
- Profile management
- AI routing and model discovery

## Architecture

```
application/services/
├── __init__.py
├── ai_discovery.py          # dynamic model discovery
├── ai_model_router.py       # model selection
├── ai_profiles.py           # per-task model profiles
├── ai_registry.py           # model metadata + approval policy
├── ai_scoring.py            # ATS scoring
├── ai_tokenizer.py          # token estimation
├── application_tracking.py
├── ats_checker.py           # ATS depth (BE-03)
├── context_budget.py        # bounded-context builder (RD-03/RD-05)
├── cv_pdf_extractor.py      # PDF text extraction
├── document_generation.py   # rendering
├── document_retrieval.py    # personal document RAG (RD-05)
├── document_store.py        # persistence
├── knowledge_base.py        # RAG knowledge base (RD-03)
├── profile_service.py
├── semantic_matching.py     # semantic job matching (RD-04)
└── shared_router.py         # shared adapter singleton (AI-01..10)
```

## Key Services

- `search_jobs()` — job search with retry/cache/pagination
- `generate_cv()` / `generate_cover_letter()` — document generation
- `analyze_resume()` — ATS analysis
- `get_adapter()` — shared AI adapter singleton
- `get_knowledge_base()` — RAG knowledge retrieval (RD-03)
- `SemanticMatchingService` / `check_resume_semantic()` — semantic + ATS combined matching (RD-04)
- `DocumentRetrievalService` / `get_document_retrieval()` — personal document chunking, indexing, and user-scoped retrieval (RD-05)
- `build_bounded_context()` — shared context-overflow safeguard used by both retrieval services

## Security

- No HTTP concerns (no request/response objects)
- Identity passed in as parameters, never from globals
- No secrets logged

## Testing

- `tests/test_ats_checker.py`
- `tests/test_jobs_hardening.py`
- `tests/test_ai_router.py`
- `tests/unit/test_knowledge_base.py`
- `tests/unit/test_semantic_matching.py`
- `tests/unit/test_document_retrieval.py`
- `tests/unit/test_context_budget.py`

## Related Modules

- `app.api.routes` — HTTP endpoints
- `app.domain` — domain models
- `app.infrastructure` — providers/export
