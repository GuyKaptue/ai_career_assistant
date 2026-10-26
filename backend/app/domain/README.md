## Purpose

The domain layer: the business models and the rules that belong to the
product, with no HTTP, no AI provider and no infrastructure dependency.

## Packages

| Package | What it owns |
|---|---|
| `applications/` | the job application tracker (status flow, notes, follow-ups) |
| `chat/` | chat threads, messages and the per-session job context |
| `cover_letters/` | the cover-letter document model |
| `cv/` | the CV document model and the skill vocabulary |
| `documents/` | the shared document model, its versions and the export contract |
| `jobs/` | the unified `Job` model and the job-search orchestration |
| `knowledge/` | the career knowledge base entries and their domains |
| `positions/` | the parsed job posting (`Position`) |
| `projects/` | the project/workspace model |
| `resume_analysis/` | the resume-analysis result model |
| `templates/` | the template registry and the template definitions |
| `users/` | the user profile and the `UserCore` (the candidate data) |

## Rules

- A model is a frozen dataclass with an explicit `to_dict()`; unknown values
  stay unknown (`None` / empty), they are never replaced with a placeholder
- Domain rules (scoring, matching, status flows) live here or in
  `app/application/services`, never in the API layer
- No imports from `app.api` or `app.infrastructure`

## Testing

- `tests/unit/` — the domain rules
- `tests/api/test_e2e_journey.py` — the journey through the whole stack

## Related Modules

- `app.application.services` — the use cases
- `app.api.routes` — the HTTP surface
- `app.infrastructure` — the adapters
