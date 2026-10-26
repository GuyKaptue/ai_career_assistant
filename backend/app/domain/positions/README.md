## Purpose

The parsed job posting: one immutable record of what a posting says about
itself. It is the **input** of the job-target verification, not the
verified target.

## Responsibilities

- Carry the posting's own fields: title, company, location, description,
  employment type, url, source, publication date and keywords
- Record **how** the record was obtained (`extracted_with`:
  `json_ld` | `heuristic` | `structured`) and what could not be read
  (`warnings`)
- Never invent a value: a field that the posting does not state stays
  `None` or empty

## Why it is separate from the job target

`Position` is what the *page* said. `JobTarget`
(`app/application/services/job_target.py`) is what the *code* could verify:
the title and the company must appear in the posting text, or they are
dropped. Keeping the two apart is what makes the anti-hallucination check
possible.

## Data contract

`Position.to_dict()` is the wire format. `extracted_with` matters: a page
with JSON-LD job markup is trusted as a posting, a heuristically parsed page
has to earn it with job signals.

## Testing

- `tests/unit/test_job_target.py` — the verification of a parsed position
- `tests/unit/test_job_resolution.py` — how the position is produced

## Related Modules

- `app.application.services.position_extraction` — the parsing
- `app.application.services.job_resolution` — the ingestion
- `app.application.services.job_target` — the verified target
