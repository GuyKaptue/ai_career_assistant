# Third-party assets and licensing

## Template-base decision (T-00, decided 2026-10-07)

- **Code base:** Reactive Resume direction (MIT) — original template implementations, attribution preserved.
- **Design reference only:** Resumaker.ai (proprietary). Used solely as publicly observable inspiration (typography hierarchy, section organization, spacing, headers, contact/skills/experience/education presentation). No source code, CSS, assets, APIs, or backend logic copied; no Resumaker.ai runtime dependency; never presented as an official integration.
- **Rule for new assets:** permissive licenses only (MIT, CC BY-SA where applicable); every third-party font/asset/design fragment gets license + attribution here and in `LICENSES.md`.

The project draws inspiration from public, professional document design patterns commonly used in modern career tools. In particular, the resume and cover-letter presentation style echoes the clean structure and hierarchy that users expect from polished templates, without copying any proprietary product code or protected assets.

The project itself is released under the MIT license. This allows the source code to remain open, permissive, and easy to adopt by individuals, universities, NGOs, and community-led career projects. Any external service or template integration introduced later should be governed by the same principle: use permissive open-source licenses wherever possible and document attribution clearly.

When a community member adds a new template, provider, or UI element, the relevant license information should be reviewed before release. This is especially important for design systems, fonts, and exported document assets that might carry a stronger attribution or copyleft requirement.

The project should never present copied proprietary code as original work. The goal is to build an original, maintainable implementation that captures the same professional design intent while remaining transparent and inspectable for future contributors.
