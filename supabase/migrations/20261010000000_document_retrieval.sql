-- RD-05: personal document retrieval.
--
-- Extends the semantic_embeddings entity types
-- with cover_letter and resume_analysis so user
-- documents (CVs, cover letters, resume
-- analyses) can be chunked, embedded, and
-- retrieved for personalized generation.
-- Retrieval stays user-scoped (RLS): a user's
-- documents are only ever retrieved within that
-- user's context.

alter table public.semantic_embeddings
    drop constraint if exists semantic_embeddings_entity_type_check;

alter table public.semantic_embeddings
    add constraint semantic_embeddings_entity_type_check
    check (entity_type in ('profile', 'cv', 'cover_letter', 'resume_analysis', 'job_description'));
