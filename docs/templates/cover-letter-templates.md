# Cover-letter templates

Six cover-letter templates are registered in
`backend/app/domain/templates/template_registry.py`. The structured
renderer in `backend/app/infrastructure/document_export/cover_letter_docx.py`
follows a roughly DIN-5008 order:

sender block → rule → recipient → date → subject → salutation →
body → closing → signature.

## Catalog

| ID | Name | Locales | Tone | Notes |
|----|------|---------|------|-------|
| formal-german-din5008 | Formal (German DIN 5008) | de, en, fr | formal | DIN-5008 order, German defaults |
| classic-letter | Classic | en, de, fr | formal | Traditional business letter |
| warm-letter | Warm | en, de, fr | warm | Personal, relationship-focused |
| brief-letter | Brief | en, de, fr | brief | Concise, one page |
| creative-letter | Creative | en, de, fr | creative | Distinctive, design-forward |
| technical-letter | Technical | en, de, fr | formal | Technical role focus |

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