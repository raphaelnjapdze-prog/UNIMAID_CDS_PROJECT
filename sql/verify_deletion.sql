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
--   3. sql/add_ownership_delete_policies.sql
--   4. sql/create_bioassay_results.sql      (optional — see section 1 before its
--   5. sql/create_clinical_case_data.sql     CHECK-constraint sections)
--
-- SIMULATING A SIGNED-IN USER
-- `set local role authenticated` alone is not enough once deletion is ownership-scoped:
-- the policy compares collector_id against auth.uid(), and auth.uid() reads the request's
-- JWT claims, which the SQL Editor does not set — so it comes back NULL and every row
-- looks like somebody else's. Sections 4 and 6 therefore also
-- `set local request.jwt.claims`, which is where auth.uid() looks. That makes it possible
-- to act as a specific user here, and to act as a *second* user, which is the only way to
-- prove one investigator cannot delete another's data.
--
-- Three fixed test identities are used, and nothing outside these ever exists:
--   11111111-…  investigator A
--   22222222-…  investigator B
--   33333333-…  an administrator

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

-- Is the DELETE policy actually ownership-scoped, or still the blanket `true`?
-- A policy of `using (true)` deletes just fine — it passes every check above — while
-- letting any signed-in account remove anybody's field data. This is the check that tells
-- those two apart, and it reads the policy's qualifier rather than trusting its name.
select
  t.tablename,
  coalesce(bool_or(p.qual ilike '%auth.uid()%'), false) as scoped_to_owner,
  coalesce(bool_or(p.qual ilike '%is_app_admin%'), false) as has_admin_exemption,
  case
    when bool_or(p.qual ilike '%auth.uid()%') then 'PASS'
    when count(p.*) > 0 then
      'FAIL — DELETE policy is not ownership-scoped (still `true`?); '
      || 'run sql/add_ownership_delete_policies.sql'
    else 'FAIL — no DELETE policy at all; run sql/add_delete_policies.sql first'
  end as verdict
from (values ('specimen_records'), ('bioassay_results'), ('clinical_case_data')) as t(tablename)
left join pg_policies p
       on p.schemaname = 'public' and p.tablename = t.tablename
      and p.cmd in ('DELETE', 'ALL')
group by t.tablename
order by t.tablename;

-- The admin roster and its membership test have to exist, or the admin half of every
-- policy above silently never matches.
select
  'public.app_admins table' as object_name,
  (to_regclass('public.app_admins') is not null) as present,
  case when to_regclass('public.app_admins') is not null then 'PASS'
       else 'FAIL — run sql/add_ownership_delete_policies.sql' end as verdict
union all
select
  'public.is_app_admin() function',
  exists (select 1 from pg_proc where proname = 'is_app_admin'
                                  and pronamespace = 'public'::regnamespace),
  case when exists (select 1 from pg_proc where proname = 'is_app_admin'
                                            and pronamespace = 'public'::regnamespace)
       then 'PASS' else 'FAIL — run sql/add_ownership_delete_policies.sql' end;

-- app_admins must have NO write policy. If one exists, a signed-in account could add
-- itself to the roster and then delete the entire project.
select
  count(*) as write_policies_on_app_admins,
  case when count(*) = 0 then 'PASS'
       else 'FAIL — a write policy on app_admins lets a session promote itself to admin' end
    as verdict
from pg_policies
where schemaname = 'public' and tablename = 'app_admins'
  and cmd in ('INSERT', 'UPDATE', 'DELETE', 'ALL');

-- Photo objects are a separate policy surface from table rows — this is the one that was
-- missing, which is why deleting photos and deleting rows behaved differently.
--
-- Note this one is NOT ownership-scoped, by design and not by oversight: objects live at
-- '{specimen_id}/{uuid}.ext' with no owner in the path, and the app deletes a row before
-- its photos, so a policy joining back to specimen_records would find the row already gone
-- and refuse every legitimate delete. See docs/DELETING_ENTRIES.md, "A known gap".
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
-- Act as investigator A. Without this auth.uid() is NULL, the rows below match no owner,
-- and every delete here would report FAIL against a perfectly correct policy.
set local request.jwt.claims = '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}';

-- A batch with two individuals vialed out of it, matching the shape the app writes.
-- collector_id is A's uid, because that is what the app stamps and what ownership means.
insert into public.specimen_records
  (specimen_id, collection_date, collector_id, breeding_site_type,
   field_screening_result, specimen_role)
