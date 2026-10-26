# Career intents and job flows (RD-06 / RD-08)

> **Naming note:** the "RD-06 / RD-08" in this document's title refers to the
> intent-aware career assistant (the chat job flows, tracked as CJ-01…CJ-10 in
> `TODO.md` §6b). It is **not** the same sequence as `TODO.md` §6, where
> **RD-06 … RD-09** are the Ollama follow-ups (UI model picker, GPU
> verification, per-user quotas, prompt caching) — see
> `docs/deployment/ollama.md`.

## Purpose

The chat platform must answer the question the user actually asked. A user
who uploads a CV and writes *"please use this cv to help me search a
corresponding jobs for me"* wants job-search targets, not a paraphrase of
their CV. Before RD-06 the assistant had one output contract for every
message (`CHAT_CONTRACT`: a **Summary** paragraph, bulleted **Steps** and an
optional **Caveats** line), so a CV paraphrase validated as a correct answer.

This document describes the intent-aware pipeline: how the intent is
detected, how the job is ingested, how the answer is validated and what the
fallbacks do.

## The rule that matters

> **The LLM extracts and phrases. Code decides, validates and grounds.**

Every decision that must be reproducible — the intent, the match score, the
job title, the job company — is made in code. The model only reads the CV,
extracts a candidate profile and writes the wording.

## Pipeline

```
 A  receive + validate        chat.py        payload limits -> 400
 B  analyse the input         chat_input     kind: job_url | job_description | question | empty
 C  resolve the job           job_resolution pasted text first, then the URL (SSRF-safe fetch)
 D  classify the intent       career_intent  rule-based, multilingual, message only
 E  check the preconditions   career_assistant  CV present? job present? -> clarify (no model call)
 F  build the job target      job_target     deterministic first pass; one model call only if
                                                the title or the company is missing
 G  route                     career_assistant  match_job | tailor_cv | cover_letter
 H  model call                model_router_facade  one intent -> one task
 I  validate + ground         career_assistant  schema, grounding, flags
 J  persist + audit           chat_store     message, routing audit, session job context
```

Stages B, C, D, E, F and I never call a model. The model is called in H
(and in F, once, when the parsed position lacks a title or a company).

## Intent detection

`app/application/services/career_intent.py` classifies the **user message
only**. The CV is data: text inside the CV can never change the routing
decision, because the classifier never receives it.

| Intent | Meaning | Needs a CV? |
|---|---|---|
| `search_jobs` | find jobs | no |
| `summarize_cv` | summarise the CV | yes |
| `improve_cv` | improve the CV | yes |
| `skill_gap` | which skills are missing | yes |
| `interview_prep` | interview preparation | no |
| `cover_letter` | write a cover letter | yes |
| `match_job` | match the CV against one job | yes |
| `tailor_cv` | tailor the CV to one job | yes |
| `clarify` | something is missing (no CV, or no job) | — |
| `general` | today's behaviour, unchanged | no |

`classify_intents()` returns one decision for a single-intent message and two
for *"match this job and tailor my CV"* (the match first, then the document).

Rules (data, not regex soup) live in module-level constants. Text is
normalised first: case-folded, accents folded (`ä` → `ae`, `ß` → `ss`), so
*"Vorstellungsgespräch"* and *"Vorstellungsgespraech"* hit the same entry.

**Precedence.** An explicit CV edit wins over a job request: *"improve my CV
so I find jobs"* is `improve_cv`. A re-read is not a generation: *"Relis mon
lettre de motivation"* (re-read my cover letter) is `general`, because the
cover-letter rule requires a **generation** verb.

## Job ingestion

`app/application/services/job_resolution.py` turns a URL or a pasted block
into a `Position`:

- pasted text is trusted (only the length can reject it);
- a fetched page needs two non-title job signals, unless it carries JSON-LD
  job markup;
- the CV veto still applies: a page that only looks like a CV is not a
  posting, unless an employer hiring phrase ("we offer", "dein profil", …)
  proves otherwise;
- OCR is explicitly disabled on the chat path (a scanned PDF yields no text);
- fetching is SSRF-safe and never logs the URL path or query.

