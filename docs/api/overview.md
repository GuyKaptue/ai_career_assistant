# API overview

The backend exposes a small but purposeful API surface: health checks, document generation, resume analysis, template discovery, and job search. The design keeps the API easy to understand while still covering the main product experience.

## Health

The service exposes a simple `/health` route so deployments can verify the application is running before traffic is routed to it.

## Template listing

The `/api/v1/templates` endpoint lists the registered templates and allows a caller to filter by document type.

## Document generation

The application supports both CV and cover-letter generation endpoints. Each route accepts a payload with the candidate information and an optional template identifier. The response includes the selected template, the document type, and the final content blob used for preview or export.

## Resume review

The `/api/v1/resume/check` endpoint compares a resume and a job description to calculate a keyword-based ATS score and returns the strongest matches and suggested improvements.

## Jobs

The jobs search route allows the frontend to request relevant roles by search text and an optional location. It surfaces an explicit configuration error if no valid provider is enabled rather than returning fabricated results.

## Saved user data

The `/api/v1/profiles`, `/api/v1/applications`, and `/api/v1/documents` record-management routes require an `Authorization: Bearer <supabase-access-token>` header. The token's verified `sub` claim determines the owner; clients cannot select an owner with a query parameter or request body. A missing or invalid token receives `401`, while a valid token without configured verification settings receives `503`. Cross-user resource access responds with `404`.
