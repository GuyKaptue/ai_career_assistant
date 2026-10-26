# Cover-letter templates

Ten cover-letter templates are registered in
`backend/app/domain/templates/template_registry.py`. The structured
renderer in `backend/app/infrastructure/document_export/cover_letter_docx.py`
follows a roughly DIN-5008 order:

sender block → rule → recipient → date → subject → salutation →
body → closing → signature.

## Catalog

| ID | Name | Locales | Layout | Description |
|----|------|---------|--------|-------------|
| brief-letter | Brief Letter | en, de | brief | A concise, three-paragraph letter for high-volume applications. |
| centered-serif-letter | Centered Serif Letter | en, de, fr | centered | Centered serif letterhead with a rule, traditional and formal. |
| classic-letter | Classic Letter | en, fr, de | formal | A refined, professional letter structure for formal applications. |
| creative-letter | Creative Letter | en, es, fr | creative | A narrative-driven letter for creative and marketing roles. |
| executive-letter | Executive Letter | en, de, fr | executive-letter | Dark executive banner with a serif body for senior roles. |
| formal-german-din5008 | Formal German DIN 5008 | de, en, fr | din5008 | Structured formal German business letter (sender, recipient, date, subject, salutation, body, closing). |
| letterhead-band | Letterhead Band | en, de, fr | letterhead | Letter with a coloured letterhead band carrying the sender name. |
| modern-letter | Modern Letter | en, de, fr | modern-letter | Clean sans-serif letter with an accent-coloured name. |
| technical-letter | Technical Letter | en, de | technical | A structured letter emphasizing technical scope and impact. |
| warm-letter | Warm Letter | en, fr, es | warm | A personable, enthusiastic tone for team-oriented cultures. |

## Tone selector

The resignation endpoint supports a `tone` selector
(`formal` | `warm` | `brief`). The cover-letter templates follow the
same principle: each template has a distinct tone, and the renderer
applies locale-aware defaults (salutation, closing) without
hard-coding user content.

## Locale-aware defaults

| Locale | Salutation | Closing |
|--------|-----------|---------|
| de | Sehr geehrte Damen und Herren, | Mit freundlichen Grüßen |
| en | Dear Hiring Manager, | Sincerely, |
| fr | Madame, Monsieur, | Cordialement, |

## Related documents

- [README.md](README.md)
- [rendering-architecture.md](rendering-architecture.md)
- [../architecture/template-system.md](../architecture/template-system.md)