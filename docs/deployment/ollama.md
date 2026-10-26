# Ollama — Local Inference

The backend prefers a **local** Ollama server for every AI generation call and
falls back to Hugging Face Inference, then to a deterministic template. This
document covers how to run, verify and troubleshoot that chain.

## Why local inference

- **No billing and no API key.** Ollama serves model weights from your own
  disk. `HF_TOKEN` stays optional and is only consulted on the fallback path.
- **Offline capable.** With `OLLAMA_MODEL` already pulled, CV, cover-letter and
  chat generation work without internet access.
- **Privacy — accurate statement.** The prompt stays on the host and inside the
  compose network **only while Ollama answers**. If Ollama is disabled,
  unreachable, missing the model, or its circuit breaker is open, the same
  prompt is sent to the Hugging Face Inference API exactly as it is today.
  The model download itself (`make ollama-pull`) fetches model files from the
  Ollama registry and transmits no user data, prompts, CVs or job text.

## Inference chain

```
   ┌──────────────┐   1. preferred    ┌─────────────────────┐
   │ Generation   ├──────────────────►│ Ollama (local)      │
   │ request      │                   │ http://ollama:11434 │
   └──────┬───────┘                   └──────────┬──────────┘
          │                                     │
          │ 2. pinned non-Ollama                │ unreachable · model
          │    model skips Ollama               │ missing · 429 · 5xx
          │                                     ▼
          │                            ┌─────────────────────┐
          └───────────────────────────►│ Hugging Face         │
                                       │ Inference API        │
                                       └──────────┬──────────┘
                                                  │
                                                  │ unavailable · schema
                                                  │ violation · quota
                                                  ▼
                                       ┌─────────────────────┐
                                       │ Deterministic       │
                                       │ template fallback   │
                                       └─────────────────────┘
```

**Circuit breaker (per process, around the Ollama channel).**
3 consecutive *availability* failures (model unavailable, timeout, rate limit)
open the breaker for 30 s. While open, calls skip Ollama entirely and go
straight to the fallback, so a dead local server adds no latency to every
request. After 30 s exactly **one** probe request is allowed through: success
returns to normal, failure re-opens the breaker for another 30 s. A schema
failure does **not** open the breaker — that is a request the server answered.

**A pinned non-Ollama model skips Ollama.** Passing `model_id` with a
Hugging Face id (or `USE_OLLAMA=false`) means Ollama is never contacted.

## Quick start

```bash
# 1. Configure the local variables (see the table below).
cp .env.example .env

# 2. Start Ollama and wait until it reports healthy (pins ollama/ollama:0.40.3).
make ollama-up

# 3. Pull the model the backend will ask for (one-shot, fails loudly).
make ollama-pull

# 4. Start the backend.
docker compose up -d backend

# 5. Readiness probe never depends on Ollama; the block is informational.
curl -s localhost:8000/api/ready

# 6. Prove the whole chain end-to-end, showing provider, model and latency.
backend/.venv/bin/python -m app.cli ai test --task career_advice --live --json
```

The CLI is invoked as a module in this repo (`python -m app.cli_ai` when run
from `backend/`, or `backend/.venv/bin/python -m app.cli` from the project
root). Both forms produce identical output.

### Verifying Ollama answers

```
$ curl -s localhost:11434/api/tags
{"models":[{"name":"llama3.2:3b","size":2019393189,"parameter_size":"3.2B",
"quantization_level":"Q4_K_M","context_length":131072}]}
```

## Model choices

Defaults and alternatives verified from the Ollama model library and from
`ollama list` in this repository. Download sizes are what the registry reports
for the current tag and can change when the model owner republishes.

| Model | Download size | Context window | RAM / VRAM guidance | Notes |
|---|---|---|---|---|
| `llama3.2:3b` (default) | 2.02 GB (2,019,393,189 bytes, measured in this repo) | 131,072 tokens | ~4 GB RAM; GPU optional | Cheapest model that still follows the career prompts well |
| `mistral:7b` | ~4.1 GB | 32,768 tokens | ~8 GB RAM, or ≥6 GB VRAM | Better multilingual answer quality, still single-GPU |
| `qwen3:8b` | ~5.1 GB | 32,768 tokens | ~10 GB RAM, or ≥8 GB VRAM | Strong multilingual, best of the three for DE/FR |

