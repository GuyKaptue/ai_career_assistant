create extension if not exists pgcrypto;

create table if not exists public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    email text unique not null,
    full_name text not null default '',
    target_role text not null default '',
    location text not null default '',
    summary text not null default '',
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

create table if not exists public.documents (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    document_type text not null check (document_type in ('cv', 'cover_letter', 'resignation')),
    title text not null,
    content text not null,
    template_id text not null default 'professional',
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

create table if not exists public.job_applications (
    application_id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    company text not null,
    position text not null,
    status text not null default 'applied' check (status in ('applied', 'interview', 'offer', 'rejected')),
    job_url text,
    notes text not null default '',
    applied_date timestamp with time zone default now(),
    follow_up_date timestamp with time zone,
    created_at timestamp with time zone default now(),
    updated_at timestamp with time zone default now()
);

alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.job_applications enable row level security;

create policy "Users can view their own profile" on public.profiles
for select to authenticated using ((select auth.uid()) = user_id);

create policy "Users can update their own profile" on public.profiles
for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "Users can insert their own profile" on public.profiles
for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "Users can view their own documents" on public.documents
for select to authenticated using ((select auth.uid()) = user_id);

create policy "Users can insert their own documents" on public.documents
for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "Users can update their own documents" on public.documents
for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "Users can delete their own documents" on public.documents
for delete to authenticated using ((select auth.uid()) = user_id);

create policy "Users can view their own applications" on public.job_applications
for select to authenticated using ((select auth.uid()) = user_id);

create policy "Users can insert their own applications" on public.job_applications
for insert to authenticated with check ((select auth.uid()) = user_id);

create policy "Users can update their own applications" on public.job_applications
for update to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

create policy "Users can delete their own applications" on public.job_applications
for delete to authenticated using ((select auth.uid()) = user_id);

create index if not exists idx_profiles_email on public.profiles(email);
create index if not exists idx_documents_user_id on public.documents(user_id);
create index if not exists idx_documents_type on public.documents(document_type);
create index if not exists idx_applications_user_id on public.job_applications(user_id);
create index if not exists idx_applications_status on public.job_applications(status);
