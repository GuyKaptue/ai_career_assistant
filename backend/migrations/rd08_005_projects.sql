-- RD-08 migration 005 (idempotent): application projects.

create table if not exists projects (
    id                      text primary key,
    user_id                 text not null,
    name                    text not null,
    status                  text not null default 'draft'
                            check (status in ('draft','researching','applied','archived')),
    template_id             text not null default 'professional',
    cover_letter_template_id text not null default 'classic-letter',
    position                jsonb,
    match                   jsonb,
    cv_document_id          text,
    cover_letter_document_id text,
    application_id          text,
    created_at              timestamptz not null default now(),
    updated_at              timestamptz not null default now()
);


create index if not exists projects_user_idx on projects (user_id, updated_at desc);

alter table projects enable row level security;

notify pgrst, 'reload schema';