values
  ('aaaaaaaa-0000-4000-8000-000000000001', current_date,
   '11111111-1111-4111-8111-111111111111', 'Stagnant pool',
   '{"screening_method":"manual_field_log",
     "result":{"anopheles_count":10,"culex_count":0,"aedes_count":0,
               "vialed_out":{"Anopheles":2}}}'::jsonb,
   'primary');

insert into public.specimen_records
  (specimen_id, parent_specimen_id, collection_date, collector_id,
   field_screening_result, specimen_role)
values
  ('aaaaaaaa-0000-4000-8000-000000000002', 'aaaaaaaa-0000-4000-8000-000000000001',
   current_date, '11111111-1111-4111-8111-111111111111',
   '{"screening_method":"field_subsample","result":{"genus":"Anopheles"}}'::jsonb, 'individual'),
  ('aaaaaaaa-0000-4000-8000-000000000003', 'aaaaaaaa-0000-4000-8000-000000000001',
   current_date, '11111111-1111-4111-8111-111111111111',
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
        '11111111-1111-4111-8111-111111111111', 'DELETE-SMOKE-TEST');

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
values (current_date, 'DELETE-SMOKE-TEST', 1, '11111111-1111-4111-8111-111111111111');

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
-- 5. OWNERSHIP: one investigator must not be able to delete another's data
-- =====================================================================================
-- Everything above proves deletion *works*. This proves it is *bounded* — the opposite
-- property, and the one a passing section 4 says nothing about. A blanket
-- `using (true)` policy passes every check in section 4 while letting any signed-in
-- account wipe a colleague's field season.
--
-- The whole section is rolled back, including the temporary admin registration.
begin;

