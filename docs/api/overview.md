# API overview

The backend exposes a small but purposeful API surface: health checks, document
generation, resume analysis, template discovery, job search, and the chat
platform. The design keeps the API easy to understand while still covering the
main product experience.

The authoritative list is the OpenAPI document the app itself produces
(`http://localhost:8000/openapi.json`, browsable at `http://localhost:8000/docs`).
The table below is generated from it.

## Regenerating the route table

Run from `backend/` with the project venv active:

```bash
python -c "
from app.main import app
from fastapi.routing import APIRoute
from app.core.security.dependencies import get_current_user, get_optional_user
def walk(routes):
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        else:
            sub = getattr(r, 'original_router', None)
            if sub is not None and hasattr(sub, 'routes'):
                yield from walk(sub.routes)
def kinds(dep):
    out = set()
    for d in dep.dependencies:
        call = getattr(d, 'call', None)
        if call is get_current_user: out.add('required')
        if call is get_optional_user: out.add('optional')
        if d.dependencies: out |= kinds(d)
    return out
rows = []
for r in walk(app.routes):
    for m in sorted((r.methods or set()) - {'HEAD', 'OPTIONS'}):
        if r.path.startswith(('/api', '/health')):
            k = kinds(r.dependant)
            label = 'required' if 'required' in k else ('optional' if 'optional' in k else 'public')
            rows.append((m, r.path, label))
rows.sort()
for m, p, k in rows:
    print(f'| `{m} {p}` | {k} |')
"
```

## Authentication

| Requirement | Meaning |
|---|---|
| **required** | a verified bearer token is mandatory; without it the route answers `401` |
| **optional** | a valid token is used when present (it changes the answer, e.g. own templates appear); the route works without one |
| **public** | no token is read; the route never touches a saved user record |

The token's verified `sub` claim is the only source of record ownership:
payloads cannot assign another owner, and another user's resource answers
`404` so existence is not disclosed. A token without usable verification
configuration answers `503`.

## Routes

| Method and path | Auth | Purpose |
|---|---|---|
| `GET /api/health` | public | Liveness probe (§28) |
| `GET /api/ready` | public | Readiness probe (§28) |
| `GET /api/v1/applications` | required |  |
| `POST /api/v1/applications` | required |  |
| `DELETE /api/v1/applications/{application_id}` | required |  |
| `GET /api/v1/applications/{application_id}` | required |  |
| `PATCH /api/v1/applications/{application_id}` | required |  |
| `PATCH /api/v1/applications/{application_id}/status` | required |  |
| `POST /api/v1/chat/completions` | required |  |
| `GET /api/v1/chat/sessions` | required |  |
| `POST /api/v1/chat/sessions` | required |  |
| `DELETE /api/v1/chat/sessions/{session_id}` | required |  |
| `GET /api/v1/chat/sessions/{session_id}` | required |  |
| `GET /api/v1/country-profiles` | public |  |
| `GET /api/v1/documents` | required |  |
| `POST /api/v1/documents` | required |  |
| `POST /api/v1/documents/cover-letter/generate` | optional |  |
| `POST /api/v1/documents/cv/generate` | optional |  |
| `POST /api/v1/documents/render` | optional |  |
| `POST /api/v1/documents/resignation/generate` | optional |  |
| `GET /api/v1/documents/retrieve` | required |  |
| `DELETE /api/v1/documents/{document_id}` | required |  |
| `GET /api/v1/documents/{document_id}` | required |  |
| `PATCH /api/v1/documents/{document_id}` | required |  |
| `GET /api/v1/documents/{document_id}/export` | required |  |
| `POST /api/v1/documents/{document_id}/index` | required |  |
| `GET /api/v1/documents/{document_id}/versions` | required |  |
| `GET /api/v1/documents/{document_id}/versions/{version}` | required |  |
| `POST /api/v1/documents/{document_id}/versions/{version}/restore` | required |  |
| `GET /api/v1/jobs/search` | optional |  |
| `POST /api/v1/knowledge/ingest` | required |  |
| `GET /api/v1/knowledge/search` | public |  |
| `GET /api/v1/models` | public |  |
| `POST /api/v1/positions/extract` | required |  |
| `POST /api/v1/positions/extract/file` | required |  |
| `POST /api/v1/profiles` | required |  |
| `DELETE /api/v1/profiles/me` | required |  |
| `GET /api/v1/profiles/{user_id}` | required |  |
| `PATCH /api/v1/profiles/{user_id}` | required |  |
| `GET /api/v1/projects` | required |  |
| `POST /api/v1/projects` | required |  |
| `POST /api/v1/projects/from-job` | required |  |
| `DELETE /api/v1/projects/{project_id}` | required |  |
| `GET /api/v1/projects/{project_id}` | required |  |
| `PATCH /api/v1/projects/{project_id}` | required |  |
| `POST /api/v1/projects/{project_id}/apply` | required |  |
| `POST /api/v1/projects/{project_id}/match` | required |  |
| `DELETE /api/v1/projects/{project_id}/position` | required |  |
| `POST /api/v1/projects/{project_id}/position` | required |  |
| `POST /api/v1/projects/{project_id}/position/file` | required |  |
| `POST /api/v1/resume/check` | public |  |
| `POST /api/v1/resume/extract` | public |  |
| `GET /api/v1/templates` | optional |  |
| `POST /api/v1/templates/preview` | public |  |
| `GET /api/v1/templates/{template_id}/sample` | public |  |
| `GET /api/v1/themes` | public |  |
| `GET /health` | public | Liveness probe |

