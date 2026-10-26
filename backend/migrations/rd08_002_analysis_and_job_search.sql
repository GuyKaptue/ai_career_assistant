-- RD-08 migration 002 (idempotent). Candidate analysis cache and job-search history.

create table if not exists candidate_analyses (
    id              text primary key,
    user_id         text not null,
    cv_document_id  text,
    input_hash      text not null,            -- sha256 of the normalized user-data core
    analysis        jsonb not null,           -- validated candidate-analysis JSON
    schema_version  text not null,
    prompt_version  text not null,
    model_id        text,
    created_at      timestamptz not null default now(),
    unique (user_id, input_hash, schema_version)
);

create table if not exists job_search_runs (
    id          text primary key,
    user_id     text not null,
    analysis_id text references candidate_analyses(id) on delete set null,
    queries     jsonb not null default '[]'::jsonb,   -- built by code from analysis keys
    providers   jsonb not null default '[]'::jsonb,   -- providers actually queried
    created_at  timestamptz not null default now()
);
create index if not exists job_search_runs_user_idx on job_search_runs (user_id, created_at desc);

create table if not exists job_search_matches (
    run_id    text not null references job_search_runs(id) on delete cascade,
    job_key   text not null,                  -- same key as job_applications.job_key
    provider  text not null,
    title     text not null,
    company   text,
    url       text,                           -- only ever copied from the provider response
    score     real check (score between 0 and 1),   -- computed by code, never by the LLM
    decision  text check (decision in ('accepted','rejected')),
    primary key (run_id, job_key)
);

-- Row level security: deny anon/authenticated by default; the backend uses the service role.
alter table profile_preferences  enable row level security;
alter table user_templates       enable row level security;
alter table candidate_analyses   enable row level security;
alter table job_search_runs      enable row level security;
alter table job_search_matches   enable row level security;
