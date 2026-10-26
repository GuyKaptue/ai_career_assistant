-- RD-08 migration 004 (idempotent): remember the job a chat session is about.
--
-- Why: "now write the cover letter" must still work when the session is loaded again from the
-- database (another worker, a restart, a scaled deployment). One jsonb column keeps the record
-- compact and needs no further schema changes.
--
-- Content (written by the backend, never sent to the browser as-is): title, company, location,
-- employment_type, skills, url, source_host, description (the job posting text, max 30 000 chars),
-- text_hash, ingested_at, company_unverified, the_role_fallback. It never holds CV text.
--
-- Privacy: the column lives on the session row, so deleting the session (GDPR erasure) deletes it.
-- Existing row-level-security policies on chat_sessions apply to the new column unchanged.
--
-- Apply this by hand in the Supabase SQL editor. It is not applied automatically.
do $$
begin
  alter table chat_sessions add column if not exists job_context jsonb;
  comment on column chat_sessions.job_context is
    'Last job target of the session (posting text, no CV text). Deleted with the session.';
exception when undefined_table then
  raise notice 'chat_sessions does not exist; nothing to do';
end $$;

-- Make PostgREST see the new column without a restart.
notify pgrst, 'reload schema';
