# Domain — Templates

## Purpose

Template registry for document rendering. Templates are
selected by `id` and `document_type` and carry metadata
(locales, color scheme, layout) without hard-coding
rendering logic.

## Responsibilities

- Register and list templates by document type
- Select a template by id + type
- Validate template support

## Architecture

```
domain/templates/
├── __init__.py
└── template_registry.py   # TemplateDefinition + TemplateRegistry
```

## Public API

- `TemplateRegistry.list_templates(document_type=None)`
- `TemplateRegistry.get(template_id, document_type=None)`
- `TemplateRegistry.validate(template_id, document_type)`

## Template Inventory

- **CV (12):** professional, modern, executive, minimal,
  academic, technical, creative, timeline, skills-based,
  international, startup, corporate
- **Cover letter (6):** formal-german-din5008, classic-letter,
  warm-letter, brief-letter, creative-letter, technical-letter
- **Resignation (1):** formal-resignation

## Testing

- `tests/test_template_registry.py` — counts, uniqueness, locales

## Related Modules

- `app.application.services.document_generation` — rendering
