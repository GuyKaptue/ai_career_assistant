# Product requirements

The AI Career Assistant is designed to help job seekers manage the full career workflow in one place. It supports drafting documents, reviewing resume fit against a position, finding relevant openings, and keeping application progress visible without forcing the user to work across multiple disconnected tools.

The product is built around three principles: clarity for the candidate, privacy for the user, and maintainability for the project team. A person should be able to create a tailored CV, review an existing resume against a job description, and track application outcomes without needing a separate spreadsheet, document editor, or job portal workflow.

## User-facing requirements

The application must enable a new user to create an account, complete a short onboarding profile, and generate a CV and a cover letter aligned to a target role. The generated documents should be stored so they remain editable and reusable, and the user should be able to switch between templates without losing the underlying content.

The CV builder should handle standard sections such as profile summary, experience, education, skills, certifications, and project highlights. The cover-letter builder should support structured sender details, recipient information, greeting, body sections, motivation, and closing language.

The resume-analysis workflow should let the user either paste or upload text and produce a clear ATS-style score with suggested improvements. The application should explain what is missing from the resume relative to the role, rather than only showing a bare score.

The job-discovery module provides search and matching behaviour for public, free job sources. It should not invent job listings or silently degrade to fake data when provider credentials are not available. If a source is unavailable, the system should fail clearly and allow a real provider integration to be configured.

The tracker should let users record each application, move it through a visible status flow, attach notes, links, and follow-up dates, and keep a history of the decisions taken around each role.

## Product constraints

The project is fully open source and self-hostable. It must not rely on paid features for basic operations, and user-facing features should work without a subscription layer. The product should run in a Docker-capable environment, and it should be possible to start the project locally with a simple command sequence.

The codebase should remain modular so new document types, providers, or UI features can be added without rewriting the whole application. Although the architecture is modular, the early version must still deliver complete, usable behaviour for the main user journey.

## Non-functional expectations

The project should prioritise security, observability, and maintainability. Credentials must be loaded from environment variables or a secure secret store and never committed to source control. The backend should validate requests and fail with clear error context when configuration is missing.

The application should produce structured logs and expose meaningful health and readiness endpoints. It should also be easy to test in isolation, with unit tests for core domain logic and API-level checks for the most important flows.

A professional documentation set is required so a developer can understand the architecture, deployment process, and ongoing maintenance responsibilities without reading the implementation prompts or hidden instructions.
