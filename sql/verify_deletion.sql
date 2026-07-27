-- Verify that deletion actually works — run in the Supabase SQL Editor.
--
-- Nothing here changes your data. Sections 2 and 3 are read-only; section 4 runs inside
-- `begin … rollback`, so the rows it creates and deletes never persist. Run the whole file
-- at once and read the PASS/FAIL column of each result.
--
-- WHY THIS FILE EXISTS
-- The failure it checks for is silent. Under row-level security a DELETE (or UPDATE) with
-- no matching policy does not raise — it matches zero rows and reports success. That is how
-- the app could appear to clear a trial run while every row stayed in the table. The app
-- now verifies the rows the database returns rather than trusting the call, but it still
-- needs the policies to exist. This file confirms they do, as the role the app actually
-- uses, without needing to sign into the app.
--
-- RUN THE MIGRATIONS FIRST, in this order:
--   1. sql/add_update_policies.sql
--   2. sql/add_delete_policies.sql
--   3. sql/create_bioassay_results.sql      (optional — see section 1 before its
--   4. sql/create_clinical_case_data.sql     CHECK-constraint sections)

-- =====================================================================================
-- 1. PRE-FLIGHT: would the CHECK constraints in the two schema files fail?
-- =====================================================================================
-- Adding a CHECK to a table with a violating row fails outright. These must both read 0
-- before you run section 4 of create_bioassay_results.sql / create_clinical_case_data.sql.
-- A violation is bad data, not a constraint to relax: more dead mosquitoes than were
-- exposed, or fewer suspected cases than confirmed, is a measurement error.
select
  'bioassay_results' as table_name,
  count(*) as violating_rows,
  case when count(*) = 0 then 'SAFE to add constraints'
       else 'FIX THESE ROWS FIRST' end as verdict
from public.bioassay_results
where mosquitoes_exposed is null or mosquitoes_exposed <= 0
   or mortality_24hr is null or mortality_24hr < 0
   or mortality_24hr > mosquitoes_exposed
   or (knockdown_60min is not null
       and (knockdown_60min < 0 or knockdown_60min > mosquitoes_exposed))
   or replicate_number is null or replicate_number <= 0
   or concentration_pct is null or concentration_pct < 0
union all
select
  'clinical_case_data',
  count(*),
  case when count(*) = 0 then 'SAFE to add constraints'
       else 'FIX THESE ROWS FIRST' end
from public.clinical_case_data
where confirmed_cases is null or confirmed_cases < 0
   or (suspected_cases is not null and suspected_cases < confirmed_cases)
   or facility_name is null or btrim(facility_name) = '';

-- =====================================================================================
-- 2. Which policies exist?
-- =====================================================================================
-- Expected after the migrations:
--   specimen_records    INSERT, SELECT, UPDATE, DELETE
--   bioassay_results    INSERT, SELECT, DELETE          (no UPDATE, by design)
--   clinical_case_data  INSERT, SELECT, DELETE          (no UPDATE, by design)
--   storage.objects     a DELETE policy for the specimen-photos bucket
select schemaname, tablename, cmd as command, policyname, roles
from pg_policies
where (schemaname = 'public'
        and tablename in ('specimen_records', 'bioassay_results', 'clinical_case_data'))
   or (schemaname = 'storage' and tablename = 'objects'
       and coalesce(qual, '') || coalesce(with_check, '') ilike '%specimen-photos%')
order by schemaname, tablename, cmd, policyname;

-- The one check that matters most, as a single verdict per table.
-- cmd = 'ALL' counts: a `for all` policy covers DELETE too, and a hand-created policy is
-- quite likely to be one. Treating only cmd = 'DELETE' as a pass would report a working
-- setup as broken.
select
  t.tablename,
  bool_or(p.cmd in ('DELETE', 'ALL')) as has_delete_policy,
  case when bool_or(p.cmd in ('DELETE', 'ALL')) then 'PASS'
       else 'FAIL — deletion will silently do nothing; run sql/add_delete_policies.sql' end
    as verdict
from (values ('specimen_records'), ('bioassay_results'), ('clinical_case_data')) as t(tablename)
left join pg_policies p
       on p.schemaname = 'public' and p.tablename = t.tablename
group by t.tablename
order by t.tablename;

-- Photo objects are a separate policy surface from table rows — this is the one that was
-- missing, which is why deleting photos and deleting rows behaved differently.
select
  case when count(*) > 0 then 'PASS'
       else 'FAIL — specimen photos cannot be deleted; run sql/add_delete_policies.sql' end
    as storage_delete_verdict
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and cmd in ('DELETE', 'ALL')
  and coalesce(qual, '') || coalesce(with_check, '') ilike '%specimen-photos%';

-- =====================================================================================
-- 3. Is RLS even switched on?
-- =====================================================================================
-- A table with policies but RLS disabled is wide open; a table with RLS on and no policies
-- is a black hole that swallows writes. Both should read `true` with policies present.
select relname as table_name, relrowsecurity as rls_enabled, relforcerowsecurity as rls_forced
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('specimen_records', 'bioassay_results', 'clinical_case_data')
order by relname;

