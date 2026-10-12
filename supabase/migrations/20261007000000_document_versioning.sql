-- BE-05: document versioning (MASTER §17 "versioning where justified",
-- §23 "version metadata if implemented").
--
-- `version` starts at 1 and increments on every content change.
-- `version_history` holds bounded snapshots (newest last) of previous
-- versions: {version, title, document_type, template_id, content, saved_at}.

alter table if exists public.documents
    add column if not exists version integer not null default 1,
    add column if not exists version_history jsonb not null default '[]'::jsonb;
