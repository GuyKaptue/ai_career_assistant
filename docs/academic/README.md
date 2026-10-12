# Academic documentation

This directory holds the academic-grade technical documentation for the
AI Career Assistant: formal system description, mathematical models,
scoring theory, and evaluation methodology.

These documents are written for readers with a computer-science or
engineering background and are intended to make the design decisions
and formulas auditable.

## Documents

| File | Topic |
|------|-------|
| [system.md](system.md) | System description: components, data flow, and invariants |
| [mathematical.md](mathematical.md) | Formal models: routing score, token budget, ATS aggregation |
| [ats.md](ats.md) | ATS scoring theory: keyword overlap, formatting, readability |
| [ai-generation.md](ai-generation.md) | AI generation theory: prompt construction, fallback, contract validation |
| [architecture.md](architecture.md) | Layered architecture, separation of concerns, extension points |
| [evaluation.md](evaluation.md) | Evaluation methodology: test strategy, metrics, and proof obligations |
| [limitations.md](limitations.md) | Known limitations, assumptions, and deferred roadmap items |

## Conventions

- Formulas use LaTeX-style notation in prose.
- "Unknown" is a first-class value: a field whose value is unknown is
  `None`, never a fabricated default (see `ModelMetadata.unknown_fields()`).
- All scores are bounded 0–100 unless stated otherwise.

## Related documents

- [../requirements/requirements.md](../requirements/requirements.md)
- [../architecture/template-system.md](../architecture/template-system.md)
- [../security/overview.md](../security/overview.md)