# Template system

## Template-base decision (T-00, decided 2026-10-07)

**Decision: Reactive Resume (MIT) as the code base; Resumaker.ai as visual/structural inspiration only.**

Rationale:
- `PROJECT_DESCRIBTION.md` names Reactive Resume (MIT, 12+ templates) as the template direction — permissively licensed, buildable now.
- `TEMPLATE_PROMPT.md` names Resumaker.ai (proprietary) as a *reference*, explicitly forbidding copying source code, assets, APIs, or claiming integration.
- These are compatible: implement original templates on an MIT-compatible engine in the spirit of Reactive Resume, using Resumaker.ai's publicly observable structure (typography hierarchy, section order, spacing, contact/skills/experience presentation) as design input only.

What this means:
- No Resumaker.ai code, CSS, assets, or APIs are copied or depended on; the app runs fully offline without resumaker.ai.
- New templates are original implementations; any third-party font/asset keeps its own license + attribution in `docs/legal/licensing/third-party-assets.md` and `LICENSES.md`.

The document experience is built around a dedicated template layer rather than custom rendering hidden inside the CV and cover-letter business logic. This separation allows the user to change a document style without altering the underlying data model or the narrative content itself.

The template registry stores the available template definitions in a way that is easy to extend. Each template has an identifier, a human-readable name, a document type, a semantic description, and optional metadata such as the locale and layout profile. The registry does not assume a fixed number of templates and does not require a large code change to add a new option.

The render path is intentionally simple: content is generated from structured user data, validated against the selected template, and converted into the final output representation. This workflow keeps the design readable and reduces the risk of accidental content mutation when a user previews another layout.

The implementation references the public design language seen in modern resume builders without copying proprietary source code, assets, or protected logic. The result is an original system that captures the same professional tone and practical structure while remaining maintainable and fully open source.

A viewer can switch between template types in the UI, preview a representative sample, and then save the selected style with the document. This preserves the content while allowing the visual treatment to change.
