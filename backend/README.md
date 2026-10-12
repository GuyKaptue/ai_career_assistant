# Backend overview

The backend is organised as a modular FastAPI application with a clear separation between configuration, domain logic, application services, and local API exposure.

## Responsibility split

- app/core: configuration, security, and shared infrastructure concerns
- app/domain: document, job, and template domain logic
- app/application/services: orchestration for generation, scoring, and workflow support
- app/main.py: API entry point

## Typical workflow

1. Build a structured candidate profile.
2. Select a CV or cover-letter template.
3. Generate document content from the domain model.
4. Score the resume against a target job description.
5. Search or track job opportunities through a provider abstraction.

This architecture keeps the product maintainable without requiring a monolithic file for every feature.
