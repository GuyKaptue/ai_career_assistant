# Implementation roadmap

## Phase 1 - Foundations

The first milestone establishes the project skeleton, environment configuration, backend app package, and testing harness. The goal is to create a maintainable structure before any feature-specific work is added.

This phase includes the base project documents, the requirement traceability set, and the modular domain structure for templates, jobs, and document generation.

## Phase 2 - Core document features

The next milestone adds the CV and cover-letter generation services. These services rely on template definitions and render a final document payload in a controlled and inspectable format. The output is structured enough for export and preview work without being tied to a specific front-end renderer.

## Phase 3 - Resume review and search

This phase introduces the ATS-style resume evaluation logic and the job-search abstraction. The analysis logic is intentionally transparent and based on structured text comparison. The job-search service raises a clear configuration error when real provider credentials are missing.

## Phase 4 - Application tracking and storage

The project then adds persistence structure and job-tracker data models. Users can store applications, statuses, notes, and follow-up dates in a simple relational schema built for Supabase and compatible with Postgres.

## Phase 5 - Frontend and deployment

The final product requires a user interface for creating documents, previewing templates, tracking jobs, and reviewing the ATS score. The deployment layer includes Docker Compose and example environment variables so the application can run locally or in a managed host.

The long-term roadmap keeps the project simple enough to maintain, while leaving room for more templates, alternative AI providers, and additional deployment options as the community grows.
