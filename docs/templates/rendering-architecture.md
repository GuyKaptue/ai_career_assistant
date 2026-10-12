# Rendering architecture

## Pipeline

```
User data (structured)
    │
    ▼
Template selection (template_id + document_type + locale)
    │
    ▼
Prompt / renderer (deterministic or AI-assisted)
    │
    ▼
Pydantic contract validation
    │
    ▼
Output (HTML / PDF / DOCX / text)
```

## Layers

### 1. Template registry

`backend/app/domain/templates/template_registry.py`

Stores template definitions: `id`, `name`, `document_type`,
`locales`, `color_scheme`, `layout`. The registry does not assume a
fixed number of templates and does not require a large code change to
add a new option.

### 2. Renderers

- `backend/app/application/services/document_generation.py` — CV and
  cover-letter rendering (HTML/PDF).
- `backend/app/infrastructure/document_export/cover_letter_docx.py` —
  structured DOCX rendering.

Renderers are data-driven: content is generated from structured user
data, validated against the selected template, and converted to the
final output representation.

### 3. Export formats

| Format | Renderer | Media type |
|--------|----------|------------|
| HTML | `render_document_to_html` | text/html |
| PDF | `render_document_to_pdf` (ReportLab) | application/pdf |
| DOCX | `render_document_to_docx` (python-docx) | application/vnd.openxmlformats-officedocument.wordprocessingml.document |
| Text | raw content | text/plain |

## Shared design primitives (T-05)

Rendering constants live in one place; no duplicated rendering logic:

- Margins: `MARGIN_TOP_BOTTOM_IN`, `MARGIN_LEFT_RIGHT_IN`
- Fonts: `FONT_NAME`, `FONT_SIZE_PT`, `SENDER_NAME_SIZE_PT`
- Colors: `FONT_COLOR`, `SENDER_NAME_COLOR`, `SENDER_CONTACT_COLOR`,
  `SUBJECT_COLOR`, `RULE_COLOR`

## Anti-fabrication

Renderers never invent employment, education, metrics, certifications,
or skills. If a metric is not provided, it is omitted — never
fabricated.

## Related documents

- [README.md](README.md)
- [cv-templates.md](cv-templates.md)
- [cover-letter-templates.md](cover-letter-templates.md)
- [../architecture/template-system.md](../architecture/template-system.md)