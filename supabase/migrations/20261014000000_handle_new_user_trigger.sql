-- handle_new_user trigger: ensures every auth.users row gets a public.profiles
-- row on signup, so a registered account never lacks a profile record. Without
-- it Supabase created auth.users rows on signup while public.profiles stayed
-- empty, yielding GET /api/v1/profiles/<id> -> 404. Migration-set overview:
-- docs/development/setup.md §3.
--
-- Idempotent: safe to run repeatedly (create or replace / drop trigger if
-- exists / on conflict do nothing). Never drops anything.

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
begin
  insert into public.profiles (user_id, email, full_name)
  values (
    new.id,
    coalesce(new.email, ''),
    -- Frontend may send either key; older payloads used 'name'.
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', '')
  )
  -- A profile for this user can already exist (e.g. created via
  -- POST /api/v1/profiles in a race with this trigger) — never fail signup.
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row
  execute function public.handle_new_user();

-- Backfill: users that signed up before this trigger existed had no profile
-- row at all. Create them now from their auth metadata.
insert into public.profiles (user_id, email, full_name)
select
  u.id,
  coalesce(u.email, ''),
  coalesce(u.raw_user_meta_data ->> 'full_name', u.raw_user_meta_data ->> 'name', '')
from auth.users u
where u.email is not null
  and not exists (select 1 from public.profiles p where p.user_id = u.id)
on conflict (user_id) do nothing;
