## Purpose

The versioned prompt modules for the **document** endpoints (CV, cover
letter, resignation) and the resume analysis. One module per prompt family,
each with its own version constant and its own anti-fabrication rules.

## Responsibilities

- One prompt builder per document type, with a version constant that travels
  with the answer
- The anti-fabrication rules: never invent employers, dates, metrics, grades
  or credentials
- The output contract of each prompt (the JSON schema or the markdown
  structure) so the answer can be validated afterwards

## Why the career-intent prompts are *not* here

The chat pipeline (RD-06/RD-08) has its own prompt module,
`app/application/services/career_prompts.py`, because its prompts are
**per intent** and they carry a different contract: the CV is data, the
request is the task, and the model answers with one JSON object. Keeping
them apart avoids the document prompts and the intent prompts drifting
together.

## Files

```
prompts/
├── __init__.py
├── cv.py                 # CV generation
├── cover_letter.py       # cover letter generation
├── resume_analysis.py    # resume analysis (ATS)
└── resignation.py        # resignation letter (tone selector)
```

## Testing

- `tests/unit/test_ai_infrastructure.py` — the prompt builders, the tone
  selector, the input caps and the output contract

## Related Modules

- `app.infrastructure.ai.prompt_templates` — the shared contracts and the
  general chat prompt
- `app.application.services.career_prompts` — the per-intent chat prompts
