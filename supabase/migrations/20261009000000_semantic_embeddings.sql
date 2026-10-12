-- RD-04: semantic job matching embeddings.
--
-- `semantic_embeddings` stores vector embeddings for
-- user profiles, CVs, and job descriptions (384
-- dimensions, matching sentence-transformers/
-- all-MiniLM-L6-v2). User-owned embeddings (profiles,
-- CVs) carry `user_id` and are RLS-scoped to the
-- owner; job-description embeddings are public
-- (user_id IS NULL).

create extension if not exists vector;

create table if not exists public.semantic_embeddings (
    id uuid primary key default gen_random_uuid(),
    entity_type text not null check (entity_type in ('profile', 'cv', 'job_description')),
    entity_id text not null,
    content text not null,
    embedding vector(384),
    user_id uuid references auth.users(id) on delete cascade,
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone default now(),
    unique (entity_type, entity_id)
);

alter table public.semantic_embeddings enable row level security;

-- Users read their own embeddings and public
-- (job-description) embeddings.
create policy "Users read own and public semantic embeddings"
    on public.semantic_embeddings for select to authenticated
    using ((user_id is null) or ((select auth.uid()) = user_id));

-- Only the service role writes embeddings.
create policy "Service role writes semantic embeddings"
    on public.semantic_embeddings for all to service_role
    using (true) with check (true);

create index if not exists idx_semantic_embeddings_entity
    on public.semantic_embeddings(entity_type);

create index if not exists idx_semantic_embeddings_user
    on public.semantic_embeddings(user_id);

create index if not exists idx_semantic_embeddings_embedding
    on public.semantic_embeddings
    using ivfflat (embedding vector_cosine_ops) with (lists = 8);

-- Server-side cosine similarity search (RD-04).
-- User-scoped: when user_filter is set, only that
-- user's rows and public rows are searched.
create or replace function public.semantic_search(
    query_embedding vector(384),
    match_threshold float default 0.0,
    match_count int default 5,
    entity_type_filter text default null,
    user_filter uuid default null
)
returns table (
    id uuid,
    entity_type text,
    entity_id text,
    content text,
    user_id uuid,
    metadata jsonb,
    created_at timestamp with time zone,
    similarity float
)
language sql stable
as $$
    select
        se.id,
        se.entity_type,
        se.entity_id,
        se.content,
        se.user_id,
        se.metadata,
        se.created_at,
        1 - (se.embedding <=> query_embedding) as similarity
    from public.semantic_embeddings se
    where se.embedding is not null
      and (entity_type_filter is null or se.entity_type = entity_type_filter)
      and (user_filter is null or se.user_id is null or se.user_id = user_filter)
      and 1 - (se.embedding <=> query_embedding) >= match_threshold
    order by se.embedding <=> query_embedding
    limit match_count;
$$;