Statuses: `ok`, `login_wall`, `not_a_job_posting`, `fetch_failed`,
`invalid_url`, `too_large`, `unsupported_type`. Anything but `ok` produces a
clarifying reply — HTTP 200, `structured.job_ingest_status` set.

## The job target

`app/application/services/job_target.py` builds a `JobTarget` from the parsed
position:

1. **Deterministic first pass** — title, company, location, employment type
   and description straight from the position. No model call.
2. **One `job_extraction` model call** *only* when the title or the company
   is missing. The job text goes into the model inside a delimited
   `<job_text>` block, with a JSON schema and exactly one repair attempt.
3. **Grounding** — a model-returned title, company and skill must appear in
   the job text. A company that does not is **dropped** (`company` becomes
   `""`, `company_unverified` is set) and a title that does not degrades to
   the literal `the role` with `the_role_fallback` set. Neither blocks the
   turn: the reply says which field could not be verified.
4. **Structural limits** — a title is one line, at most 120 characters and at
   most 12 words, and carries no instruction-like markup. An over-long title
   is **rejected** (it falls back to `the role`), never silently truncated.

## Answering

| Intent | Pipeline | `structured` |
|---|---|---|
| `match_job` | `score_job` (code) + `job_gaps` | `match {score, label, matched_skills, missing_skills, reasons}`, `job {title, company, source_host, flags}`, `next_steps` |
| `tailor_cv` | `tailoring_pipeline.tailor_cv` | `document {type: cv, content, template_id}`, `grounding {removed}`, `gaps` |
| `cover_letter` | `tailoring_pipeline.write_cover_letter` | `document {type: cover_letter, content, template_id}`, `grounding`, `gaps` |

The **match score comes only from `score_job`**. The model may phrase an
explanation, but it can never change the number, and the explanations are
built from the verified matched and missing skills only.

`structured.job` is a **safe summary** (title, company, source host, flags).
The posting text, the URL and the path stay on the server.

## Session memory

`chat_sessions.job_context` (migration `rd08_004_chat_session_job_context.sql`,
applied by hand) keeps the job a thread is about: title, company, location,
employment type, skills, url, source host, the posting text (capped at
30 000 characters), a `text_hash` and the two flags. It never holds CV text,
it is deleted with the session, and it is never part of the payload sent to
the browser. With it, *"now write the cover letter"* still works after a
restart or in another worker.

Without the migration the write is refused (PostgREST answers PGRST204) and
the refusal is logged as a fact — never with content. The turn keeps working,
because the job in the message is enough.

## Privacy

- The CV and the job text only go where they went before: to Ollama, or to
  Hugging Face when the local model is unavailable.
- Nothing from the CV, the message, the job text, the prompt or the answer is
  logged or put into metrics. The logs carry the intent label, the rule id,
  the input kind, the ingest status, the host, the lengths and the counts.
- The search links are built by code from a template; the titles and skills
  leave the instance only when the user clicks one.
- `structured` never contains the posting text.

## Fallbacks

| Situation | Behaviour |
|---|---|
| no CV for a CV intent | clarify, `structured.missing = ["cv"]`, **no model call** |
| no job for a job intent | clarify, `structured.missing = ["job"]`, **no model call** |
| the page could not be read | clarify, `structured.job_ingest_status` set, HTTP 200 |
| the model returns invalid JSON | one repair attempt, then the on-intent fallback |
| Ollama **and** Hugging Face are down | the deterministic, on-intent fallback (never a CV paraphrase) |

The `general` intent is untouched: same prompt, same `CHAT_CONTRACT`, same
output. `backend/tests/api/test_chat_general_characterization.py` pins it.

## See also

- `app/application/services/career_intent.py` — the intent model
- `app/application/services/career_prompts.py` — the per-intent prompts
- `app/application/services/career_assistant.py` — the routing and the turns
- `app/application/services/job_target.py` — the verified job target
- `app/application/services/job_resolution.py` — the job ingestion
- `app/application/services/tailoring_pipeline.py` — CV tailoring and letters
- `app/application/services/job_search_pipeline.py` — the only scoring formula
- `docs/privacy/data-flow.md` — what leaves the instance
