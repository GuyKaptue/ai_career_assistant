-- Application <-> job/document link columns.
--
-- The JobApplication domain model (backend/app/domain/applications/models.py)
-- serialises five optional linking fields, but the original init migration only
-- created the base job_applications table. Writing a tracked application that
-- carries any of these fields failed with PostgREST PGRST204 ("Could not find
-- the '<column>' column of 'job_applications' in the schema cache") because the
-- columns did not exist. This migration brings the table in line with the
-- model so the Application Tracker (and the project apply-flow) can persist.
--
-- All columns are nullable so existing/manual rows keep working unchanged.

alter table if exists public.job_applications
    add column if not exists job_key text,
    add column if not exists source text,
    add column if not exists project_id uuid,
    add column if not exists cv_document_id uuid,
    add column if not exists cover_letter_document_id uuid;

-- Lookup indexes for the new link columns (cheap; only written when populated).
create index if not exists idx_applications_job_key on public.job_applications(job_key);
create index if not exists idx_applications_project_id on public.job_applications(project_id);
create index if not exists idx_applications_cv_document_id on public.job_applications(cv_document_id);
create index if not exists idx_applications_cover_letter_document_id on public.job_applications(cover_letter_document_id);