-- Seed as postgres (the SQL Editor's own role, which RLS does not apply to) so the
-- starting state is guaranteed regardless of what the INSERT policies say. The point
-- under test is DELETE, not INSERT.
insert into public.specimen_records
  (specimen_id, collection_date, collector_id, breeding_site_type,
   field_screening_result, specimen_role)
values
  ('bbbbbbbb-0000-4000-8000-00000000000a', current_date,
   '11111111-1111-4111-8111-111111111111', 'Stagnant pool',
   '{"screening_method":"manual_field_log","result":{"anopheles_count":5}}'::jsonb, 'primary'),
  ('bbbbbbbb-0000-4000-8000-00000000000b', current_date,
   '22222222-2222-4222-8222-222222222222', 'Stagnant pool',
   '{"screening_method":"manual_field_log","result":{"anopheles_count":7}}'::jsonb, 'primary'),
  ('bbbbbbbb-0000-4000-8000-00000000000c', current_date,
   'unattributed-legacy', 'Stagnant pool',
   '{"screening_method":"manual_field_log","result":{"anopheles_count":3}}'::jsonb, 'primary');

-- --- Acting as investigator A -------------------------------------------------------
set local role authenticated;
set local request.jwt.claims = '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}';

-- 5a. A deletes A's own row. This must succeed, or the rule has locked everyone out.
with removed as (
  delete from public.specimen_records
   where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000a'
  returning specimen_id
)
select 'A deletes their OWN entry' as check_name,
       count(*) as rows_affected,
       case when count(*) = 1 then 'PASS'
            else 'FAIL — an investigator cannot delete their own data; '
                 || 'check auth.uid() resolves and collector_id holds the uid as text' end
         as verdict
from removed;

-- 5b. A tries to delete B's row. THE CHECK THIS FILE WAS EXTENDED FOR.
-- Zero rows is the pass. RLS refuses by matching nothing rather than raising, which is
-- exactly why this needs asserting rather than eyeballing.
with removed as (
  delete from public.specimen_records
   where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000b'
  returning specimen_id
)
select 'A CANNOT delete B''s entry' as check_name,
       count(*) as rows_affected,
       case when count(*) = 0 then 'PASS'
            else 'FAIL — one investigator can delete another''s field data; '
                 || 'run sql/add_ownership_delete_policies.sql' end as verdict
from removed;

-- 5c. A tries to delete a pre-identity row. Nobody can claim it, so nobody but an admin
-- may remove it.
with removed as (
  delete from public.specimen_records
   where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000c'
  returning specimen_id
)
select 'A CANNOT delete an unattributed-legacy entry' as check_name,
       count(*) as rows_affected,
       case when count(*) = 0 then 'PASS'
            else 'FAIL — an ownerless row was deletable by a non-admin' end as verdict
from removed;

-- 5d. A blanket delete must not become a way around the rule: no WHERE clause, and B's
-- row plus the legacy row still have to survive.
-- The ::text cast is needed because specimen_id may be a uuid column, and `like` has no
-- operator for uuid.
with removed as (
  delete from public.specimen_records
   where specimen_id::text like 'bbbbbbbb-0000-4000-8000-%'
  returning specimen_id
)
select 'An unfiltered DELETE still only takes A''s rows' as check_name,
       count(*) as rows_affected,
       case when count(*) = 0 then 'PASS'
            else 'FAIL — a broad DELETE reached rows A does not own' end as verdict
from removed;

-- --- Back to postgres to count survivors --------------------------------------------
-- Counted as postgres rather than as A on purpose: if the SELECT policy is ever narrowed,
-- A would simply not see B's row and this would report a false FAIL for the wrong reason.
-- What is under test is whether the row still EXISTS, not whether A can see it.
reset role;

select 'B''s entry survived everything A tried' as check_name,
       count(*) as rows_remaining,
       case when count(*) = 2 then 'PASS'
            else 'FAIL — expected B''s row and the legacy row to both remain' end as verdict
from public.specimen_records
where specimen_id in ('bbbbbbbb-0000-4000-8000-00000000000b',
                      'bbbbbbbb-0000-4000-8000-00000000000c');

-- --- Acting as an administrator -----------------------------------------------------
-- Register one, as postgres: app_admins deliberately has no write policy, so this is the
-- only way in — which is the property being relied on. Rolled back with everything else.
insert into public.app_admins (user_id, note)
values ('33333333-3333-4333-8333-333333333333', 'verify_deletion.sql — temporary, rolled back')
on conflict (user_id) do nothing;

set local role authenticated;
set local request.jwt.claims = '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}';

-- 5e. The admin sees themselves as an admin.
select 'is_app_admin() recognises a registered admin' as check_name,
       public.is_app_admin() as result,
       case when public.is_app_admin() then 'PASS'
            else 'FAIL — is_app_admin() is false for a registered admin; '
                 || 'check it is SECURITY DEFINER' end as verdict;

-- 5f. The admin deletes rows belonging to B and to nobody — the exemption, working.
with removed as (
  delete from public.specimen_records
   where specimen_id in ('bbbbbbbb-0000-4000-8000-00000000000b',
                         'bbbbbbbb-0000-4000-8000-00000000000c')
  returning specimen_id
)
select 'An admin CAN delete anyone''s entry' as check_name,
       count(*) as rows_affected,
       case when count(*) = 2 then 'PASS'
            else 'FAIL — an admin cannot delete other investigators'' rows; '
                 || 'check public.app_admins contains the uid' end as verdict
from removed;

-- 5g. A non-admin is not accidentally an admin. Guards against is_app_admin() being
-- written so that it returns true for everyone (a `security definer` function with a
-- missing WHERE would do exactly that, and every other check here would still pass).
set local request.jwt.claims = '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}';
select 'is_app_admin() is false for a normal user' as check_name,
       public.is_app_admin() as result,
       case when public.is_app_admin() then
              'FAIL — is_app_admin() returns true for an unregistered user; '
              || 'everyone is an admin and the rule is void'
            else 'PASS' end as verdict;

-- Nothing above is kept — including the temporary admin registration.
rollback;

-- =====================================================================================
-- 6. Confirm the rollback left nothing behind
-- =====================================================================================
select count(*) as leftover_test_rows,
       case when count(*) = 0 then 'CLEAN' else 'LEFTOVERS — delete these rows' end as verdict
from (
  select 1 from public.specimen_records
   where collector_id in ('delete-smoke-test',
                          '11111111-1111-4111-8111-111111111111',
                          '22222222-2222-4222-8222-222222222222')
      or specimen_id::text like 'bbbbbbbb-0000-4000-8000-%'
  union all
  select 1 from public.bioassay_results where batch_reference = 'DELETE-SMOKE-TEST'
  union all
  select 1 from public.clinical_case_data where facility_name = 'DELETE-SMOKE-TEST'
  union all
  select 1 from public.app_admins
   where user_id = '33333333-3333-4333-8333-333333333333'
) as test_rows;
