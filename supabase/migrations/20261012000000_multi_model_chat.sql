-- Multi-model chat (Issue 4) + workspace language on chat sessions.
--
-- Adds:
--   * chat_sessions.language — the language the assistant answers in, so a
--     session's prompt contracts and the UI locale cannot drift apart.
--   * chat_messages.routing — per-message routing audit: which model answered,
--     whether it was auto-selected or a manual override, the fallback chain
--     tried, and whether the output contract passed or had to be repaired.
--
-- Both columns are additive with defaults, so existing rows stay valid.

alter table public.chat_sessions
    add column if not exists language text not null default 'en'
    check (language in ('en', 'de', 'fr'));

alter table public.chat_messages
    add column if not exists routing jsonb not null default '{}'::jsonb;

comment on column public.chat_sessions.language is
    'Language the assistant answers in (i18n locale of the session owner).';

comment on column public.chat_messages.routing is
    'Routing audit for this assistant message: selected model, auto vs manual override, fallback chain, contract pass/repair/fallback.';

-- chat_sessions as updated above, with the new language default applied.