## Health

`GET /health` is a liveness probe and `GET /api/ready` a readiness probe
that also reports the local-inference channel. Both are public.

## Template listing

`GET /api/v1/templates` lists the registered templates and filters by
document type. It is **optional-auth**: an anonymous caller sees the built-in
templates, a signed-in caller also sees their own templates. The items carry
additive fields (`type`, `layout`, `color_scheme`, `columns`, `sidebar`,
`sidebar_pct`, `theme_id`, `source`).

`GET /api/v1/templates/{template_id}/sample` renders a sample of one template
(`document_type`, `locale`, `format`, `theme_id`, `country`, `sidebar`) and is
public. `POST /api/v1/templates/preview` previews a template body and is
public. `GET /api/v1/themes` lists the colour themes and `GET
/api/v1/country-profiles` the per-country layout rules; both are public.

## Document generation

`POST /api/v1/documents/cv/generate`, `.../cover-letter/generate` and
`.../resignation/generate` are **optional-auth**: they work for an anonymous
caller and, when a token is present, ground the answer in that user's own
documents. The response carries the selected template, the document type and
the final content used for preview or export.

`POST /api/v1/documents/render` is a **stateless** render: it returns the
rendered document without storing anything, which is what the export
download uses. `GET /api/v1/documents/{document_id}/export` serves a stored
document and requires a token.

## Resume review

`POST /api/v1/resume/check` compares a resume and a job description to
calculate a keyword-based ATS score and returns the strongest matches and
suggested improvements; `POST /api/v1/resume/extract` extracts the structured
data. Both are public.

## Jobs

`GET /api/v1/jobs/search` requests relevant roles by search text and an
optional location. It is optional-auth: a signed-in caller does not see the
jobs they already tracked, and the route surfaces an explicit configuration
error if no valid provider is enabled rather than returning fabricated results.

### Project workflow

The project routes tie a position, a tailored CV, a cover letter and the
tracker entry together.

| Method and path | Purpose |
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

All project and application routes answer **404 for another user's ids**.

The `projects` table and the profile-preference columns live in the
`backend/migrations/rd08_001_user_core_and_templates.sql` migration, which is
applied by hand (see [`docs/development/setup.md`](../development/setup.md)).

## Chat

`POST /api/v1/chat/completions` runs one conversation turn and is
**required-auth**. Beyond `message` and `session_id` it accepts
`document_context` (the CV text), `job_url` and `job_text` (the posting),
`document_type` (`cv` or `cover_letter`), `template_id`, `theme_id` and
`preferences` (which may carry `treat_as_plain_text`). A message or a job text
over the documented limit answers **400**. The response keeps the existing
fields and adds `intent`, `structured` and the routing audit; the pipeline is
described in [`career-intents.md`](../architecture/career-intents.md).

## Saved user data

The `/api/v1/profiles`, `/api/v1/applications`, `/api/v1/documents` and
`/api/v1/chat` record-management routes require an `Authorization: Bearer
<supabase-access-token>` header. A missing or invalid token receives `401`,
while a valid token without configured verification settings receives `503`.
Cross-user resource access responds with `404`. `DELETE /api/v1/profiles/me`
is the GDPR erasure path for the caller's own records.
