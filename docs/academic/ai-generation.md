# AI generation theory

CV and cover-letter generation combine a deterministic template path with
an optional Hugging Face inference path. The two paths share a
contract: the output must validate against a Pydantic schema.

## 1. Two paths

### 1.1 Offline (default)

`use_ai` is `false` (or `HF_TOKEN` is unset). The document is rendered
by a deterministic template renderer. No network call is made. The
result carries `ai_generated: false` and `review_before_sending: false`.

### 1.2 Online (opt-in)

`use_ai: true` and `HF_TOKEN` is set. The backend:

1. Builds a prompt from user-supplied facts (no fabrication).
2. Selects a model via the router (task + context + language + health).
3. Calls the Hugging Face Inference API.
4. Validates the response against a Pydantic schema.
5. On schema violation, falls back to the template path.

The result carries `ai_generated: true`, the `model_id`, and
`review_before_sending: true`. A notice is appended to the content:
"AI-generated content — review before sending."

## 2. Prompt construction (§BE-02)

Prompts are built by dedicated modules in `infrastructure/ai/prompts/`:

- `cv.py` — `build_cv_prompt`
- `cover_letter` — `build_cover_letter_prompt`
- `resume_analysis.py` — `build_resume_analysis_prompt`
- `resignation.py` — `build_resignation_prompt`

Rules:

- Only user-supplied facts are included.
- If a metric is not provided, it is omitted — never fabricated.
- No PII defaults, no hardcoded employer.
- Prompts are versioned and auditable.

## 3. Contract validation (§AI-09)

Every AI output is validated against a Pydantic schema before use:

- `CVGenerationResult`
- `CoverLetterGenerationResult`
- `ResumeAnalysisResult`
- `JobMatchResult`

If validation fails, the output is rejected and the caller falls back
to the template path. The system **never** returns fake-valid output.

## 4. Fallback (§AI-07, §AI-08)

When the AI path fails (provider unavailable, schema violation, context
exhausted), the system:

1. Tries the next candidate in the dynamically generated fallback chain.
2. If all candidates fail, raises `AIProviderError` (mapped to 502).
3. The caller decides whether to fall back to local templates.

The fallback chain is bounded by `AI_MAX_FALLBACK_DEPTH` and is
dynamically generated per request.

## 5. Data minimization

Only the **prompt** (user-supplied career facts) is sent to Hugging Face.
The system never sends:

- The user's JWT or Supabase credentials.
- The user's `user_id`.
- Stored documents, applications, or tracker data.
- Job search queries or results.

Prompts are never logged; observability uses sanitized correlation IDs.

## 6. Observability (§AI-10)

Every routing decision is logged with:

- Task, selected model, fallback reason, fallback chain.
- Routing score, required context, success flag.

Metrics (§28) track: requests, successes, failures, fallbacks, latency,
token usage, circuit-breaker state, and per-model health.

## Related documents

- [mathematical.md](mathematical.md)
- [system.md](system.md)
- [limitations.md](limitations.md)