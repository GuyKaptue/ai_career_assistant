# CV templates

Thirty CV templates are registered in
`backend/app/domain/templates/template_registry.py`. Each template is
an original implementation; the design language is inspired by public,
professional resume builders (see `resumaker-reference.md`).

The table below is generated from the registry — the ids, names, locales,
layouts and descriptions are the registry's own values, so it cannot drift
from the code.

## Catalog

| ID | Name | Locales | Layout | Description |
|----|------|---------|--------|-------------|
| academic | Academic | en, de, fr | academic | Publication- and research-focused layout for academic and R&D roles. |
| sidebar-right-blue | Blue Sidebar (Right) | en, de, fr | sidebar | Two-column CV with a bright blue right sidebar for skills and certificates. |
| sidebar-right-burgundy | Burgundy Classic (Right) | en, de, fr | sidebar | Serif two-column CV with a burgundy right sidebar. |
| sidebar-left-charcoal | Charcoal Modern (Left) | en, de, fr | sidebar | Dark charcoal sidebar with an orange accent. |
| banner-right-coral | Coral Banner (Right) | en, de, fr | sidebar | Full-width coral banner with a right sidebar below. |
| corporate | Corporate | en, de, fr | corporate | Formal layout for finance, legal, and enterprise roles. |
| creative | Creative | en, es, fr | creative | Visual layout for design, marketing, and media roles. |
| emerald-left | Emerald Sidebar (Left) | en, de, fr | sidebar | Fresh emerald left sidebar for health and sustainability roles. |
| executive | Executive | en | executive | High-clarity layout designed for senior leadership and strategic positions. |
| sidebar-left-forest | Forest Sidebar (Left) | en, de, fr | sidebar | Calm green left sidebar with marker-style section headings. |
| dark-left-graphite | Graphite Dark (Left) | en, de, fr | sidebar | Dark-mode two-column CV for engineering and data roles. |
| international | International | en, de, fr, es, nl | international | Neutral layout for cross-border and multilingual applications. |
| ivory-right-serif | Ivory Serif (Right) | en, de, fr | sidebar | Quiet serif two-column CV on ivory with a stone sidebar. |
| soft-left-lavender | Lavender Soft (Left) | en, de, fr | sidebar | Soft violet left sidebar for design and product roles. |
| sidebar-left-narrow | Light Narrow Sidebar | en, de, fr | sidebar | Slim light-grey sidebar that maximises space for experience. |
| dark-right-midnight | Midnight Gold (Right) | en, de, fr | sidebar | Black and gold right-sidebar CV for premium positioning. |
| minimal | Minimal | en | minimal | Low-noise format prioritizing readability and content density. |
| modern | Modern | en, es, nl | modern | Clean editorial layout for modern product and consulting roles. |
| sidebar-left-navy | Navy Sidebar (Left) | en, de, fr | sidebar | Executive two-column CV with a navy left sidebar and gold accents. |
| banner-left-ocean | Ocean Banner (Left) | en, de, fr | sidebar | Full-width name banner with a left sidebar below. |
| olive-left-compact | Olive Compact (Left) | en, de, fr | sidebar | Compact olive sidebar layout for dense, one-page CVs. |
| sidebar-right-wide | Plum Wide Sidebar (Right) | en, de, fr | sidebar | Wide plum right sidebar for skill-heavy profiles. |
| professional | Professional | en, fr, de | classic | Structured, ATS-friendly format for broad job applications. |
| rose-right | Rose Quartz (Right) | en, de, fr | sidebar | Rose right sidebar for marketing and communications. |
| skills-based | Skills-Based | en, fr | functional | Functional layout grouping skills over chronological history. |
| startup | Startup | en | startup | Compact, impact-focused layout for fast-moving teams. |
| sidebar-right-teal | Teal Executive (Right) | en, de, fr | sidebar | Teal right sidebar for leadership and consulting profiles. |
| technical | Technical | en, de | technical | Skills-first layout for engineering and data roles. |
| timeline | Timeline | en, de, nl | timeline | Chronological layout emphasizing career progression. |
| sand-right-warm | Warm Sand (Right) | en, de, fr | sidebar | Warm sand and brown right sidebar with an amber accent. |

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