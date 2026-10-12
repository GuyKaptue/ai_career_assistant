# Features

## Purpose

Feature modules (FE-02). Each feature owns its
local state, renders its own panels, and reports
transient outcomes to the global status channel.

## Modules

| Module | Responsibility |
| --- | --- |
| `auth/AuthPanel` | Supabase sign-in / sign-up form, signed-in state |
| `documents/DocumentStudio` | CV / cover-letter input form |
| `documents/TemplateGallery` | Template selection + server-rendered preview modal |
| `resume-checker/ResumeChecker` | ATS review form, score reporting |
| `jobs/JobDiscovery` | Job search form, results, save-to-tracker |
| `tracker/ApplicationTracker` | Quick-add form + Kanban pipeline (applied → interview → offer → rejected) |

## Conventions

- Features receive cross-feature data via props
  (session, applications bundle, callbacks).
- Features never fetch cross-feature data directly;
  the shell or a shared hook owns that.
- All user-facing strings go through `useI18n().t()`.

## Testing

- `features/auth/AuthPanel.test.jsx`
- `features/documents/TemplateGallery.test.jsx`
- `features/tracker/ApplicationTracker.test.jsx`

## Related Modules

- `../hooks` — shared state and data access
- `../components` — shared UI primitives
