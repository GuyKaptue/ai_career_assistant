# Templates

This directory documents the template system: the template registry,
the per-template catalog, the cover-letter catalog, the rendering
architecture, and the Resumaker.ai reference decision.

## Documents

| File | Topic |
|------|-------|
| [README.md](README.md) | Template system overview and conventions |
| [resumaker-reference.md](resumaker-reference.md) | T-00 decision: Reactive Resume vs Resumaker.ai |
| [cv-templates.md](cv-templates.md) | CV template catalog (12 templates) |
| [cover-letter-templates.md](cover-letter-templates.md) | Cover-letter template catalog (6 templates) |
| [rendering-architecture.md](rendering-architecture.md) | Rendering pipeline and shared primitives |

## Template inventory

- **CV (12):** professional, modern, executive, minimal, academic,
  technical, creative, timeline, skills-based, international,
  startup, corporate
- **Cover letter (6):** formal-german-din5008, classic-letter,
  warm-letter, brief-letter, creative-letter, technical-letter
- **Resignation (1):** formal-resignation

## Conventions

- Templates are selected by `id` and `document_type`.
- Each template carries metadata: `id`, `name`, `document_type`,
  `locales`, `color_scheme`, `layout`.
- Rendering is data-driven: content is generated from structured user
  data, validated against the selected template, and converted to the
  final output representation.
- No hard-coded user content; no duplicated rendering primitives.

## Related documents

- [../architecture/template-system.md](../architecture/template-system.md)
- [../requirements/requirements.md](../requirements/requirements.md)
- [../legal/licensing/third-party-assets.md](../legal/licensing/third-party-assets.md)