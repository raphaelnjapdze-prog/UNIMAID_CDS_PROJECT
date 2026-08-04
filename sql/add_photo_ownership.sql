-- Migration: ownership-scope the specimen-photos bucket.
--
-- Run this in the Supabase SQL Editor. Safe to re-run.
--
-- ORDER MATTERS: migrate the existing objects FIRST, with
--   python scripts/migrate_photo_paths.py --apply
-- and only then run this file. See "Legacy objects" below for what happens if you don't —
-- it is recoverable, not destructive, but it will look like deletion has broken.
--
-- Why this exists
-- ---------------
-- sql/add_ownership_delete_policies.sql scoped deletion of the three tables to
-- "your own rows, or any row if you are a registered admin", and explicitly left this
-- bucket open: any authenticated user held DELETE on every object in it. Two things
-- blocked the obvious fix at the time, and this migration removes the first, which was
-- what made the second unfixable:
--
--   * Objects were stored at '{specimen_id}/{uuid}.ext'. No owner appears anywhere in
--     that path, so a policy could not tell whose photo it was looking at.
--   * The app deletes a specimen row *before* its photos (utils/data_manager.py — the
--     row must go first so a blocked photo delete can never leave a row citing a URL
--     that no longer resolves). A policy that joined storage.objects back to
--     specimen_records to find the owner would therefore find the row already gone and
--     refuse every legitimate delete.
--
-- Putting the owner in the path settles both at once: the check becomes local to the
-- object, needing no other row to still exist. utils/data_manager.py::_upload_photo_bytes
-- now writes '{collector_id}/{specimen_id}/{uuid}.ext', and storage.foldername(name)[1]
-- is that collector_id.
--
-- This is the last piece of the deletion boundary. With it, "you may delete what you
-- recorded; an admin may delete anything" holds for photo objects as well as rows.

-- ---------------------------------------------------------------------------
-- Pre-flight: what is there right now.
-- ---------------------------------------------------------------------------
-- Read this before anything below changes it. The DELETE policy should currently read
-- `bucket_id = 'specimen-photos'` with no owner test — that is what this file replaces.
select policyname, cmd as command, roles, qual as using_expr, with_check
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and (qual like '%specimen-photos%' or with_check like '%specimen-photos%')
order by cmd, policyname;

-- How many objects are still on the legacy two-segment path. This must be 0 before the
-- policies below are worth anything: run scripts/migrate_photo_paths.py --apply until it
-- is. A non-zero count here is not a failure of this migration, it just means the objects
-- it is about to scope have not been moved into the shape it scopes them by.
select
  count(*) filter (where array_length(storage.foldername(name), 1) >= 2) as owner_prefixed,
  count(*) filter (where array_length(storage.foldername(name), 1) < 2)  as legacy_flat,
  count(*)                                                               as total
from storage.objects
where bucket_id = 'specimen-photos';

-- ---------------------------------------------------------------------------
-- The policies.
-- ---------------------------------------------------------------------------

-- Upload. Tightened from "any authenticated user may write anywhere in the bucket" to
-- "only under your own id". Without this half, ownership in the path means nothing: a
-- user could upload directly into someone else's prefix and then delete it, since the
-- DELETE policy below would read that prefix and agree it was theirs.
drop policy if exists "Authenticated users can upload specimen photos" on storage.objects;
drop policy if exists "Users upload specimen photos under their own id" on storage.objects;
create policy "Users upload specimen photos under their own id"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'specimen-photos'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- Read stays public, matching the bucket and the rest of the app: the stored public URLs
-- are fetched by the browser with no token, from the reports and dashboard pages. Nothing
-- about ownership changes who may *look* at a specimen photo.
drop policy if exists "Public read access for specimen photos" on storage.objects;
create policy "Public read access for specimen photos"
  on storage.objects for select to public
  using (bucket_id = 'specimen-photos');

-- Delete. The point of the file. Mirrors the rule the three tables already use, so there
-- is one sentence to remember rather than one per surface.
drop policy if exists "Authenticated users can delete specimen photos" on storage.objects;
drop policy if exists "Users delete their own specimen photos" on storage.objects;
create policy "Users delete their own specimen photos"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'specimen-photos'
    and (
      (storage.foldername(name))[1] = auth.uid()::text
      or public.is_app_admin()
    )
  );

-- Still deliberately NOT added: UPDATE. Nothing in the app overwrites a photo object — a
-- new photo goes to a fresh uuid path. The one process that does move objects is
-- scripts/migrate_photo_paths.py, which runs with the service role and bypasses RLS.

-- ---------------------------------------------------------------------------
-- Legacy objects
-- ---------------------------------------------------------------------------
-- An object still at '{specimen_id}/{uuid}.ext' has a first path segment that is a
-- specimen id, not a uid. It therefore matches no user under the DELETE policy above and
-- becomes admin-only to remove.
--
-- That is the safe direction to fail — nothing is deleted that should not be, and
-- delete_specimen_photos() already counts what the bucket declined and surfaces it as
-- photos_orphaned rather than reporting a cleanup that did not happen. But it does mean a
-- non-admin clearing their own old entries will see "N photo(s) are still in storage"
-- until the objects are migrated. Run scripts/migrate_photo_paths.py --apply.

-- ---------------------------------------------------------------------------
-- Confirm.
-- ---------------------------------------------------------------------------
-- Expect exactly three policies: INSERT and DELETE to {authenticated}, both mentioning
-- auth.uid(), and SELECT to {public}. A DELETE qualifier that still reads only
-- `bucket_id = 'specimen-photos'` means this file did not take.
select policyname, cmd as command, roles, qual as using_expr, with_check
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and (qual like '%specimen-photos%' or with_check like '%specimen-photos%')
order by cmd, policyname;

-- And the objects themselves: legacy_flat should now be 0.
select
  count(*) filter (where array_length(storage.foldername(name), 1) >= 2) as owner_prefixed,
  count(*) filter (where array_length(storage.foldername(name), 1) < 2)  as legacy_flat
from storage.objects
where bucket_id = 'specimen-photos';

-- Objects whose owning prefix matches no real user — orphaned by a deleted account, or
-- left by a migration that could not resolve a collector. Admin-only to delete, by the
-- policy above. Expect zero rows.
select (storage.foldername(name))[1] as owner_prefix, count(*) as objects
from storage.objects
where bucket_id = 'specimen-photos'
  and array_length(storage.foldername(name), 1) >= 2
  and not exists (
    select 1 from auth.users u
    where u.id::text = (storage.foldername(name))[1]
  )
group by 1
order by 2 desc;
