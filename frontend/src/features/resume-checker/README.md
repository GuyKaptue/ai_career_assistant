# Resume Checker Feature

## Purpose

ATS resume review (FE-02). Posts the resume text
and job description to `POST /api/v1/resume/check`
and reports the score and matched keywords.

## Behavior

- Requires a session; reports `signInRequired`
  otherwise.
- Score is lifted to the shell (`onScore`) so the
  stats grid can display it.
- Errors render inline with `role="alert"`.

## Key Exports

- `ResumeChecker({ session, onScore })`

## Testing

- Covered by the API contract tests on the backend;
  the component is exercised through the shell.
