# Privacy and data handling

The project is designed for user-controlled career data and self-hosted deployment. The privacy model assumes the user owns their CV, job-search context, and application status information, and that the application should respect that ownership boundary.

## Core principles

- use explicit user identity rather than implicit local defaults
- keep storage and access decisions under infra configuration and app-level ownership checks
- avoid sending user data to providers or model endpoints unless the project configuration makes that explicit
- ensure auditability through clear configuration and readable service boundaries

## Relevant documents

- [overview.md](overview.md)
- [data-flow.md](data-flow.md) — what leaves the instance and when
- [../requirements/requirements.md](../requirements/requirements.md)
- [../security/overview.md](../security/overview.md)
