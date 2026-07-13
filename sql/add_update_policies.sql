-- Migration: allow the UPDATE/DELETE the app actually performs.
--
-- specimen_records had RLS enabled with only INSERT and SELECT policies. Under RLS an
-- UPDATE with no matching policy does not raise — it matches zero rows and silently does
-- nothing. Every update path in the app was therefore a no-op in production:
--
--   * attach_identification_to_specimen() — identifying a vialed-out specimen (caught and
--     surfaced as an error, so it was visibly broken)
--   * upsert_specimen_record() — PCR confirmation onto an existing row
--   * vial_out_specimens() — inserts the children, then updates the batch's vialed_out
--     tally. The insert is permitted and the update is not, so the batch keeps its full
--     raw counts while each child also contributes 1: the same mosquitoes counted twice,
--     which is exactly the invariant subsampling exists to prevent. This one reported
--     success.
--
-- DELETE is needed for vial_out_specimens()'s rollback path: if the tally update fails it
-- deletes the children it just created, so the batch tally and the child rows can never
-- disagree. Without a DELETE policy that rollback silently fails and leaves orphans.
--
-- Safe to run on an existing database. Run it in the Supabase SQL Editor.

-- Identifications, PCR confirmations, and batch tally updates.
drop policy if exists "Authenticated users can update specimen records" on public.specimen_records;
create policy "Authenticated users can update specimen records"
  on public.specimen_records
  for update
  to authenticated
  using (true)
  with check (true);

-- Rollback of vialed-out children when the batch tally update fails.
drop policy if exists "Authenticated users can delete specimen records" on public.specimen_records;
create policy "Authenticated users can delete specimen records"
  on public.specimen_records
  for delete
  to authenticated
  using (true);

-- Deliberately NOT added: update/delete on bioassay_results and clinical_case_data. The
-- app only ever inserts and reads those, so granting more would widen the surface for no
-- reason. Add them if and when an edit feature exists.

-- Confirm: specimen_records should now list INSERT, SELECT, UPDATE and DELETE.
select tablename, policyname, cmd as command, roles
from pg_policies
where schemaname = 'public'
  and tablename in ('specimen_records','bioassay_results','clinical_case_data')
order by tablename, cmd;
