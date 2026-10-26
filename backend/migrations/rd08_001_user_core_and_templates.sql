-- RD-08 migration 001 (Supabase/PostgreSQL, idempotent). Review before applying.
-- Assumption: existing tables use text user_id (NOT verifiable from the zip: the
-- original SQL migrations are not part of it). Adjust the type if yours is uuid.

-- 1) User-data core: the structured fields the frontend collects (profiles only has
--    email/full_name/target_role/location/summary today).
create table if not exists profile_preferences (
    user_id                      text primary key,
    target_titles                jsonb not null default '[]'::jsonb,
    target_industries            jsonb not null default '[]'::jsonb,
    preferred_locations          jsonb not null default '[]'::jsonb,
    remote_policy                text  check (remote_policy in ('onsite','hybrid','remote','any')),
    employment_types             jsonb not null default '[]'::jsonb,
    salary_min                   integer check (salary_min >= 0),
    salary_max                   integer check (salary_max >= 0),
    salary_currency              text,
    seniority                    text,
    work_authorization           text,
    notice_period_days           integer check (notice_period_days >= 0),
    must_haves                   jsonb not null default '[]'::jsonb,
    deal_breakers                jsonb not null default '[]'::jsonb,
    default_cv_template_id       text,
    default_cover_letter_template_id text,
    preferred_model_id           text,            -- manual pin; null = auto-select
    created_at                   timestamptz not null default now(),
    updated_at                   timestamptz not null default now()
);

-- 2) User-created or edited templates (the built-in 19 stay in code).
create table if not exists user_templates (
    id               text primary key,
    user_id          text not null,
    kind             text not null check (kind in ('cv','cover_letter')),
    base_template_id text,
    name             text not null,
    structure_type   text,
    tone             text,
    language         text check (language in ('en','de','fr')),
    content          jsonb not null default '{}'::jsonb,
    created_at       timestamptz not null default now(),
    updated_at       timestamptz not null default now()
);
create index if not exists user_templates_user_idx on user_templates (user_id, kind);

-- 3) Per-job override already exists: projects.template_id and
--    projects.cover_letter_template_id. Overrides must never write to
--    profile_preferences.default_*; that is enforced in code and tested.
