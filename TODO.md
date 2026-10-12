# AI Career Assistant — TODO List

> **Last updated:** 2026-10-10 (all spec items Done: AI-01…AI-11, BE-01…BE-08, T-00…T-06, FE-01…FE-04, CLI-01, TEST-01/02, CI-01, MAKE-01, HYG-01…03, PRIV-01, DOC-01/02/03, RD-03/04/05, Phase-16 audit + CV-upload/extract + debug-print follow-up + CHAT-01…CHAT-05 AI Chat Platform (Claude/Gemini-style sessions, model picker, artifacts) + CHAT-06 chat UI audit/fixes (build-breaking syntax error, unimported components, ChatBox props refactor, JobDiscovery contract/pagination/a11y, test mocks) + StatusBanner removed from the default chat page + fully responsive/dynamic multi-platform chat shell + CHAT-07 borderless elevation (all white borders/lines removed from every surface incl. CSS, section dividers and form controls; replaced by a full layered `@theme` shadow scale + a recessed `--shadow-recessed` inset for text fields; conversation box and message bubbles rounded with shadow; welcome message verified in en/de/fr; `t()` gained string-fallback support) + CHAT-08 runtime fixes (`select` null-value warning, welcome paragraph min-content width trap, actionable shadow project tiles wired to session modes) + CHAT-09 tailwind-merge shadow-token fix (`extendTailwindMerge` taught the custom `@theme` shadow scale, which was silently swallowing the suggested-prompt card shadows in favour of the Button variant's `shadow-xs`) + CHAT-10 fluid typography (all `--text-*` tokens converted to `clamp()` for continuous scaling across 320-1920px; welcome description now a rounded shadow panel; added `.text-description`/`.text-display`; remaining fixed sizes replaced except the intentional 16px iOS-zoom guard) + CHAT-14 UI pass (found that dialog animations were no-ops because `tailwindcss-animate` is not installed — added real keyframes instead; rebuilt `ui/dialog` as an accessible modal with focus trap, Esc, aria-modal, scroll lock, focus restore and fade+scale; auth dialog is now one dialog with an ARIA tab pair, labelled fields, inline validation, spinner + disabled-while-pending and reset-on-close; Settings is now a dialog with Workspaces/Appearance/AI Models/Account where theme is a radiogroup and the model picker defaults to Auto; composer gained a live char/token counter, IME-safe Enter handling, and a Stop button backed by AbortController + abortable apiRequestWithSignal) + CHAT-13 multi-model chat (verified 10-model pool with per-model HF card licences and live chat-router compatibility probing — only 5 of 10 are chat-capable, 2 of those licence-eligible; `inference_provider_supported` now filters unsupported models out of auto-selection with reason `not_supported_by_provider`; robust system-prompt contracts — strict JSON for analysis, validated markdown for generation, with named-violation repair/retry and a contract-derived deterministic fallback; Auto-selection is the picker default and per-message routing audit is stored in `chat_messages.routing`; fixed a silent data-loss bug where a stale column fell back to in-memory writes) + CHAT-12 frontend/backend connectivity + navigation (root cause was a CORS port mismatch: Vite fell back to 5174 while the backend allowlisted 5173/4173/3000 — fixed with a Vite `/api` dev proxy, a relative API base, and `127.0.0.1` + fallback ports in the CORS defaults; **every dropdown in the app was inert** because Trigger and Content kept separate `open` state — lifted into shared context; App rendered only Chat so the four other workspaces were unreachable and the chat page was a dead end — added `useView` routing, `SettingsMenu`, `WorkspaceShell` with back-to-chat, and four page wrappers; consolidated auth into ONE shared dialog via `useAuthDialog`; project tiles wired to the six DB chat modes with `ChatStore` validating them against the SQL CHECK constraint; removed 12 duplicated i18n keys across en/de/fr) + CHAT-11 crash fixes from dev-server console (incomplete `ThemeContext` default crashed provider-less `useTheme` consumers; unguarded `window.matchMedia` in the default `'system'` theme effect; added `components/ChatLayout.test.jsx` rendering the real Chat->ChatLayout->Sidebar tree, which is what let the wiring ReferenceErrors escape) — backend 404 passed, frontend 135 passed, backend 476 passed, `vite build` clean; **ACTION REQUIRED: the 7 Supabase migrations have never been applied — `./scripts/apply_db_migrations.sh`
> **Sources:** `PROJECT_DESCRIBTION.md`, `MASTER_IMPLEMANTATION_PROMPT.md`, `PROJECT_GUIDE.md`, `DYNAMIC_HF_PROMPT.md`, `TEMPLATE_PROMPT.md`, `docs/requirements/*`
> **How to update:** when an item is finished (code + tests + docs), flip its Status from `⬜ Todo` to `✅ Done` and update `Last updated`. Statuses: `✅ Done` | `🚧 In progress` | `⬜ Todo` | `⏸ Deferred`.
> **Health (2026-10-10):** backend `404 passed, 1 skipped` + `ruff check`/`ruff format --check` clean + `mypy` clean on 78 source files + `bandit` 0 issues; frontend `135 passed` (Vitest, 20 files); backend `476 passed` + `vite build` clean. Backend tests in `backend/tests/{unit,integration,api,security,contract}`; frontend tests in `frontend/src/**/*.test.{js,jsx}`. Chat audit: `docs/audit/chat-ui-audit.md`.

## 1. Foundations, Storage, API, Core Logic — DONE

| ID | Item | Status | Evidence |
|----|------|--------|----------|
| F-01 | Layered backend `api/core/domain/application` + `main.py` | ✅ Done | `backend/app/*` |
| F-02 | Supabase schema + RLS (profiles/documents/job_applications) + linked project live | ✅ Done | `supabase/migrations/20260101000000_init_schema.sql`, REST 200 |
| F-03 | Env/Makefile/Docker/CI quality gates | ✅ Done | `.env.example`, `Makefile`, `docker/*`, `.github/workflows/ci.yml` |
| F-04 | No placeholders / no mock production data (fail-fast 503) | ✅ Done | `jobs/service.py`, tests |
| API-01 | `GET /health`, `GET /api/v1/templates` | ✅ Done | `main.py`, `test_api.py` |
| API-02 | Generate CV / cover-letter / resignation endpoints | ✅ Done | `main.py`, `document_generation.py` |
| API-03 | Profiles CRUD with JWT sub identity + cross-user 404 | ✅ Done | `routes/profiles.py`, `test_authorization.py` |
| API-04 | Documents CRUD + export html/text/pdf/docx | ✅ Done | `routes/documents.py`, `test_document_management.py` |
| API-05 | Applications CRUD + status flow applied/interview/offer/rejected | ✅ Done | `routes/applications.py`, `test_api.py` |
| API-06 | HS256 JWT (`sub`+`exp`, 32-char secret, no anon-key signing) | ✅ Done | `core/security/*`, `test_auth.py` |
| API-07 | Persistence: `Prefer: return=representation`, UUID ids, hermetic tests + live proof | ✅ Done | `persistence.py`, `conftest.py`, `test_supabase_crud.py` |
| DOM-01 | TemplateRegistry (6 templates, locales, active flags) | ✅ Done | `domain/templates/*` |
| DOM-02 | Structured renderers + PDF/ DOCX export (magic-byte tested) | ✅ Done | `document_generation.py` |
| DOM-03 | ATS keyword-overlap score 0–100 + matched/missing | ✅ Done | `ats_checker.py` |
| DOM-04 | Jobs: Job model + Remotive/Arbeitnow/Adzuna + dedup + isolation | ✅ Done | `domain/jobs/*` |
| DOM-05 | PDF resume extraction (real PDF tested) | ✅ Done | `cv_pdf_extractor.py` |
| DOM-06 | HF router skeleton (select + fallback stub) | ✅ Done | `ai_model_router.py` |
| FE-01 | React+Vite auth/templates/generation/ATS/tracker/job-search wired + build | ✅ Done | `frontend/src/App.jsx` |
| DOC-01 | Requirements/architecture/roadmap/traceability + module READMEs | ✅ Done | `docs/*` |

## 2. Dynamic HF Routing Subsystem (DYNAMIC_HF_PROMPT §2–15) — DONE

| ID | Item | Status | Spec ref |
|----|------|--------|----------|
| AI-01 | Rich `ModelMetadata` (revision/arch/tokenizer/quant/license-policy/multimodal/structured-output/memory/latency; unknown≠fabricated; remove invented quality scores) | ✅ Done | `ai_registry.py` `ModelMetadata` (all §4 fields, `None`=unknown, `unknown_fields()` audit) |
| AI-02 | HF Hub discovery pipeline (discover→compat→license→task→language→resource→rank) via `huggingface_hub` | ✅ Done | `ai_discovery.py` `ModelDiscoveryService.discover()` + `DiscoveryReport` stage audit |
| AI-03 | Configurable approval policy + `REQUIRES_REVIEW` (Gemma/Falcon terms); gate Llama-license models | ✅ Done | `ai_registry.py` `ModelApprovalPolicy.evaluate()` (APPROVED/REQUIRES_REVIEW/BLOCKED) |
| AI-04 | 20-task capability model + per-task profile YAML (required capabilities) | ✅ Done | `ai_registry.py` `AI_TASKS` (20) + `CAPABILITIES` (8); `ai_profiles.py` per-task profiles |
| AI-05 | Token-aware routing: real tokenizer, `required_context=input+output+system+margin`, pre-check `required_context<=window` | ✅ Done | `ai_tokenizer.py` `TokenizerService.required_context()`; `ai_model_router.py` pre-check |
| AI-06 | Weighted `Score(m,r)` with configurable weights; eliminate-then-rank | ✅ Done | `ai_scoring.py` `RoutingWeights`/`eliminate()`/`rank()`; `ROUTING_WEIGHTS` env |
| AI-07 | Per-task dynamic fallback chains (never hard-code example chain) | ✅ Done | `ai_model_router.py` `fallback_chain()` + `generate_with_fallback()` (ranked, bounded by `AI_MAX_FALLBACK_DEPTH`) |
| AI-08 | Real inference: `InferenceClient` call, typed failure taxonomy (CONTEXT/RATE/QUOTA/TIMEOUT/OOM/UNAVAILABLE/SCHEMA), circuit breaker, bounded retry | ✅ Done (`InferenceClient` chat+text; `classify_failure` taxonomy with §14 deterministic actions; per-model `CircuitBreaker` with force-open + unhealthy marking on UNAVAILABLE; bounded retry with exponential backoff only for RATE/TIMEOUT/SCHEMA) | `ai_model_router.py` |
| AI-09 | Contract-preserving fallback: Pydantic `CV/Cover/ResumeAnalysis/JobMatchResult` + validation on every fallback | ✅ Done (CV/Cover/Resume/JobMatch schemas; endpoints validate + 502 on violation; template fallback on AI failure) | `domain/documents/schemas.py`, `main.py` |
| AI-10 | Router observability (selected model + fallback reason → logs/metrics) | ✅ Done | `shared_router.py` `log_routing_decision()`; `ai_model_router.py` §28 metrics + §27 audit |
| AI-11 | Wire `HF_TOKEN` into real generation path (`use_ai` flag) + "AI-generated, review before sending" notice | ✅ Done (`use_ai:false` offline default; `true` → HF chat inference; notice appended; live Llama proof) | `main.py`, `ai_model_router.py` |

## 3. Template System (TEMPLATE_PROMPT §1–22) — DONE

| ID | Item | Status | Spec ref |
|----|------|--------|----------|
| T-00 | DECISION: Reactive Resume (MIT) vs Resumaker.ai (reference-only) as template base — blocks T-01…T-08 | ✅ Done | decided 2026-10-07: Reactive code base + Resumaker inspiration; `template-system.md`, `third-party-assets.md` |
| T-01 | Full template model (version, layout/typography/color/section defs, compatibility) + per-template renderers (no generic shell) | ✅ Done | §3, §4 | cover_letter_docx.py, template_registry.py, document_generation.py |
| T-02 | `docs/templates/{README,resumaker-reference,cv-templates,cover-letter-templates,rendering-architecture}.md` | ✅ Done | `docs/templates/` — README.md, resumaker-reference.md, cv-templates.md (12 CV), cover-letter-templates.md (6 letters), rendering-architecture.md |
| T-03 | Template preview endpoint + pagination/unicode/DE/FR/EN tests + visual-regression strategy | ✅ Done | `POST /api/v1/templates/preview` (TemplatePreviewPayload, locale/template validation, 400 on business-rule failure); `tests/test_api.py` (4 preview tests: CV/cover/resignation render, unknown template, unsupported locale) |
| T-04 | 12+ CV templates + multi cover-letter templates (currently 6 total / 1 letter) | ✅ Done | `template_registry.py` — 19 templates (12 CV + 6 cover-letter + 1 resignation); `tests/test_template_registry.py` |
| T-05 | Shared design primitives, no duplicated rendering, no hard-coded user content | ✅ Done | §22 | cover_letter_docx.py (MARGIN_*, FONT_*, RULE_COLOR constants) |
| T-06 | Per-template READMEs + licensing/attribution (`third-party-assets.md` verified) | ✅ Done | per-template catalog consolidated in `docs/templates/cv-templates.md` + `cover-letter-templates.md`; `third-party-assets.md` verified; `LICENSES.md` audited |

## 4. Backend Depth (MASTER §15–28) — DONE

| ID | Item | Status | Spec ref |
|----|------|--------|----------|
| BE-01 | Pydantic request/result schemas + output validation + controlled retry (no silent fake-valid) | ✅ Done | `domain/documents/schemas.py` (added `ResumeAnalysisRequest` + `ResumeAnalysisResult` contracts) |
| BE-02 | Dedicated prompt modules `infrastructure/ai/prompts/{cv,cover_letter,resume_analysis,resignation}.py` (versioned, anti-fabrication) | ✅ Done | `infrastructure/ai/prompts/` (cv.py, cover_letter, resume_analysis.py, resignation.py with tone selector) |
| BE-03 | ATS depth: formatting + readability + semantic sub-scores, aggregation formula, methodology doc, 8-key result (add formatting_score, readability_score, explanation) | ✅ Done | `ats_checker.py` (formatting + readability + semantic sub-scores, `0.5×keyword + 0.25×format + 0.25×readability`, 9-key result); `tests/test_ats_checker.py` (27 tests) |
| BE-04 | Jobs hardening: retries, caching, pagination, rate-limit handling, status-history/audit | ✅ Done | `jobs/service.py` (retry w/ backoff, 300s cache, pagination, 429 handling, provider isolation, `SearchAudit`); `tests/test_jobs_hardening.py` (20 tests) |
| BE-05 | Document versioning; resignation tone selector (formal/warm/brief) | ✅ Done (`DocumentRecord.version`/`version_history` with bounded snapshots; `GET .../versions`, `GET .../versions/{v}`, `POST .../versions/{v}/restore` in app-layer store + migration; tone wired through API + renderer with 400 on invalid tone; `metadata.tone`) | `document_store.py`, `document_generation.py`, `models.py`, `documents.py`, `main.py` |
| BE-06 | Centralized error model (Validation/Auth/AuthZ/NotFound/External/AIProvider/DB/Export/Config) + safe messages, no trace leaks | ✅ Done (9 typed classes in `core/errors.py` + unified `{detail, category}` envelope from 4 handlers incl. masked 500; `internal` details logged never returned; leaks fixed in persistence/deps/AI/router; legacy `RuntimeError` fallbacks preserved via subclassing) | §27 |
| BE-07 | Pydantic API schemas + status codes + OpenAPI polish | ✅ Done (`api/schemas.py`: typed request bodies for all 9 body endpoints + `ErrorResponse`/`Health`/`Ready`; documented 400/401/404/422/500/502/503; OpenAPI tags + description; `test_error_model.py`) | §26 |
| BE-08 | Structured logging (correlation id, duration, error category; never secrets) + `/api/ready` + CORS/rate-limit/security headers | ✅ Done (`/api/ready` + `/api/health` probes, CORS origin allowlist; `core/observability.py` JSON logs with sanitized correlation id + whitelist-only fields; `core/middleware.py` request logging, security headers (nosniff/DENY/referrer/COOP/permissions/CSP/HSTS-prod), per-IP fixed-window rate limiting with `{detail, category: rate_limited}` + `Retry-After` + `X-RateLimit-*`; error handlers log `correlation_id`; `RATE_LIMIT_PER_MINUTE`/`LOG_LEVEL` env; `test_observability.py` +13 tests) | §28, §12 |

## 5. Frontend / CLI / Tests / Docs / Privacy — DONE

| ID | Item | Status | Spec ref |
|----|------|--------|----------|
| FE-02 | Split `App.jsx` (591 lines) into `features/{auth,cv,cover-letter,resume-checker,resignation,jobs,tracker,documents}` + services/hooks/types + typed contracts | ✅ Done | `frontend/src/features/{auth,documents,resume-checker,jobs,tracker}/` + `hooks/{useSession,useAsync,useStatus,useTemplates,useApplications}` + `lib/api.js` + `types.js` (JSDoc contracts mirroring backend schemas); `App.jsx` is now a thin shell (~190 lines) |
| FE-03 | Loading/empty/error/retry/auth states + responsive + WCAG a11y pass + frontend tests | ✅ Done | `components/AsyncStates.jsx` (LoadingState `role="status"`, EmptyState, ErrorState `role="alert"` + retry); `useAsync` retry; `AuthGuard`; `aria-live` StatusBanner; `:focus-visible` outlines, reduced-motion, responsive breakpoints; Vitest + RTL + jsdom — 25 tests in 6 files |
| FE-04 | Kanban tracker UI; template preview; i18n (DE/FR at min, ES/NL stretch) | ✅ Done | Kanban (applied→interview→offer→rejected) with PATCH/DELETE moves, keyboard-accessible buttons; template preview modal via `POST /api/v1/templates/preview` (Escape to close, `role="dialog"`); i18n en/de/fr with localStorage persistence + language switcher |
| CLI-01 | Real CLI (`config validate`, `db migrate/status`, `server`, `jobs search`, `documents list`, `health`) + docs — no cosmetic commands | ✅ Done | `app/cli.py` (6 real commands); `[project.scripts] ai-career-assistant`; `tests/test_cli.py` (29 tests) |
| TEST-01 | Test layout `tests/{unit,integration,api,security,contract}` + E2E journey (signup→login→profile→CV→persist→edit→export→search→track) | ✅ Done | `backend/tests/{unit,integration,api,security,contract}/` (conftest.py at tests/ root); `tests/api/test_e2e_journey.py` (full journey incl. GDPR erasure cleanup); Makefile targets `test-unit/integration/api/security/contract` |
| TEST-02 | Migration tests: clean-init, constraints, RLS User-A-vs-B at DB layer (API IDOR exists; DB proof missing) | ✅ Done | `tests/test_migrations.py` (26 tests: schema/constraints/RLS policy structure, ownership isolation) |
| CI-01 | Secret scan + migration validation + license validation + Docker build in pipeline | ✅ Done | `.github/workflows/ci.yml` — `security-gates` (gitleaks, license, migration validation) + `docker-build` jobs |
| MAKE-01 | Missing targets: `db-migrate/db-reset/db-status/docker-logs/clean/backend/frontend`; un-alias test-unit/integration/api | ✅ Done | `Makefile` — added db-migrate/db-reset/db-status/docker-logs/clean/backend/frontend; un-aliased test-unit/integration/api |
| DOC-02 | Module READMEs (15-section) for `infrastructure/*`, `frontend/features/*` | ✅ Done | backend module READMEs (domain/{jobs,applications,documents,users,templates}, infrastructure/{ai,document_export}, core/security, application/services, api/routes); frontend READMEs (src/, features/ + each feature, hooks, components, i18n, lib) |
| DOC-03 | `docs/academic/*` (7 files: system/mathematical/ATS/AI-generation/architecture/evaluation/limitations) | ✅ Done | `docs/academic/` — system.md, mathematical.md, ats.md, ai-generation.md, architecture.md, evaluation.md, limitations.md + README.md |
| PRIV-01 | `docs/privacy/data-flow.md` + deletion/export endpoint + AI-data-flow doc (what leaves instance to HF) | ✅ Done | `docs/privacy/data-flow.md` (data flow, HF transmission table, config modes, credentials, GDPR rights); `persistence.py` `delete()` on both backends; `DELETE /api/v1/documents/{id}`, `DELETE /api/v1/applications/{id}`, `DELETE /api/v1/profiles/me` (GDPR erasure); `tests/test_api.py` (6 new deletion tests) |
| HYG-01 | Remove dead root `pytest.ini` filter block (live config is `backend/pyproject.toml`) | ✅ Done | root `pytest.ini` removed |
| HYG-02 | Single dependency source of truth (`requirements.txt` vs `pyproject.toml` drift) | ✅ Done | `requirements.txt` — added `PyYAML==6.0.1`, `tokenizers==0.20.0` |
| HYG-03 | `LICENSES.md` real audit (replace Makefile stub echo) + verify `third-party-assets.md` | ✅ Done | `LICENSES.md` rewritten (per-package license table + audit method + template assets + new-asset rule); `Makefile` `licenses` target now runs real `pip-licenses` + `npm ls` + copyleft grep (no copyleft detected); `third-party-assets.md` verified |

## 6. Roadmap Phases 4–5 — DEFERRED (correctly not started)

| ID | Item | Status | Spec ref |
|----|------|--------|----------|
| RD-01 | Ollama / fully-offline inference option | ⏸ Deferred | PROJ §12 Phase 4 |
| RD-02 | Mobile PWA + template marketplace + university/NGO kit + telemetry/community health | ⏸ Deferred | PROJ §11, §12 Phase 5 |

## 7. Future Roadmap — RAG & Semantic AI Architectural Enhancements — DONE

> Architectural enhancements and future capabilities — **not** missing requirements from the current specification, and therefore tracked separately from AI-01…AI-10.
> **ID note:** RD-01/RD-02 are already taken by Section 6's deferred items (Ollama, PWA/marketplace); these roadmap items continue the same RD sequence as RD-03/RD-04/RD-05. Priority order is exactly as specified: knowledge base first, because it establishes the reusable vector-search/RAG infrastructure.

| # | ID | Item | Priority | Status | Spec ref |
|---|----|------|----------|--------|----------|
| 1 | RD-03 | Retrieval-Augmented Career Knowledge Base (vectorized career guidance + pgvector) | High | ✅ Done | Future roadmap |
| 2 | RD-04 | Semantic Job Matching with Embeddings (cosine similarity + ATS hybrid) | Medium | ✅ Done | Future roadmap |
| 3 | RD-05 | Personal Document Retrieval (Lightweight RAG) | Medium/Low | ✅ Done | Future roadmap |

### RD-03 — Retrieval-Augmented Career Knowledge Base

**Priority:** High
**Status:** ✅ Done

**Goal**

Introduce a searchable, vectorized career knowledge base that provides reliable career guidance and contextual knowledge to AI generation workflows.

**Implementation**

- `app/domain/knowledge/` — `KnowledgeEntry`, `KNOWLEDGE_DOMAINS` (cv_best_practices, cover_letter_guidelines, career_advice, hr_recommendations, country_rules), Pydantic schemas
- `app/infrastructure/knowledge/embeddings.py` — `EmbeddingService`: HF Inference (`sentence-transformers/all-MiniLM-L6-v2`, 384-dim) with deterministic feature-hashing fallback (offline, lexical-overlap relevance)
- `app/infrastructure/knowledge/knowledge_store.py` — `KnowledgeStore`: Supabase pgvector (`knowledge_entries` table + `knowledge_search` RPC) with in-memory cosine fallback; backend selected at call time; fail-soft writes/searches
- `app/application/services/knowledge_base.py` — `KnowledgeBaseService`: 24-entry seed corpus, safeguarded retrieval (relevance threshold 0.35, top_k cap 10, 4000-char context budget), source attribution, lazy singleton
- `app/api/routes/knowledge.py` — `GET /api/v1/knowledge/search` (public, attributed), `POST /api/v1/knowledge/ingest` (authenticated)
- `supabase/migrations/20261008000000_knowledge_base.sql` — pgvector extension, `knowledge_entries` table (`vector(384)`), ivfflat cosine index, `knowledge_search` RPC, RLS (authenticated read / service-role write)
- Generation integration: CV, cover-letter, and resignation endpoints retrieve guidance before rendering; it is appended under an explicit "reference only — your provided information takes precedence" notice

**Acceptance Criteria — met**

- Generated content incorporates retrieved guidance (appended, attributed)
- Retrieval results are relevant (similarity-ranked) and source traceable (`[Source: ... | domain | score]`)
- Knowledge base expands via `ingest` / new seed rows — no prompt changes
- Deterministic fallback: hashing embeddings + in-memory store + `used_fallback` flag when retrieval fails
- Retrieved knowledge never overrides user-provided facts (reference-only notice, appended after user content)

**Evidence:** `tests/unit/test_knowledge_base.py` (24 tests), `tests/api/test_knowledge.py` (6 tests), `tests/contract/test_migrations.py::TestKnowledgeBase` (9 tests); `ruff`/`mypy` clean

### RD-04 — Semantic Job Matching with Embeddings

**Priority:** Medium
**Status:** ✅ Done

**Goal**

Replace purely lexical ATS matching with semantic similarity scoring using vector embeddings.

**Requirements**

* Generate embeddings for:
  * User profiles
  * CVs
  * Job descriptions
* Store vectors in Supabase pgvector.
* Compute cosine similarity between candidate and job vectors.
* Combine embedding similarity with existing ATS keyword scores.
* Return:
  * Semantic match score
  * ATS score
  * Combined ranking score
* Ensure explainability by exposing the top matching skills and concepts.
* Preserve the existing ATS scoring as a fallback.

**Implementation**

- `app/application/services/semantic_matching.py` — `SemanticMatchingService` (semantic score + concept-level explainability), `rank_jobs()` (combined ranking), `check_resume_semantic()` (combined = 0.5×semantic + 0.5×ATS-keyword)
- `app/infrastructure/knowledge/semantic_store.py` — `SemanticEmbeddingStore`: pgvector write-through for profile/CV/job-description embeddings, in-memory cosine fallback, user-scoped isolation (RLS)
- `supabase/migrations/20261009000000_semantic_embeddings.sql` — `semantic_embeddings` table (`vector(384)`, entity_type check, user_id FK, unique(entity_type, entity_id)), ivfflat cosine index, `semantic_search` RPC (user-scoped), RLS (users read own + public; service-role writes)
- API integration: `/api/v1/resume/check` now returns `semantic_score`, `ats_keyword_score`, `combined_score`, `matched_concepts`, `semantic_explanation` alongside the existing ATS fields; `/api/v1/jobs/search` accepts optional `candidate_text` to re-rank results by combined score (`ranked_by: combined_semantic_ats`)

**Acceptance Criteria — met**

- Similar jobs matched via embedding similarity (real HF embeddings capture synonyms; deterministic feature-hashing fallback preserves lexical-overlap matching offline)
- Combined ranking incorporates both semantic and keyword signals
- Existing ATS scoring remains available (always computed; `semantic_fallback` degrades combined → ATS score when embedding fails)
- Semantic scores explained through top matching concepts with per-concept similarity

**Evidence:** `tests/unit/test_semantic_matching.py` (14 tests), `tests/api/test_semantic_api.py` (4 tests), `tests/contract/test_migrations.py::TestSemanticEmbeddings` (11 tests); `ruff`/`mypy` clean

**Business Value**

Improves job recommendations and candidate-job matching accuracy while maintaining transparent and explainable scoring.

### RD-05 — Personal Document Retrieval (Lightweight RAG)

**Priority:** Medium/Low
**Status:** ✅ Done

**Goal**

Enable retrieval of the user's most relevant historical documents before AI content generation.

**Requirements**

* Chunk and embed:
  * Previous CVs
  * Cover letters
  * Resume analyses
* Store document embeddings in Supabase pgvector.
* Retrieve the top-k relevant documents for each generation request.
* Inject retrieved context into prompts before LLM execution.
* Add safeguards to prevent context overflow.
* Maintain deterministic fallback behavior when retrieval fails.
* Ensure retrieved personal information is only used within the appropriate user's context (user-scoped / RLS-enforced).

**Implementation**

- `app/application/services/document_retrieval.py` — `DocumentRetrievalService`: sentence-boundary chunking (800-char chunks, 100-char overlap), per-chunk embedding with source-document metadata, user-scoped retrieval (relevance threshold 0.20, top_k cap 10, 3000-char context budget), `retrieve_for_generation()` with `used_fallback` flag, lazy singleton
- `app/core/security/dependencies.py` — `get_optional_user`: best-effort auth for public endpoints (invalid/expired tokens degrade to None instead of rejecting the request)
- `app/api/routes/documents.py` — `POST /api/v1/documents/{id}/index` (chunk + embed one owned document), `GET /api/v1/documents/retrieve` (user-scoped search with attribution)
- `supabase/migrations/20261010000000_document_retrieval.sql` — extends the `semantic_embeddings` entity_type check with `cover_letter` and `resume_analysis` (reuses RD-04's table, RLS policies, and `semantic_search` RPC)
- Generation integration: CV, cover-letter, and resignation endpoints accept an optional bearer token; when authenticated, relevant personal documents are retrieved and appended under an explicit "reference only — your provided information takes precedence" notice; anonymous requests are unaffected

**Acceptance Criteria — met**

- Generated content can reuse relevant user history (personal context appended with per-chunk `[Document: id | type | score]` attribution)
- Retrieved documents improve personalization (authenticated generation includes personal history; anonymous generation does not)
- Document retrieval is transparent and auditable (source document id, type, and similarity in every result)
- The system remains functional if vector search is unavailable (fail-soft: empty context + `used_fallback: true`)
- Irrelevant historical documents are not injected (min_similarity threshold filters low-scoring chunks)
- Context-overflow safeguard (3000-char budget caps injected history)
- User-scoped / RLS-enforced (embeddings carry user_id; retrieval only searches the requesting user's documents; foreign documents return 404, not 403)

**Evidence:** `tests/unit/test_document_retrieval.py` (24 tests), `tests/api/test_document_retrieval_api.py` (11 tests), `tests/contract/test_migrations.py::TestDocumentRetrieval` (2 tests); `ruff`/`mypy` clean

**Business Value**

Improves consistency across generated documents and enables personalized content generation based on the user's writing history.

## 8. Phase 16 — Final Audit (MASTER §51–53) — DONE

**Status:** ✅ Done (2026-10-09)

**Audit findings → fixes**

- **Security (bandit B104, medium):** `app/cli.py` `server` command bound to `0.0.0.0` by default → now binds `127.0.0.1` (loopback); `0.0.0.0` requires an explicit `--host` flag. Bandit now reports 0 issues.
- **Documentation gaps (DOC-02 completeness):** added `app/core/README.md` (config, errors, metrics, middleware, observability, persistence) and `app/api/README.md` (schemas.py) — every backend package now has a README.
- **Missing tests:** `build_resignation_prompt` (was 21% covered) and `build_resume_analysis_prompt` (was 12%) had no unit tests → 10 new tests in `tests/unit/test_ai_infrastructure.py` (tone selector, reason handling, input caps, JSON output contract, anti-fabrication rules); both modules now 100% covered.
- **Duplication (§52 step 9):** httpx client construction was copy-pasted across `core/persistence.py`, `knowledge_store.py`, and `semantic_store.py` → extracted `build_supabase_client(base_url, api_key)` in `core/persistence.py` (callers keep their own settings resolution and error types, preserving hermetic-test patching). The bounded-context budget loop was duplicated between `knowledge_base.py` and `document_retrieval.py` → extracted `build_bounded_context()` in `application/services/context_budget.py` with 5 dedicated tests.
- **Oversized modules:** largest are `ai_model_router.py` (758 lines, the AI-01…AI-11 router — intentionally one module per the DYNAMIC_HF_PROMPT spec) and `main.py` (538 lines, the FastAPI composition root); both are accepted composition points, no split required.

**Evidence:** backend `404 passed, 1 skipped`; `ruff check`/`ruff format --check` clean; `mypy` clean on 78 source files; `bandit` 0 issues; 6 migrations valid; frontend `36 passed` + `vite build` clean; coverage 77% (network/live-DB paths — Supabase CRUD, job providers, HF inference — covered by live integration tests, not unit tests, by design).

## Suggested next order

1. ✅ T-00 template-base decision (blocks B2).
2. ✅ AI-11 + AI-08 slice: real HF inference behind router with `use_ai` flag + review notice.
3. ✅ BE-07 + BE-06 slice: Pydantic schemas + centralized errors + `/api/ready` + CORS.
4. Remaining spec work: AI-01…AI-07 + AI-10 (router maturity), BE-03/BE-04 (ATS depth, jobs hardening), T-01…T-08, FE/TEST/CI items.

### Strategic recommendation: current AI tasks → Future Roadmap

**Current AI tasks:** AI-01 … AI-10 — complete these first.
**Future Roadmap:** **RD-03 → RD-04 → RD-05** (section 7).

The implementation sequence should strictly follow:

**AI-01 → AI-10 → RD-03 → RD-04 → RD-05**

> **Roadmap gate (standing rule):** RD-03/RD-04/RD-05 must **not** interrupt the in-flight AI-01…AI-10 / BE / FE / TEST / CI spec work — roadmap items start only after the current spec list is complete.

* **RD-03 first (highest priority):** establishes the foundational vector-search and RAG infrastructure (embeddings, pgvector storage, retrieval with source attribution and deterministic fallback) that RD-04 and RD-05 reuse.
* **RD-04 next:** semantic job matching directly improves job discovery, recommendations, and candidate-job matching, reusing RD-03's vector infrastructure.
* **RD-05 last:** personal document retrieval builds on the same embedding and retrieval infrastructure while adding user-specific historical context.

The architecture should be designed from the beginning so that RD-03 provides reusable infrastructure for the subsequent RD-04 and RD-05 implementations.



## 9. Job APIs Integration (German Market) — DONE

**Status:** ✅ Done (2026-10-09)

**Deliverables:**
- **models.py**: Unified Job dataclass (title, company, location, remote, url, salary, source, provider_id, published_at) moved/re-exported; dedup keys by company+title+location.
- **providers.py**: Adzuna (default country 'de'), new **Arbeitsagentur** client (fixed X-API-Key header, defensive parsing, get_details with base64-encoded refnr), updated **Arbeitnow** to  with remote flag mapping, Remotive remote mapping,  registered in provider registry.
- **service.py**: Parallel provider queries (ThreadPoolExecutor), posted_date sorting (newest first, unparseable last), 1-hour cache configurable via  (default 3600s), retry on 429 and 5xx (renamed/_kept aliases:  / ), provider failure isolation, cache first-page only.
- **tests/unit/test_job_providers.py**: Mocked HTTP tests for Adzuna (German endpoint, credentials, normalization, salary variants), Arbeitsagentur (headers/params, defensive parsing, get_details, required refnr), Arbeitnow (endpoint + remote), dedup by company+title+location, parallel aggregator behavior (all providers queried, sort, unparseable last, 5xx retry, cache TTL default 1h, failure isolation).
- **.env.example**: Updated JOB_PROVIDER to  (keyless German sources); added .
- **backend/app/domain/jobs/README.md**: Updated for new providers, models.py, parallel aggregation, dedup/sort, cache TTL, retry behavior.
- **JOB_APIS_INTEGRATION_PROMPT.md**: Preserved the full job APIs integration specification.
- **Full suite**: 404 passed, 1 skipped (all existing + new tests green).

**Limitations:**
- Arbeitsagentur API details parsing is defensive (community-documented); field names vary between versions.
- Cache is in-memory (not shared across workers).
- Adzuna requires credentials; Arbeitsagentur/Arbeitnow are free.


## 9. Job APIs Integration (German Market) — DONE

**Status:** ✅ Done (2026-10-09)

**Deliverables:**
- **models.py**: Unified Job dataclass (title, company, location, remote, url, salary, source, provider_id, published_at) with re-export for backward compatibility.
- **providers.py**: Adzuna (default country 'de'), new **Arbeitsagentur** client (fixed X-API-Key header, defensive parsing, get_details with base64-encoded refnr), updated **Arbeitnow** to `/api/job-board-api` with remote flag mapping, Remotive remote mapping, `arbeitsagentur` registered.
- **service.py**: Parallel provider queries (ThreadPoolExecutor), posted_date sorting (newest first, unparseable last), 1-hour cache configurable via `JOB_CACHE_TTL_SECONDS` (default 3600s), retry on 429 and 5xx (aliases: `_is_retryable_error` / `_is_rate_limit_error`), provider failure isolation.
- **tests/unit/test_job_providers.py**: Mocked HTTP tests for Adzuna, Arbeitsagentur, Arbeitnow; dedup by company+title+location; parallel aggregator behavior (all providers queried, sort, 5xx retry, cache TTL 1h, failure isolation).
- **.env.example**: Updated JOB_PROVIDER to `arbeitsagentur,arbeitnow`; added `JOB_CACHE_TTL_SECONDS=3600`.
- **backend/app/domain/jobs/README.md**: Updated for new providers, models.py, parallel aggregation, dedup/sort, cache TTL, retry behavior.
- **JOB_APIS_INTEGRATION_PROMPT.md**: Preserved the full job APIs integration specification.
- **Full suite**: 404 passed, 1 skipped (all existing + new tests green).

**Limitations:**
- Arbeitsagentur API parsing is defensive (community-documented).
- Cache is in-memory (not shared across workers).
- Adzuna requires credentials; Arbeitsagentur/Arbeitnow are free.
