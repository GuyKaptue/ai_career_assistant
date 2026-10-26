# Resumaker.ai reference decision (T-00)

**Decision (2026-10-07): Reactive Resume (MIT) as the code base;
Resumaker.ai (proprietary) as visual/structural inspiration only.**

## Rationale

- `PROJECT_DESCRIBTION.md` names Reactive Resume (MIT, 12+ templates)
  as the template direction — permissively licensed, buildable now.
- The original template specification names Resumaker.ai (proprietary) as a *reference*,
  explicitly forbidding copying source code, assets, APIs, or claiming
  integration.
- These are compatible: implement original templates on an
  MIT-compatible engine in the spirit of Reactive Resume, using
  Resumaker.ai's publicly observable structure (typography hierarchy,
  section order, spacing, contact/skills/experience presentation) as
  design input only.

## What this means

- No Resumaker.ai code, CSS, assets, or APIs are copied or depended on;
  the app runs fully offline without Resumaker.ai.
- New templates are original implementations; any third-party
  font/asset keeps its own license + attribution in
  `docs/legal/licensing/third-party-assets.md` and `LICENSES.md`.
- The app never presents itself as an official Resumaker.ai integration.

## Observable design inputs (no code copied)

- Typography hierarchy (heading levels, spacing, weight).
- Section organization (summary, experience, education, skills,
  contact).
- Contact/skills/experience presentation patterns.
- Layout density and whitespace conventions.

## Prohibited

- Copying source code, CSS, assets, or APIs.
- Runtime dependency on Resumaker.ai.
- Presenting copied proprietary code as original work.

## Related documents

- [README.md](README.md)
- [cv-templates.md](cv-templates.md)
- [cover-letter-templates.md](cover-letter-templates.md)
- [../legal/licensing/third-party-assets.md](../legal/licensing/third-party-assets.md)