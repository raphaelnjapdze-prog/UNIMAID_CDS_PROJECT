-- Migration: a user may delete only their own entries; admins may delete any.
--
-- Run this in the Supabase SQL Editor. Safe to re-run.
--
-- Why this exists
-- ---------------
-- sql/add_delete_policies.sql granted DELETE to every authenticated user with
-- `using (true)`. That made deletion work at all, which was the problem it was solving,
-- but it means any signed-in account can delete any row in the project — including a
-- colleague's field data. The app's UI never offered to do that, but RLS is the only
-- thing that actually prevents it: the anon key and a user's own JWT are enough to call
-- the REST API directly, so a policy of `true` is the whole story.
--
-- This replaces those policies with ownership:
--
--     you may delete a row if you recorded it, or if you are a registered admin.
--
-- Ownership columns already exist and are already non-blank (sql/enforce_collector_id.sql):
--   specimen_records.collector_id   -- the auth uid, as text
--   bioassay_results.submitted_by
--   clinical_case_data.submitted_by
--
-- Two consequences worth knowing before you run this:
--
--   * Rows marked 'unattributed-legacy' predate identity tracking. They match no user, so
--     only an admin can delete them. That is correct — nobody can claim them.
--   * submitted_by is nullable on both side tables. Any existing row with a NULL there has
--     no owner and becomes admin-only to delete. The query at the bottom counts them so
--     you know what you are looking at.

-- 1. Who is an admin.
--
-- A table, not a flag on the user, and not a passkey: the passkey the app asks for before
-- a bulk wipe is a confirmation step in the UI, and the UI is not a security boundary.
-- This is.
create table if not exists public.app_admins (
  user_id    uuid primary key,
  note       text,
  added_at   timestamptz not null default now()
);

alter table public.app_admins enable row level security;

-- A user may read their own row and nothing else. That is enough for the app to answer
-- "am I an admin?" without publishing the roster to every signed-in account.
drop policy if exists "A user can read their own admin row" on public.app_admins;
create policy "A user can read their own admin row"
  on public.app_admins
  for select
  to authenticated
  using (user_id = auth.uid());

-- Deliberately NO insert/update/delete policy. Admins are added here, in the SQL editor,
-- with the service role. Without a write policy a compromised session cannot promote
-- itself to admin and then delete the project.

-- 2. The membership test, as a function.
--
-- SECURITY DEFINER so the check runs past app_admins' own RLS: a policy that had to read
-- app_admins as the calling user would be answerable only for that user's row, which
-- happens to work here but breaks the moment the table's own policy is tightened. Pinning
-- search_path stops a rogue `public` object from shadowing the table inside a definer
-- function.
create or replace function public.is_app_admin()
  returns boolean
  language sql
  stable
  security definer
  set search_path = public
as $$
  select exists (select 1 from public.app_admins where user_id = auth.uid());
$$;

revoke all on function public.is_app_admin() from public;
grant execute on function public.is_app_admin() to authenticated;

-- 3. Ownership on the three tables.
--
-- collector_id is text and auth.uid() is uuid, hence the cast. It is on the uid rather
-- than the column so the comparison stays sargable and a malformed collector_id (there
-- are none — see enforce_collector_id.sql — but still) cannot raise on cast.

drop policy if exists "Authenticated users can delete specimen records" on public.specimen_records;
drop policy if exists "Users delete their own specimen records" on public.specimen_records;
create policy "Users delete their own specimen records"
  on public.specimen_records
  for delete
  to authenticated
  using (collector_id = auth.uid()::text or public.is_app_admin());

drop policy if exists "Authenticated users can delete bioassay results" on public.bioassay_results;
drop policy if exists "Users delete their own bioassay results" on public.bioassay_results;
create policy "Users delete their own bioassay results"
  on public.bioassay_results
  for delete
  to authenticated
  using (submitted_by = auth.uid()::text or public.is_app_admin());

drop policy if exists "Authenticated users can delete clinical case data" on public.clinical_case_data;
drop policy if exists "Users delete their own clinical case data" on public.clinical_case_data;
create policy "Users delete their own clinical case data"
  on public.clinical_case_data
  for delete
  to authenticated
  using (submitted_by = auth.uid()::text or public.is_app_admin());

-- 4. What this migration deliberately does NOT change.
--
-- storage.objects: the DELETE policy on the specimen-photos bucket stays open to any
-- authenticated user. Ownership cannot be expressed there yet — objects are stored at
-- '{specimen_id}/{uuid}.ext' with no owner in the path, and the app deletes a row before
-- its photos, so a policy joining back to specimen_records would find the row already
-- gone and refuse every legitimate delete. Deleting someone else's photo therefore
-- requires already knowing its object path. Closing this properly means putting the owner
-- in the path and migrating the existing objects; it is a separate piece of work.
--
-- UPDATE policies: untouched. Identifying a specimen vialed out of someone else's batch
-- is a normal collaboration, and attach_identification_to_specimen() depends on it.
-- Ownership on UPDATE would break that; deletion is the destructive verb.

-- 5. Register yourself as the first admin.
--
-- Find your uid: Supabase dashboard -> Authentication -> Users, or
--   select id, email from auth.users order by created_at;
-- Then uncomment and run:
--
-- insert into public.app_admins (user_id, note)
-- values ('00000000-0000-0000-0000-000000000000', 'Raphael — project owner')
-- on conflict (user_id) do nothing;

-- 6. Confirm.
--
-- Each of the three tables should list exactly one DELETE policy, and its qualifier
-- should mention auth.uid() rather than reading `true`.
select tablename, policyname, cmd as command, qual as using_expression
from pg_policies
where schemaname = 'public'
  and tablename in ('specimen_records', 'bioassay_results', 'clinical_case_data')
  and cmd = 'DELETE'
order by tablename;

-- How many rows nobody can claim — these are admin-only to delete from now on.
select 'specimen_records' as table_name,
       count(*) filter (where collector_id = 'unattributed-legacy') as ownerless
from public.specimen_records
union all
select 'bioassay_results', count(*) filter (where submitted_by is null)
from public.bioassay_results
union all
select 'clinical_case_data', count(*) filter (where submitted_by is null)
from public.clinical_case_data;
