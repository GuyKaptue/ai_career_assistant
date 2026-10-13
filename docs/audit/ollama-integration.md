# Ollama integration — audit and implementation record

Date: 2026-10-13. Scope: the local-first inference chain (RD-01) and the
documentation/diagram pass that accompanied it (Sub-step 8a/8b).

## What changed

| Area | Change |
|------|--------|
| Backend | `OllamaInferenceAdapter` (sync httpx client, bounded retries, tag-aware model probe); `OllamaFirstAdapter` (local-first wrapper, circuit breaker, pinned-model handling); `get_ollama_status()` shared status probe with a 5 s TTL cache |
| API | `GET /api/ready` reports an informational `checks["ollama"]` block; the 200/503 verdict is unchanged and independent of Ollama |
| Compose | `ollama` service (`ollama/ollama:0.40.3`, `ollama_data` volume, `127.0.0.1:11434` only, healthcheck `ollama list`); `ollama-pull` one-shot (`restart: "no"`, `depends_on: ollama: condition: service_healthy`); `docker-compose.gpu.yml` opt-in override |
| Makefile | `ollama-up`, `ollama-pull`, `ollama-logs`, `ollama-gpu-up` |
| CLI | `models list` gains an `Ollama:` section; `ai test --live` reports `provider`, `model_id`, `latency_ms`, `fallback_chain`, `fallback_reason` and the typed failure class |
| Metrics | `ollama_requests_total`, `ollama_success_total`, `ollama_failed_total`, `ollama_fallback_total` |
| Docs | `docs/deployment/ollama.md` (new); `README.md`, `docs/privacy/data-flow.md`, `docs/academic/{ai-generation,system,limitations}.md`, `docs/deployment/overview.md`, `docs/security/overview.md`, `backend/app/infrastructure/ai/README.md`, `TODO.md` |
| Diagrams | `docs/diagrams/{ai_routing_architecture,deployment_architecture}.dot` updated and re-rendered with `dot -Tpng -Gdpi=110` (Graphviz 14.0.5) |
| Tests | 114 tests across `tests/api/test_ready_ollama.py`, `tests/api/test_generation_ollama_chain.py`, `tests/contract/test_ollama_contracts.py`, `tests/unit/test_cli_ollama.py`; earlier stages added the adapter, wrapper, probe, shared-router and compose contract tests |

## Verification

- `pytest` — 1091 passed, 1 skipped (tesseract), in the 4-run matrix
  `{default, USE_OLLAMA=false}` × `{Ollama up, stopped}`
- `ruff check`, `ruff format --check`, `mypy` — clean
- `docker compose up -d --wait ollama`, `make ollama-pull`,
  `docker compose up -d backend`, `curl localhost:8000/api/ready`,
  `ai test --live` — all executed against the real stack in Sub-step 6
- Mutation sanity checks (manual, restored byte-identical):
  readiness gated on Ollama, printed generation content, a Cline reference, a
  removed template fallback, and a logged prompt each failed at least one test

## Not verified here

- GPU acceleration — no NVIDIA GPU on the development or CI host. The
  override file is documented, not executed.
- The Ollama model library sizes for `mistral:7b` and `qwen3:8b` are stated as
  approximations sourced from the registry; only `llama3.2:3b` (2,019,393,189
  bytes) was measured in this repository.

## Documentation audit (Sub-step 8a)

10 documents needed change, all traced to RD-01. 72 Markdown files and 26
images inventoried; 2 images were stale (`ai_routing_architecture.png`,
`deployment_architecture.png`) and both have editable `.dot` sources, so no
image required manual regeneration. `docs/legal/**` was inspected for data-flow
and processor statements and contains none, so it was left untouched.

## Pre-existing drift (reported, not fixed)

Out of scope for RD-01, left for an explicit decision. Each entry is drift
unrelated to Ollama found while auditing:

| File | Observation |
|------|-------------|
| `docs/academic/limitations.md` | §1.1 still describes inference as requiring `HF_TOKEN`/network at the top level; the §3 table entry for RD-01 was corrected, the prose was not restructured |
| `docs/privacy/data-flow.md` | Mentions `core/observability.py`, a module that does not exist under that name (privacy/logging code lives in the API and middleware layers) |
| `backend/app/infrastructure/ai/README.md` | References `tests/test_api.py`, a path that no longer matches the current `tests/api/` layout |
| `docs/deployment/overview.md` | No env-variable table and no port inventory besides the new service table |
| `README.md` | Tech stack lists the AI layer as Hugging Face only (`AI/ML` row); updated in the prose and env table but not that row |
