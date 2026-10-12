# CV templates

Twelve CV templates are registered in
`backend/app/domain/templates/template_registry.py`. Each template is
an original implementation; the design language is inspired by public,
professional resume builders (see `resumaker-reference.md`).

## Catalog

| ID | Name | Locales | Layout | Notes |
|----|------|---------|--------|-------|
| professional | Professional | en, de, fr | classic | Balanced, conservative |
| modern | Modern | en, de, fr | two-column | Contact sidebar |
| executive | Executive | en, de, fr | classic | Senior leadership |
| minimal | Minimal | en, de, fr | single-column | Sparse, whitespace |
| academic | Academic | en, de, fr | single-column | Publications, institutions |
| technical | Technical | en, de, fr | skills-based | Technical skills focus |
| creative | Creative | en, de, fr | visual | Color accents |
| timeline | Timeline | en, de, fr | timeline | Chronological timeline |
| skills-based | Skills-based | en, de, fr | skills-first | Competency-led |
| international | International | en, de, fr | single-column | Multi-locale aware |
| startup | Startup | en, de, fr | compact | Dense, energetic |
| corporate | Corporate | en, de, fr | classic | Formal, structured |

## Selection

Templates are selected by `template_id` and `document_type`. The
registry validates that the selected template supports the requested
document type and locale.

## Per-template READMEs (T-06)

Each template should have a short README describing its layout,
typography, color scheme, and when to use it. Currently consolidated
here; expand per-template as the catalog grows.

## Related documents

- [README.md](README.md)
- [rendering-architecture.md](rendering-architecture.md)
- [../architecture/template-system.md](../architecture/template-system.md)