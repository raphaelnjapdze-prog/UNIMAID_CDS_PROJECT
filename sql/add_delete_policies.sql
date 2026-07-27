-- Migration: allow the app to delete trial/demo entries.
--
-- Run this in the Supabase SQL Editor. Safe to re-run.
--
-- Why this exists
-- ---------------
-- sql/add_update_policies.sql added a DELETE policy on specimen_records, but only for
-- vial_out_specimens()'s rollback path, and it deliberately left the two side tables
-- alone: "Deliberately NOT added: update/delete on bioassay_results and clinical_case_data.
-- The app only ever inserts and reads those... Add them if and when an edit feature
-- exists." A delete feature now exists (utils/data_manager.py, DELETION section), so this
-- adds what it needs.
--
-- Under RLS a DELETE with no matching policy does not raise — it matches zero rows and
-- silently reports success. That is how the app could appear to clear a trial run while
-- every row stayed in the table. The delete helpers now verify the rows the database
-- actually returned and refuse to claim a deletion they cannot see, but they still need
-- these policies to do the work.

-- Storage objects are a separate policy surface from table rows. Without a DELETE policy
-- on the bucket, photos survive every attempt to remove them: they keep counting against
-- storage and stay reachable by their public URL long after the record citing them is
-- gone. (The INSERT/SELECT policies for this bucket were created by hand — see the note
-- in sql/add_investigator_profiles.sql — so only the missing one is added here.)
drop policy if exists "Authenticated users can delete specimen photos" on storage.objects;
create policy "Authenticated users can delete specimen photos"
  on storage.objects
  for delete
  to authenticated
  using (bucket_id = 'specimen-photos');

-- Bioassay replicates: needed to reset a trial run.
drop policy if exists "Authenticated users can delete bioassay results" on public.bioassay_results;
create policy "Authenticated users can delete bioassay results"
  on public.bioassay_results
  for delete
  to authenticated
  using (true);

-- Clinical case counts: same.
drop policy if exists "Authenticated users can delete clinical case data" on public.clinical_case_data;
create policy "Authenticated users can delete clinical case data"
  on public.clinical_case_data
  for delete
  to authenticated
  using (true);

-- specimen_records already has a DELETE policy from sql/add_update_policies.sql. Recreated
-- here so a database that never ran that migration is not left half-configured — this file
-- alone is enough to make deletion work.
drop policy if exists "Authenticated users can delete specimen records" on public.specimen_records;
create policy "Authenticated users can delete specimen records"
  on public.specimen_records
  for delete
  to authenticated
  using (true);

-- Still deliberately NOT added: UPDATE on bioassay_results or clinical_case_data. Nothing
-- edits those rows — the app inserts, reads, and now deletes them. Granting update would
-- widen the surface for no caller.

-- Confirm: each of the three tables should list a DELETE policy, plus one on
-- storage.objects for the specimen-photos bucket.
select schemaname, tablename, policyname, cmd as command, roles
from pg_policies
where (schemaname = 'public'
        and tablename in ('specimen_records', 'bioassay_results', 'clinical_case_data'))
   or (schemaname = 'storage' and tablename = 'objects' and policyname ilike '%specimen photos%')
order by schemaname, tablename, cmd;
