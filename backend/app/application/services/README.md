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
├── career_assistant.py      # intent routing + the chat turns (RD-06/RD-08)
├── career_intent.py         # the intent model and the rule tables (RD-06)
├── career_prompts.py        # the per-intent prompts (RD-06)
├── candidate_analysis.py    # the candidate profile the model extracts
├── chat_input.py            # input analysis and the job signals
├── context_budget.py        # bounded-context builder (RD-03/RD-05)
├── cv_pdf_extractor.py      # PDF text extraction
├── document_generation.py   # rendering
├── document_retrieval.py    # personal document RAG (RD-05)
├── document_store.py        # persistence
├── job_resolution.py        # job posting ingestion (URL or pasted text)
├── job_search_pipeline.py   # the one and only job scoring formula
├── job_target.py            # the verified job target (title/company/skills)
├── knowledge_base.py        # RAG knowledge base (RD-03)
├── model_router_facade.py   # the model-facing API the services use
├── profile_service.py
├── rag_enrichment.py        # RAG enrichment for a generation request
├── semantic_matching.py     # semantic job matching (RD-04)
├── shared_router.py         # shared adapter singleton (AI-01..10)
├── tailoring_pipeline.py    # CV tailoring and cover letters
└── template_service.py      # template resolution
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
- `classify_intent()` / `classify_intents()` — the intent model and the rule tables (RD-06)
- `build_career_messages()` — the per-intent prompts; the CV is always data (RD-06)
- `run_career_turn()` — the intent routing and the chat turns (RD-06/RD-08)
- `build_job_target()` — the verified job target; the score is never the model's (RD-08)
- `resolve_job_from_text()` / `resolve_job_from_url()` — the job ingestion (RD-08)
- `tailor_cv()` / `write_cover_letter()` — the document pipelines (RD-08)
- `score_job()` — the only job scoring formula

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
- `tests/unit/test_career_intent.py`
- `tests/unit/test_career_prompts.py`
- `tests/unit/test_job_target.py`
- `tests/unit/test_job_resolution.py`
- `tests/unit/test_chat_store_job_context.py`
- `tests/api/test_career_chat.py`
- `tests/api/test_chat_job_flows.py`

## Related Modules

- `app.api.routes` — HTTP endpoints
- `app.domain` — domain models
- `app.infrastructure` — providers/export
