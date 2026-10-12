# Supabase overview

The Supabase layer defines the persistence and access model for user accounts, documents, and job-tracker data. The schema is deliberately aligned to Postgres and Row-Level Security so that each user can only access their own information.

The project keeps the database design simple, sensible, and compatible with future extension. It can be used with Supabase cloud or a self-hosted Postgres deployment.
