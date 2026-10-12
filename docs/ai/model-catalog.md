# Model catalog — verified via the Hugging Face API

# Model catalog — verified against the live Hugging Face API

The routing candidate pool lives in `backend/app/application/services/model_catalog.py`.
Two things were verified per model **before** registering it, both against the real API and with a
real token:

1. `GET https://huggingface.co/api/models/<model_id>` — availability, and the license in the
   model card's `cardData`.
2. `POST https://router.huggingface.co/v1/chat/completions` — whether the Inference Providers
   chat router can actually serve a chat turn for the model.

Nothing below is assumed, and the second check changed the pool materially: **five of the ten models
are not chat-capable** through the provider. See [Chat-capability](#chat-capability-the-check-that-changed-the-pool).

The routing candidate pool lives in `backend/app/application/services/model_catalog.py`.
Every entry below was checked against `https://huggingface.co/api/models/<model_id>` before being
registered: availability, the license in the model card's `cardData`, and whether the repo is gated.
No value below is assumed.

## Licensing summary

| Model | License (HF card) | Hub | Chat-capable | Policy status |
|---|---|---|---|---|
| `meta-llama/Llama-3.3-70B-Instruct` | `llama3.3` | 200 | **yes** | REQUIRES_REVIEW |
| `Qwen/Qwen2.5-72B-Instruct` | `qwen` (`other`+`license_name`) | 200 | **yes** | REQUIRES_REVIEW |
| `google/gemma-3-27b-it` | `gemma` | 200 | **yes** | REQUIRES_REVIEW |
| `microsoft/phi-4` | `mit` | 200 (→ `phi-4`) | **yes** | APPROVED |
| `deepseek-ai/DeepSeek-R1` | `mit` | 200 | **yes** | APPROVED |
| `mistralai/Mistral-Small-3.1-24B-Instruct-2503` | `apache-2.0` | 200 | no — "not a chat model" | APPROVED |
| `mistralai/Mixtral-8x7B-Instruct-v0.1` | `apache-2.0` | 200 | no — "not a chat model" | APPROVED |
| `HuggingFaceH4/zephyr-7b-beta` | `mit` | 200 | no — "model_not_supported" | APPROVED |
| `openchat/openchat_3.5` | `apache-2.0` | 200 | no — "model_not_supported" | APPROVED |
| `teknium/OpenHermes-2.5-Mistral-7B` | `apache-2.0` | 200 | no — "model_not_supported" | APPROVED |

**Net effect:** exactly two models are both chat-capable and licence-eligible — `deepseek-ai/DeepSeek-R1`
and `microsoft/phi-4`. The other three chat-capable models are licence-gated. All 20 routing tasks
resolve to one of them; unblocking a gated one with `AI_APPROVED_MODEL_IDS` immediately widens the
pool.

## Chat-capability (the check that changed the pool)

`POST /v1/chat/completions` answers the validation question **before** spending anything, so the
verdict is exact and was recorded per model in `CHAT_ROUTER_VERIFIED`:

* a `402 "You have no remaining credits"` reply means the model *is* a valid chat model — only the
  account is out of credits;
* `"The requested model ... is not a chat model"` means the Hub repo exists but the router refuses
  its architecture (both Mistral entries);
* `model_not_supported` means the router rejects the model outright (zephyr, openchat, OpenHermes).

`ModelMetadata.inference_provider_supported` carries this flag, and `ai_scoring.eliminate()` now
excludes models whose flag is `False` with the reason `not_supported_by_provider` — so
auto-selection can never pick a model that can only fail, while the models stay registered (and
listed, with `chat_compatible: false`) so an operator can still see and enable them.

> The HF account currently has **no remaining credits**, so even the chat-capable models return 402.
> The app degrades correctly to a labelled deterministic reply in that case; that is an account
> issue, not a code one.

The three REQUIRES_REVIEW licences carry additional terms (Llama community licence, the Qwen
licence, Gemma terms). They are registered so the picker can display them and an operator can
approve them, but the router never auto-selects them. Configure
`AI_APPROVED_MODEL_IDS=meta-llama/Llama-3.3-70B-Instruct` to unblock one.

## Substitutions (verified, not assumed)

Two requested ids do not exist: the API returns **404** for them, and the substitution is recorded in
`SUBSTITUTIONS` so it stays auditable rather than silent.

| Requested | HTTP | Registered instead | HTTP |
|---|---|---|---|
| `mistralai/Mistral-Small-3.1-24B-Instruct` | 404 | `mistralai/Mistral-Small-3.1-24B-Instruct-2503` | 200 |
| `openchat/openchat-3.5-7b` | 404 | `openchat/openchat_3.5` | 200 |

`microsoft/Phi-4` 307-redirects to the canonical lowercase `microsoft/phi-4`, which is what is
registered.

## Auto-selection by task

`GET /api/v1/models?task=<task>` ranks the pool for that task and returns
`auto_default_model` — the model the router picks when the user leaves the picker on **Auto**.
Auto-selection is the default.

With the default policy, all 20 routing tasks resolve to `deepseek-ai/DeepSeek-R1` — it is the only
model that is chat-capable, licence-eligible, multilingual (en/de/fr) and covers every task. When an
operator unblocks the gated models, `meta-llama/Llama-3.3-70B-Instruct`, `Qwen/Qwen2.5-72B-Instruct`
and `google/gemma-3-27b-it` join it and the ranking starts differentiating again.

Runs through the same eliminate-then-rank pipeline in `ai_scoring.py`: capability gaps, task support,
licence, context window and language all filter candidates before ranking, and a per-task fallback
chain is generated from the live ranking (bounded by `AI_MAX_FALLBACK_DEPTH`).

## Output contracts (`infrastructure/ai/prompt_templates.py`)

Each task family has an explicit contract that is stated in the prompt and enforced afterwards.

- **Analysis tasks** (`ats_analysis`, `resume_analysis`, `job_description_analysis`,
  `keyword_extraction`, `skill_extraction`) → strict JSON with `additionalProperties: false`.
- **Generation and chat tasks** (`cv_*`, `cover_letter_*`, `career_advice`, …) → validated markdown
  with required `## Section` headings.

Malformed answers are repaired, not silently accepted
(`application/services/output_validation.py`):

1. validate the raw answer against the contract and collect the exact violations;
2. re-prompt naming those violations, up to `max_repairs` rounds (default 2);
3. if still invalid, return a labelled deterministic payload built **from the contract itself**, so it
   always validates — the reason travels on `ValidatedGeneration.fallback_reason`, never smuggled into
   the data as an extra key.

Every prompt also carries the honesty rules: no invented employers, dates, grades, credentials or
metrics, and a missing fact is reported rather than guessed.

## Routing audit

Each assistant message stores a `routing` audit in `chat_messages.routing`
(`supabase/migrations/20261012000000_multi_model_chat.sql`):

```json
{
  "selected_model": "deepseek-ai/DeepSeek-R1",
  "selection": "auto",
  "task": "ats_analysis",
  "fallback_chain": ["mistralai/Mixtral-8x7B-Instruct-v0.1"],
  "routing_score": 0.72,
  "contract": "json",
  "contract_status": "passed",
  "attempts": 1
}
```

`selection` is `auto` or `manual_override`; `contract_status` is `passed`, `repaired` or `fallback`;
`failure_reason` is added only when something failed.
