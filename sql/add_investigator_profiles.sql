-- Migration: store investigator profiles in the database, not on the app's disk.
--
-- components/profile.py wrote each profile to data/profiles/<uid>_profile.json and its
-- avatar to a .png beside it. Streamlit Cloud's filesystem is ephemeral: every reboot and
-- every redeploy wipes the container, so a user's profile and photo silently disappeared.
--
-- Safe to run on an existing database. Run it in the Supabase SQL Editor.

create table if not exists public.investigator_profiles (
    user_id     text primary key,
    profile     jsonb not null default '{}'::jsonb,
    avatar_url  text,
    updated_at  timestamptz not null default now()
);

alter table public.investigator_profiles enable row level security;

-- Teammates can see each other's profiles (a surveillance team needs to know who is who),
-- but nobody may write to a profile that is not their own. The previous file-based scheme
-- namespaced by uid for exactly this reason; here the database enforces it.
drop policy if exists "Authenticated users can read profiles" on public.investigator_profiles;
create policy "Authenticated users can read profiles"
  on public.investigator_profiles for select to authenticated
  using (true);

drop policy if exists "Users can insert their own profile" on public.investigator_profiles;
create policy "Users can insert their own profile"
  on public.investigator_profiles for insert to authenticated
  with check (user_id = auth.uid()::text);

drop policy if exists "Users can update their own profile" on public.investigator_profiles;
create policy "Users can update their own profile"
  on public.investigator_profiles for update to authenticated
  using (user_id = auth.uid()::text)
  with check (user_id = auth.uid()::text);

-- Avatars: a public-read bucket, writable only by the signed-in user, mirroring the
-- specimen-photos setup (the app renders the returned public URL directly and does not
-- generate signed URLs).
insert into storage.buckets (id, name, public)
values ('profile-avatars', 'profile-avatars', true)
on conflict (id) do nothing;

drop policy if exists "Authenticated users can upload avatars" on storage.objects;
create policy "Authenticated users can upload avatars"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'profile-avatars');

drop policy if exists "Authenticated users can replace avatars" on storage.objects;
create policy "Authenticated users can replace avatars"
  on storage.objects for update to authenticated
  using (bucket_id = 'profile-avatars');

drop policy if exists "Public read access for avatars" on storage.objects;
create policy "Public read access for avatars"
  on storage.objects for select to public
  using (bucket_id = 'profile-avatars');

-- Confirm.
select 'table' as kind, tablename as name from pg_tables
 where schemaname = 'public' and tablename = 'investigator_profiles'
union all
select 'bucket', id from storage.buckets where id = 'profile-avatars';
