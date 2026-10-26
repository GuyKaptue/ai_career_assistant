# Privacy overview

The application is designed around the principle that personal career data should remain under the control of the user and the instance owner. The project supports self-hosting and keeps the database and authorization flow aligned with the idea that user information should not be treated as a commodity.

The exporter and document-generation layers are designed to work with user-supplied content and to store it in a controlled, user-scoped model. The architecture does not assume that data should be pushed to a third-party service without a clear configuration decision.

This also fits the open-source goal of the project: the stack should be familiar enough for a community maintainer to run it responsibly and adapt it to their own hosting or compliance requirements.

## Practical boundaries

- user identity must come from the authenticated subject, not a fake local placeholder
- stored documents and applications remain scoped by `user_id` and are validated in the API layer
- external job or model settings must be configured explicitly; no silent fallback to placeholder data is accepted
- deployment configuration should make it clear which environment owns the data and which keys are required for secure operation

## Stored data inventory

The persisted state lives in the Supabase Postgres schema. The table below lists
every relation that stores data, derived from the migrations under
`supabase/migrations/` and `backend/migrations/`. `user_id` always equals the
authenticated JWT `sub`; the API layer derives identity from the token and never
from the request body, so one account cannot address another's rows.

| Table | Primary key | Ownership | Row-level security | Holds user PII |
|---|---|---|---|---|
| `profiles` | `user_id` (uuid) | `auth.uid() = user_id` | per-user policy | yes — email, name, role, location, summary |
| `documents` | `id` (uuid) | `auth.uid() = user_id` | per-user policy | yes — CV/cover/resignation content, title |
| `job_applications` | `application_id` (uuid) | `auth.uid() = user_id` | per-user policy | yes — company, position, URL, notes, follow-up |
| `profile_preferences` | `user_id` (text) | `auth.uid() = user_id` (app-layer) | enabled, no per-user policy | yes — titles, industries, salary, must-haves, deal-breakers |
| `user_templates` | `id` (text) | `auth.uid() = user_id` (app-layer) | enabled, no per-user policy | yes — template content |
| `chat_sessions` | `id` (uuid) | `auth.uid() = user_id` | per-user policy | yes — conversation metadata |
| `chat_messages` | `id` (uuid) | via `chat_sessions` | per-session policy | yes — message text (richest PII surface) |
| `semantic_embeddings` | `id` (uuid) | own: `user_id`; public: `user_id IS NULL` | own + public | no — derived vectors, not raw PII |
| `knowledge_entries` | `id` (uuid) | shared across authenticated users | authenticated-read / service-role-write | no — shared career knowledge |
| `candidate_analyses` | `id` (text) | `auth.uid() = user_id` (app-layer) | enabled, no per-user policy | yes — CV/job-analysis output |
| `job_search_runs` | `id` (text) | `auth.uid() = user_id` (app-layer) | enabled, no per-user policy | yes — search query text |
| `job_search_matches` | `(run_id, job_key)` | `auth.uid() = user_id` via run (app-layer) | enabled, no per-user policy | no — job listings, not user PII |

The five `profile_preferences`, `user_templates`, `candidate_analyses`,
`job_search_runs` and `job_search_matches` relations enable row-level security but
carry no per-user policy; ownership is enforced in the backend service (which uses
the service role) rather than at the database row level, so they must be read and
written only through the authenticated backend service. `chat_messages` is the
richest personal-data surface (full conversation text) and is deleted together
with its owning `chat_sessions` row; `semantic_embeddings` and
`knowledge_entries` may contain text supplied by any authenticated user and are
shared across the instance.
