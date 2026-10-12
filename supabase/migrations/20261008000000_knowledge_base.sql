-- RD-03: vectorized career knowledge base (RAG).
--
-- `knowledge_entries` stores career guidance snippets with
-- pgvector embeddings (384 dimensions, matching
-- sentence-transformers/all-MiniLM-L6-v2). The knowledge
-- base is a shared resource: readable by every
-- authenticated user, writable by the service role only.

create extension if not exists vector;

create table if not exists public.knowledge_entries (
    id uuid primary key default gen_random_uuid(),
    domain text not null,
    content text not null,
    source text not null,
    embedding vector(384),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamp with time zone default now()
);

alter table public.knowledge_entries enable row level security;

create policy "Knowledge base is readable by authenticated users"
    on public.knowledge_entries for select to authenticated using (true);

create policy "Knowledge base is writable by service role"
    on public.knowledge_entries for all to service_role using (true) with check (true);

create index if not exists idx_knowledge_entries_domain on public.knowledge_entries(domain);

create index if not exists idx_knowledge_entries_embedding
    on public.knowledge_entries using ivfflat (embedding vector_cosine_ops) with (lists = 8);

-- Server-side cosine similarity search (RD-03).
-- similarity = 1 - cosine distance, filtered by the
-- relevance threshold, best matches first, capped at
-- match_count. domain_filter is optional.
create or replace function public.knowledge_search(
    query_embedding vector(384),
    match_threshold float default 0.35,
    match_count int default 5,
    domain_filter text default null
)
returns table (
    id uuid,
    domain text,
    content text,
    source text,
    metadata jsonb,
    created_at timestamp with time zone,
    similarity float
)
language sql stable
as $$
    select
        ke.id,
        ke.domain,
        ke.content,
        ke.source,
        ke.metadata,
        ke.created_at,
        1 - (ke.embedding <=> query_embedding) as similarity
    from public.knowledge_entries ke
    where ke.embedding is not null
      and (domain_filter is null or ke.domain = domain_filter)
      and 1 - (ke.embedding <=> query_embedding) >= match_threshold
    order by ke.embedding <=> query_embedding
    limit match_count;
$$;
