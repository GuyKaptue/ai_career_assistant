# Project workflow — implementation notes

Implements the backend gaps from the analysis: projects, position intake, apply flow, applied-job
exclusion, default job recency, tracker edits and the `models` / `ai test` CLI.

**Apply `supabase/migrations/20261011000000_projects_and_tracker_links.sql` first** (review the
`ASSUMES` comments). Without it the Supabase-backed stores cannot save the new columns / table
(the in-memory fallback used by tests and local dev works without it).

## API

| Method & path | Purpose |
|---|---|
| `GET/POST /api/v1/projects` | list / create (`name`, optional `template_id`, `cover_letter_template_id`; unknown templates → 400) |
| `POST /api/v1/projects/from-job` | start a project from a `/jobs/search` result (`{"job": {...}}`) |
| `GET/PATCH/DELETE /api/v1/projects/{id}` | PATCH: name, status, templates only. Delete keeps documents + tracker entry |
| `POST /api/v1/projects/{id}/position` | attach: `{"url"}` or `{"text"}` (extracted) or `{"position": {...}}` (user-edited) |
| `POST /api/v1/projects/{id}/position/file?index=0` | attach from PDF / DOCX / image / ZIP / HTML / text |
| `DELETE /api/v1/projects/{id}/position` | remove (not allowed once applied) |
| `POST /api/v1/projects/{id}/match` | `{"cv_text"}` or `{"cv_document_id"}` → ATS + semantic score, stored on the project |
| `POST /api/v1/projects/{id}/apply` | tailor CV + cover letter, create tracker entry (*applied*), link all; 409 if already applied |
| `POST /api/v1/positions/extract` | preview extraction from `{"url"}` or `{"text"}` (auth required) |
| `POST /api/v1/positions/extract/file` | preview extraction from an upload (auth required) |
| `GET /api/v1/applications/{id}` | read one entry |
| `PATCH /api/v1/applications/{id}` | edit `notes`, `follow_up_date` (ISO date or null), `job_url`, `company`, `position`, `status` |
| `GET /api/v1/jobs/search` | **new params** `include_old`, `include_applied`; signed-in users no longer see tracked jobs |

All project/application routes return **404 for other users' ids** (no existence leak).

## Behaviour worth knowing

* **Recency.** Every search keeps only postings from the last `JOB_DEFAULT_RECENCY_DAYS` days
  (default 30; `0` disables) for *all* providers (post-filter; providers that can filter server-side
  also get the window). `published_since_days` overrides it (max 100), `include_old=true` disables it.
  Postings with **no date are kept** (they cannot be proven old) and counted in `audit.undated_kept`.
* **Applied exclusion.** Identity = `job_key` (company+title+location), else normalised job URL,
  else — for manual tracker entries with neither — company+title. Same title in another city is a
  *different* job. All statuses (applied/interview/offer/rejected) are hidden unless
  `include_applied=true`, which annotates each result with `application_status`.
  Anonymous searches are unchanged. The cache is partitioned per tracked-set, so users never see
  each other's filtered pages.
* **Position extraction never invents data.** Missing title/company/location stay `null` with a
  `warnings` entry. JSON-LD `JobPosting` is preferred for web pages.
* **Safety limits.** Upload 5 MB (read capped, never fully buffered); PDF ≤ 30 pages; images ≤ 25 MP;
  ZIP ≤ 25 files, ≤ 5 MB per member, ≤ 20 MB expanded, ratio ≤ 100 (zip-bomb guard), unsafe paths and
  nested archives skipped, nothing written to disk. Types are detected from bytes, not file names.
* **URL import is SSRF-hardened:** http/https on 80/443 only, no credentials, every resolved address
  must be a global IP, redirects re-validated (max 3), connection pinned to the checked IP with TLS
  still verifying the original host (verified against a local TLS server), 2 MB cap, 10 s timeout.
  *Limitation:* pages that need JavaScript to render the posting are not supported.
* **Image import needs the `tesseract` CLI** (uses installed `deu`/`eng`/`fra` packs). Without it the
  API answers **503** with a clear message; no Python dependency was added.
* **Apply is deterministic (`ai_generated: false`).** It only *reorders* the candidate's own skills
  and highlights by relevance to the position; nothing is added. It requires `candidate.name` (no
  "Candidate" placeholder) or existing `cv_document_id` / `cover_letter_document_id`. If a later step
  fails, documents created in that call are deleted again.

## CLI

```
python -m app.cli models list [--task T] [--discovered] [--json]
python -m app.cli models validate [--json]            # exit 1 on inconsistencies / uncovered tasks
python -m app.cli models health [--live]
python -m app.cli models benchmark [--task T] [--json]            # offline routing benchmark
python -m app.cli models benchmark --live --model ID --runs 3     # real latency (needs HF_TOKEN)
python -m app.cli models discover [--task T]          # dry run, needs HF_TOKEN
python -m app.cli models refresh  [--task T]          # caches approved candidates, needs HF_TOKEN
python -m app.cli models enable|disable MODEL_ID      # restart the API afterwards
python -m app.cli ai test [--task T] [--language de] [--live] [--model ID]
python -m app.cli jobs search "python" --include-old
```

Offline by default; only `discover`, `refresh` and `--live` use the network (`--live` sends the
prompt to Hugging Face and says so). Discovered models are **never routable automatically**: they
need an explicit `models enable`, and the license policy still blocks `REQUIRES_REVIEW` / `BLOCKED`
ones. Operator choices live in `~/.config/ai-career-assistant/*.json`
(`AI_MODEL_OVERRIDES_FILE`, `AI_DISCOVERED_MODELS_FILE`).

## Not part of this change (still open from the analysis)

JWT `aud` handling (real Supabase tokens are rejected), the privacy gate for remote inference,
knowledge-base write access, export hardening, and the real template engine.
