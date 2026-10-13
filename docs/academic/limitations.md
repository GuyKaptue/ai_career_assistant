# Known limitations

This document records the known limitations, assumptions, and deferred
roadmap items. It is auditable: every limitation is traceable to a
decision or a documented gap.

## 1. Assumptions

1. The user provides truthful resume and job-description text. The
   system does not verify facts.
2. The Hugging Face Inference API is reachable when `use_ai=true`.
3. Supabase is configured for production (self-hosted or managed).
4. Job providers are free public APIs; availability is not guaranteed.

## 2. Known limitations

### 2.1 AI subsystem

- **No empirical quality benchmarks.** `quality_score` is `None` for all
  models; routing does not use an invented score (§11).
- **Context windows are unknown** for discovered models. Fit is not
  verifiable when `context_window` is `None`; the model is not
  eliminated for this reason.
- **Dynamic discovery requires network access** and `HF_TOKEN`. It is
  disabled when `AI_ENABLE_DISCOVERY` is false.
- **Circuit breakers are per-process.** Model health does not survive
  a restart.

### 2.2 ATS scoring

- **Lexical matching only.** Synonyms and semantic similarity are not
  matched (future RD-04).
- **English-centric.** Formatting and readability heuristics assume
  English text.
- **Not a hiring prediction.** The score is a heuristic estimate.

### 2.3 Jobs

- **In-memory cache** is not shared across workers.
- **Adzuna requires credentials.** Remotive and Arbeitnow are free.
- **Provider failures are isolated** but the search may return fewer
  results.

### 2.4 Persistence

- **Supabase REST only.** No native PostgreSQL driver.
- **Fallback to in-memory** when the table is missing (hermetic tests);
  this is not a production configuration.

### 2.5 Frontend

- **Single-page application** (one `App.jsx`). Feature splitting is a
  tracked item (FE-02).
- **No browser E2E tests** in this environment.

## 3. Deferred roadmap

| ID | Item | Status |
|----|------|--------|
| RD-01 | ~~Ollama / fully-offline inference~~ **Done** — local Ollama channel implemented (see `docs/deployment/ollama.md`) | Done |
| RD-02 | Mobile PWA + template marketplace | Deferred |
| RD-03 | RAG career knowledge base (pgvector) | Future roadmap |
| RD-04 | Semantic job matching with embeddings | Future roadmap |
| RD-05 | Personal document retrieval (Lightweight RAG) | Future roadmap |

Roadmap gate: RD-03/RD-04/RD-05 must not interrupt the current spec
work. They start only after the current spec list is complete.

## 4. Security limitations

- **No rate limiting on the Hugging Face API** itself; the circuit
  breaker and bounded retry protect the app, not the provider.
- **JWT secret must be ≥ 32 bytes.** Shorter secrets raise
  `InsecureKeyLengthWarning` and are rejected at runtime.
- **No hardware security module.** Secrets are environment variables.

## 5. Privacy limitations

- **Online mode sends the prompt to Hugging Face.** See
  `docs/privacy/data-flow.md` for what leaves the instance and when.
- **No dedicated "export all my data" endpoint.** Users can export
  individual documents; a bulk-export endpoint is a future enhancement.
- **Profile deletion is app-layer only.** The Supabase Auth account is
  managed by the Auth service.

## Related documents

- [system.md](system.md)
- [evaluation.md](evaluation.md)
- [../privacy/data-flow.md](../privacy/data-flow.md)