RAM/VRAM figures are approximations derived from the quantised weight sizes
above (roughly 1.3-1.5× the file size for runtime overhead); they come from the
weight sizes, not from benchmarking on this host.

## Environment variables

All defaults are read from `backend/app/core/config.py` and
`docker-compose.yml` — both are enforced by
`tests/contract/test_ollama_docs.py`, so this table cannot silently drift.

| Variable | Default | Meaning | Valid range | Read by |
|---|---|---|---|---|
| `USE_OLLAMA` | `true` | Master switch. `false` makes the backend behave as before this change. | `true`, `false` | backend |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Where Ollama runs. **Compose overrides this to `http://ollama:11434`** because inside the container network `localhost` is the backend itself. | `http`/`https` URL, no credentials | backend |
| `OLLAMA_MODEL` | `llama3.2:3b` | Model Ollama must have pulled; the same variable drives the pull one-shot. | any Ollama tag | backend + compose |
| `OLLAMA_TIMEOUT_SECONDS` | `120` | Whole-request read timeout. | `> 0` | backend |
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | `3` | Connect timeout, also the whole-request budget for the readiness probe. | `> 0` | backend |
| `OLLAMA_KEEP_ALIVE` | `5m` | How long Ollama keeps the model in memory after a call. | Ollama duration string | backend |
| `OLLAMA_TEMPERATURE` | `0.3` | Sampling temperature for career tasks. | `0.0` – `2.0` | backend |
| `OLLAMA_NUM_CTX` | `8192` | Context window (tokens) requested per call. Clamped once at startup against the real context length the model reports via `/api/show` (the configured value is the ceiling; a failed lookup keeps it unchanged). | integer ≥ `512` | backend |
| `OLLAMA_IMAGE_TAG` | `0.40.3` | Pinned image tag. Never `latest`: a silent image bump must not change behaviour. | pinned semver | compose |

## GPU

Ollama uses the GPU automatically when the container runtime exposes one.
Enable it with the NVIDIA override file, which adds a device reservation to
the `ollama` service only:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --wait ollama
```

Host requirement: the **NVIDIA Container Toolkit**
(https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html).
Verify with `docker run --rm --gpus all ollama/ollama nvidia-smi`.

> **NOT RUN here.** This repository's CI and development host have no NVIDIA
> GPU, so the GPU path is documented, not verified. Everything else in this
> document was executed and its output is shown.

## Security

Ollama ships **no authentication and no TLS**. The compose file therefore binds
it to `127.0.0.1` only:

```yaml
ports:
  - "127.0.0.1:11434:11434"   # loopback only; never 0.0.0.0
