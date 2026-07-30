-- Migration: put the specimen-photos bucket's policies under version control.
--
-- Run this in the Supabase SQL Editor. Safe to re-run.
--
-- Why this exists
-- ---------------
-- Every other policy this app depends on lives in sql/. The specimen-photos INSERT and
-- SELECT policies did not: they were created by hand in the dashboard, which
-- sql/add_delete_policies.sql notes in passing ("The INSERT/SELECT policies for this
-- bucket were created by hand ... so only the missing one is added here"). A policy that
-- exists only in the dashboard cannot be reviewed, diffed, or restored, and there is no
-- record of which role it was granted to.
--
-- That matters because photo upload broke: the app's uploads reached Storage carrying the
-- anon key rather than the signed-in user's token, and Storage rejected each one with
-- "new row violates row-level security policy". The client-side half of that is fixed in
-- utils/auth.py::_apply_storage_token(). This file is the server-side half — it states,
-- in a file that can be re-run, that uploading requires an authenticated user and reading
-- does not.
--
-- Deleting is left to sql/add_delete_policies.sql, which already owns it. Running both is
-- fine in either order; neither drops the other's policy.

-- ---------------------------------------------------------------------------
-- Pre-flight: what is actually there right now.
-- ---------------------------------------------------------------------------
-- Read this before the statements below change anything. If a policy here is granted to
-- `{anon}`, uploads were succeeding without a logged-in user and anyone holding the
-- publishable key could write to the bucket.
select policyname, cmd as command, roles, qual as using_expr, with_check
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and (qual like '%specimen-photos%' or with_check like '%specimen-photos%')
order by cmd, policyname;

-- The bucket must exist and be public: the app stores get_public_url() results on the row
-- and renders them directly, with no signed-URL step. `public` false would leave every
-- photo already recorded pointing at a 400.
select id, name, public, created_at from storage.buckets where id = 'specimen-photos';

-- ---------------------------------------------------------------------------
-- The policies.
-- ---------------------------------------------------------------------------
-- Created here rather than assumed, so a project restored from scratch works. Mirrors the
-- profile-avatars bucket in sql/add_investigator_profiles.sql.
insert into storage.buckets (id, name, public)
values ('specimen-photos', 'specimen-photos', true)
on conflict (id) do update set public = true;

-- Upload. `to authenticated` is the point of this file: a specimen photo is evidence
-- attached to a collection event, and an unauthenticated writer could fill the bucket with
-- objects no record accounts for. utils/auth.py must send the user's access token for this
-- to pass — pinned by tests/test_supabase_client_wiring.py.
drop policy if exists "Authenticated users can upload specimen photos" on storage.objects;
create policy "Authenticated users can upload specimen photos"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'specimen-photos');

-- Read. Public, matching the bucket: the stored public URLs are fetched by the browser
-- with no token, including from the reports and dashboard pages.
drop policy if exists "Public read access for specimen photos" on storage.objects;
create policy "Public read access for specimen photos"
  on storage.objects for select to public
  using (bucket_id = 'specimen-photos');

-- Deliberately NOT added: UPDATE. Nothing in the app overwrites a photo object — a new
-- photo is uploaded under a fresh uuid path (utils/data_manager.py::_upload_photo_bytes),
-- and the old object is removed by the deletion path, not replaced in place.

-- ---------------------------------------------------------------------------
-- Confirm.
-- ---------------------------------------------------------------------------
-- Expect: INSERT to {authenticated}, SELECT to {public}, and — once
-- sql/add_delete_policies.sql has also been run — DELETE to {authenticated}.
select policyname, cmd as command, roles
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and (qual like '%specimen-photos%' or with_check like '%specimen-photos%')
order by cmd, policyname;

-- An upload still failing after this is a client problem, not a policy one: the request is
-- arriving as `anon`. Check that utils/auth.py::_apply_storage_token() is being applied to
-- the client doing the upload.
