-- Chat platform: conversation sessions and messages.
--
-- A session is a conversation thread owned by one user (auth.users.id).
-- Messages alternate user/assistant; assistant messages record the model
-- that produced them, optional source citations, and an optional artifact
-- payload (CV / cover letter / analysis preview rendered side-by-side in
-- the UI). Retrieval and RAG stay user-scoped: a user only ever sees their
-- own threads and messages (RLS). Foreign sessions return nothing.

create table if not exists public.chat_sessions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    title text not null default 'New chat',
    model_id text,
    mode text not null default 'general'
        check (mode in ('general', 'cv_builder', 'cover_letter', 'ats_checker', 'job_search', 'interview_prep')),
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

create table if not exists public.chat_messages (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references public.chat_sessions(id) on delete cascade,
    role text not null check (role in ('user', 'assistant', 'system')),
    content text not null,
    model_id text,
    citations jsonb not null default '[]'::jsonb,
    artifact jsonb,
    created_at timestamp with time zone default now()
);

alter table public.chat_sessions enable row level security;
alter table public.chat_messages enable row level security;

create policy "Users can view their own chat sessions" on public.chat_sessions
for select to authenticated using ((select auth.uid()) = user_id);

create policy "Users can insert their own chat sessions" on public.chat_sessions
for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "Users can update their own chat sessions" on public.chat_sessions
for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "Users can delete their own chat sessions" on public.chat_sessions
for delete to authenticated using ((select auth.uid()) = user_id);

-- Messages inherit ownership through their session. A user can read/write a
-- message only when the parent session belongs to them.
create policy "Users can view messages in their own sessions" on public.chat_messages
for select to authenticated using (
    exists (
        select 1 from public.chat_sessions s
        where s.id = chat_messages.session_id and s.user_id = (select auth.uid())
    )
);

create policy "Users can insert messages in their own sessions" on public.chat_messages
for insert to authenticated with check (
    exists (
        select 1 from public.chat_sessions s
        where s.id = chat_messages.session_id and s.user_id = (select auth.uid())
    )
);

create policy "Users can update messages in their own sessions" on public.chat_messages
for update to authenticated using (
    exists (
        select 1 from public.chat_sessions s
        where s.id = chat_messages.session_id and s.user_id = (select auth.uid())
    )
) with check (
    exists (
        select 1 from public.chat_sessions s
        where s.id = chat_messages.session_id and s.user_id = (select auth.uid())
    )
);

create policy "Users can delete messages in their own sessions" on public.chat_messages
for delete to authenticated using (
    exists (
        select 1 from public.chat_sessions s
        where s.id = chat_messages.session_id and s.user_id = (select auth.uid())
    )
);

create index if not exists idx_chat_sessions_user_id on public.chat_sessions(user_id);
create index if not exists idx_chat_sessions_updated_at on public.chat_sessions(updated_at desc);
create index if not exists idx_chat_messages_session_id on public.chat_messages(session_id);
create index if not exists idx_chat_messages_created_at on public.chat_messages(created_at);