-- =====================================================================================
-- 4. END-TO-END: delete as the app's role, then roll it all back
-- =====================================================================================
-- The SQL Editor runs as `postgres`, which owns these tables — and RLS does not apply to a
-- table's owner. Testing here as-is would pass no matter what the policies say. `set local
-- role authenticated` switches to the role the app's logged-in users actually get, so the
-- policies are genuinely exercised.
--
-- Everything is rolled back at the end. If you interrupt this section part-way, run
-- `rollback;` before doing anything else — the test rows are tagged 'delete-smoke-test'
-- and 'DELETE-SMOKE-TEST' if you ever need to find them.
begin;

set local role authenticated;

-- A batch with two individuals vialed out of it, matching the shape the app writes.
insert into public.specimen_records
  (specimen_id, collection_date, collector_id, breeding_site_type,
   field_screening_result, specimen_role)
values
  ('aaaaaaaa-0000-4000-8000-000000000001', current_date, 'delete-smoke-test', 'Stagnant pool',
   '{"screening_method":"manual_field_log",
     "result":{"anopheles_count":10,"culex_count":0,"aedes_count":0,
               "vialed_out":{"Anopheles":2}}}'::jsonb,
   'primary');

insert into public.specimen_records
  (specimen_id, parent_specimen_id, collection_date, collector_id,
   field_screening_result, specimen_role)
values
  ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000001',
   current_date, 'delete-smoke-test',
   '{"screening_method":"field_subsample","result":{"genus":"Anopheles"}}'::jsonb, 'individual'),
  ('aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000001',
   current_date, 'delete-smoke-test',
   '{"screening_method":"field_subsample","result":{"genus":"Anopheles"}}'::jsonb, 'individual');

-- 4a. UPDATE — the app decrements a batch's vialed_out tally through this. Without it,
-- deleting one vialed individual leaves that collection event short by a mosquito.
with updated as (
  update public.specimen_records
     set field_screening_result =
         jsonb_set(field_screening_result, '{result,vialed_out,Anopheles}', '1'::jsonb)
   where specimen_id = 'aaaaaaaa-0000-4000-8000-000000000001'
  returning specimen_id
)
select 'specimen_records UPDATE (batch tally restore)' as check_name,
       count(*) as rows_affected,
       case when count(*) = 1 then 'PASS'
            else 'FAIL — no UPDATE policy; run sql/add_update_policies.sql' end as verdict
from updated;

-- 4b. DELETE one child — the per-entry delete path.
with removed as (
  delete from public.specimen_records
   where specimen_id = 'aaaaaaaa-0000-4000-8000-000000000002'
  returning specimen_id
)
select 'specimen_records DELETE (one vialed individual)' as check_name,
       count(*) as rows_affected,
       case when count(*) = 1 then 'PASS'
            else 'FAIL — no DELETE policy; run sql/add_delete_policies.sql' end as verdict
from removed;

-- 4c. DELETE the batch and its remaining child — the cascade the app performs itself,
-- because parent_specimen_id is `on delete set null` and would otherwise orphan children
-- rather than remove them.
with removed as (
  delete from public.specimen_records
   where specimen_id in ('aaaaaaaa-0000-4000-8000-000000000001',
                         'aaaaaaaa-0000-4000-8000-000000000003')
  returning specimen_id
)
select 'specimen_records DELETE (batch + child cascade)' as check_name,
       count(*) as rows_affected,
       case when count(*) = 2 then 'PASS'
            else 'FAIL — expected 2 rows removed' end as verdict
from removed;

-- 4d/4e. The two side tables. Deleted by a marker column rather than by primary key, so
-- this works whichever key column the live table actually has.
insert into public.bioassay_results
  (assay_date, treatment_name, concentration_pct, replicate_number, is_control,
   mosquitoes_exposed, exposure_time_minutes, mortality_24hr, submitted_by, batch_reference)
values (current_date, 'Deltamethrin', 0.05, 1, false, 20, 60.0, 18,
        'delete-smoke-test', 'DELETE-SMOKE-TEST');

with removed as (
  delete from public.bioassay_results
   where batch_reference = 'DELETE-SMOKE-TEST'
  returning 1
)
select 'bioassay_results DELETE' as check_name,
       count(*) as rows_affected,
       case when count(*) = 1 then 'PASS'
            else 'FAIL — no DELETE policy; run sql/add_delete_policies.sql' end as verdict
from removed;

insert into public.clinical_case_data
  (report_date, facility_name, confirmed_cases, submitted_by)
values (current_date, 'DELETE-SMOKE-TEST', 1, 'delete-smoke-test');

with removed as (
  delete from public.clinical_case_data
   where facility_name = 'DELETE-SMOKE-TEST'
  returning 1
)
select 'clinical_case_data DELETE' as check_name,
       count(*) as rows_affected,
       case when count(*) = 1 then 'PASS'
            else 'FAIL — no DELETE policy; run sql/add_delete_policies.sql' end as verdict
from removed;

-- Nothing above is kept. Every insert and delete in section 4 is undone here.
rollback;

-- =====================================================================================
-- 5. Confirm the rollback left nothing behind
-- =====================================================================================
select count(*) as leftover_test_rows,
       case when count(*) = 0 then 'CLEAN' else 'LEFTOVERS — delete these rows' end as verdict
from (
  select 1 from public.specimen_records where collector_id = 'delete-smoke-test'
  union all
  select 1 from public.bioassay_results where batch_reference = 'DELETE-SMOKE-TEST'
  union all
  select 1 from public.clinical_case_data where facility_name = 'DELETE-SMOKE-TEST'
) as test_rows;