```

Binding `0.0.0.0` would expose an unauthenticated local LLM to anyone who can
reach the host. If remote access is genuinely required, do **not** publish
`11434` directly — put a reverse proxy in front that terminates TLS and
enforces authentication (or keep Ollama on a private network that only the
backend can reach). Other containers reach Ollama over the compose network,
which is not affected by the host-side binding.

## Observability

### `/api/ready` — informational only

The `ollama` block reports the local channel and **never changes the 200/503
decision**. That verdict is decided by the config and database checks alone, so
a broken Ollama leaves the service "ready" and the app keeps serving through
the fallback chain. The probe is cached for 5 s (monotonic clock, thread-safe)
so health-check traffic does not hammer Ollama.

```json
{
  "status": "ready",
  "checks": {
    "ollama": {
      "enabled": true,
      "reachable": true,
      "model": "llama3.2:3b",
      "model_installed": true,
      "circuit": "closed",
      "latency_ms": 3
    }
  }
}
```

| Field | Meaning |
|---|---|
| `enabled` | `false` → `USE_OLLAMA=false`; every other field is then `null` and no request is made |
| `reachable` | `true` if `/api/tags` answered inside the connect-timeout budget; `null` when nothing could be determined |
| `model` | The configured model name |
| `model_installed` | `true`/`false` once the tag list is known; `null` while unknown. Tag aliases count (`llama3.2` ≡ `llama3.2:latest`) but a different tag does not |
| `circuit` | `closed` · `open` · `half_open`. `null` only when `enabled=false`. Never flip-breaker: the probe reads state |
| `latency_ms` | Round-trip time of the probe, `null` when unreachable |

### Metrics

Counters live in the default `/metrics` registry and are process-local.

| Counter | Meaning |
|---|---|
| `ollama_requests_total` | One per Ollama `chat()` call the breaker allowed through — every real generation attempt, including retries inside a single call. |
| `ollama_success_total` | Calls where Ollama answered the turn. |
| `ollama_failed_total` | Calls where Ollama was actually contacted and failed. This counter also counts the resulting fallback to Hugging Face. |
| `ollama_fallback_total` | Every turn that ended up on Hugging Face: a **breaker skip** and **any failed Ollama call**. Both paths append to it. |

`ollama_fallback_total` covers both causes — a breaker skip (the breaker was
open, so Ollama was never contacted) and a fallback after a failed Ollama call
(also counted by `ollama_failed_total`). A breaker skip leaves
`ollama_requests_total` unchanged, which is how the two are told apart.

### What is logged

Routing decisions (`log_routing_decision`), the selected model, the fallback
reason, latency and token counts. **Never** prompts, generated content, the
base URL or credentials. This is enforced by a static AST test and by
`caplog` assertions — see
`backend/tests/contract/test_ollama_contracts.py::TestPrivacyGuard`.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/api/ready` shows `reachable=false` | Ollama not running, or the backend cannot reach it | `make ollama-up`; in compose check `OLLAMA_BASE_URL=http://ollama:11434`, not `localhost` |
| `reachable=false` and `circuit="open"` | Three availability failures opened the breaker | Wait 30 s; the next request is a single probe. Confirm state in `/api/ready` |
| `model_installed=false` | The configured model is not pulled | `make ollama-pull` (or `ollama pull <model>` inside the container) |
| `AIProviderError`: "model 'X' is not installed; run \`ollama pull X\`" | 404 from Ollama for an unpulled model | Run the `ollama pull X` command the message names |
| `make ollama-pull` exits 1 | Bad model name, or no internet access | Check the pull output in `make ollama-logs`; verify the name on the Ollama model library |
| `ollama-pull` shows `Exited (1)` in `docker compose ps -a` | The one-shot recorded a failure | Read its logs: `docker compose logs ollama-pull` |
| First request after an idle period is very slow | Ollama is loading the weights | Raise `OLLAMA_KEEP_ALIVE` (e.g. `30m`), or accept the one-off cost |
| Read timeout on a slow CPU | The model needs longer than `OLLAMA_TIMEOUT_SECONDS` | Raise the timeout, or use a smaller model (`llama3.2:3b`) |
| Long prompts come back truncated | `num_ctx` is set to the request's `token_budget` | Lower the task budget, or use a model with a larger context window |
| Every request is slow even though `/api/ready` is healthy | The breaker is half-open, so each call probes first | `curl -s localhost:8000/api/ready` and read `circuit` |

## Cline

Cline is a **development-time CLI tool only**. Its free models are not
available through a public API, so the backend never calls it and contains no
Cline code. This is enforced by
`backend/tests/contract/test_ollama_contracts.py::TestNoCline`, which fails the
build if any file under `backend/app` mentions `api.cline.bot` or imports a
`cline` package.

## Roadmap

Not implemented in this repository yet (tracked as RD-06 … RD-09 in
`TODO.md`; RD-01 local inference itself is Done):

- **RD-06** — UI model picker so users can override the auto choice.
- **RD-07** — GPU acceleration verified on real hardware (see GPU above).
- **RD-08** — per-user quotas and rate limits on generation.
- **RD-09** — prompt caching for repeated analysis tasks.

## See also

- [`docs/deployment/overview.md`](overview.md) — the whole compose stack
- [`docs/privacy/data-flow.md`](../../docs/privacy/data-flow.md) — what leaves the host
- [`docs/ai/model-catalog.md`](../../docs/ai/model-catalog.md) — Hugging Face candidate pool and licences
