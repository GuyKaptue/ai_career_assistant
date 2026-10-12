# Architecture decisions

The application uses a layered architecture so each part of the product owns a clear responsibility. The backend separates domain logic from application services and infrastructure concerns. This keeps the CV generation logic independent from the template registry and keeps the job-search abstraction independent from the UI and any eventual provider implementations.

The document domain is the central model of the product. A document is not just raw text; it has structure, a selected template, metadata, and an export workflow. This allows the same candidate data to be rendered as a CV, a cover letter, or a future document type without duplicating the underlying information model.

The template system is intentionally data-driven. Instead of building separate rendering functions for each format, the project stores template definitions and renders the final content from a shared document model. This keeps template selection a user-level choice and prevents the content from being mutated as the visual style changes.

For resume analysis, the system uses a content-based matching approach that compares the candidate resume against a target job description. This makes the feature transparent and explainable while avoiding a brittle dependency on a proprietary scoring engine. The score is derived from keyword overlap and overlap quality rather than opaque ranking mechanics.

The interface is deliberately simple and production-minded: one backend package, one frontend application, one Supabase migration set, and a clear set of deployment assets. This avoids unnecessary microservice complexity while still allowing the project to scale beyond an initial prototype.

Authentication and configuration are treated as explicit design elements. The project does not rely on hard-coded secrets or insecure token handling. Where external credentials are needed, they are validated and surfaced as configuration errors rather than being silently bypassed.

The project also treats template and data licensing carefully. The design takes inspiration from a publicly visible professional resume-builder experience without copying proprietary code or protected assets. That separation is documented in the legal and architecture references.
