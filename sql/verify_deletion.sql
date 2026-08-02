-- Verify that deletion works, and that it is BOUNDED — run in the Supabase SQL Editor.
--
-- Select the whole file and Run. It ends with a single SELECT that returns every check as
-- one table of PASS/FAIL rows.
--
-- READ THIS BEFORE EDITING THE FILE
-- The SQL Editor displays the result of the LAST statement only. An earlier version of
-- this file was ~20 separate statements each returning its own PASS/FAIL row; every one of
-- them was computed and thrown away, and the editor reported "Success. No rows returned" —
-- which reads like a pass and means nothing at all. So every check now writes into
-- _verify_results and the file ends with one SELECT of that table. If you add a check, add
-- it the same way; do not end the file with anything else.
--
-- WHY THIS FILE EXISTS
-- The failure it checks for is silent. Under row-level security a DELETE (or UPDATE) with
-- no matching policy does not raise — it matches zero rows and reports success. That is how
-- the app could appear to clear a trial run while every row stayed in the table.
--
-- Sections 1-3 are read-only. Section 4 proves deletion WORKS. Section 5 proves it is
-- BOUNDED, which is the opposite property: a blanket `using (true)` policy passes all of
-- section 4 while letting any signed-in account wipe a colleague's field season.
--
-- IS IT SAFE?
-- Sections 4 and 5 create rows, delete them, and then explicitly delete anything left over,
-- all inside one transaction. If any statement raises, the whole transaction rolls back and
-- nothing persists. On success the cleanup has already removed everything, and the last two
-- checks in the output assert exactly that. Every row it creates is a fixed, recognisable
-- id, so if you ever interrupt it mid-run you can find them:
--   specimen_id like 'aaaaaaaa-0000-4000-8000-%' or 'bbbbbbbb-0000-4000-8000-%'
--   batch_reference / facility_name = 'DELETE-SMOKE-TEST'
--   app_admins.user_id = '33333333-3333-4333-8333-333333333333'
--
-- RUN THE MIGRATIONS FIRST, in this order:
--   1. sql/add_update_policies.sql
--   2. sql/add_delete_policies.sql
--   3. sql/add_ownership_delete_policies.sql
--   4. sql/create_bioassay_results.sql      (optional — see the pre-flight rows before
--   5. sql/create_clinical_case_data.sql     running their CHECK-constraint sections)
--
-- SIMULATING A SIGNED-IN USER
-- `set local role authenticated` alone is not enough once deletion is ownership-scoped: the
-- policy compares the owner column against auth.uid(), and auth.uid() reads the request's
-- JWT claims, which the SQL Editor does not set — so it comes back NULL, every row looks
-- like somebody else's, and correct policies report FAIL. Sections 4 and 5 therefore also
-- `set local request.jwt.claims`, which is where auth.uid() looks. That is also what makes
-- it possible to act as a *second* user, which is the only way to prove one investigator
-- cannot delete another's data.
--
-- Three fixed test identities, and nothing outside these ever exists:
--   11111111-…  investigator A
--   22222222-…  investigator B
--   33333333-…  an administrator (registered, then removed again)

-- =====================================================================================
-- The results table. Created outside the transaction so it survives to be selected.
-- =====================================================================================
drop table if exists _verify_results;
create temp table _verify_results (
  seq        int,
  section    text,
  check_name text,
  detail     text,
  verdict    text
);

begin;

-- =====================================================================================
-- 1. PRE-FLIGHT: would the CHECK constraints in the two schema files fail?
-- =====================================================================================
-- Adding a CHECK to a table with a violating row fails outright. Both must read 0 before
-- you run the CHECK-constraint sections of create_bioassay_results.sql /
-- create_clinical_case_data.sql. A violation is bad data, not a constraint to relax: more
-- dead mosquitoes than were exposed, or fewer suspected cases than confirmed, is a
-- measurement error.
insert into _verify_results
select 10, '1. pre-flight', 'bioassay_results rows violating the CHECKs', count(*)::text,
       case when count(*) = 0 then 'SAFE to add constraints' else 'FIX THESE ROWS FIRST' end
from public.bioassay_results
where mosquitoes_exposed is null or mosquitoes_exposed <= 0
   or mortality_24hr is null or mortality_24hr < 0
   or mortality_24hr > mosquitoes_exposed
   or (knockdown_60min is not null
       and (knockdown_60min < 0 or knockdown_60min > mosquitoes_exposed))
   or replicate_number is null or replicate_number <= 0
   or concentration_pct is null or concentration_pct < 0;

insert into _verify_results
select 11, '1. pre-flight', 'clinical_case_data rows violating the CHECKs', count(*)::text,
       case when count(*) = 0 then 'SAFE to add constraints' else 'FIX THESE ROWS FIRST' end
from public.clinical_case_data
where confirmed_cases is null or confirmed_cases < 0
   or (suspected_cases is not null and suspected_cases < confirmed_cases)
   or facility_name is null or btrim(facility_name) = '';

-- =====================================================================================
-- 2. Do the policies exist, and are they ownership-scoped?
-- =====================================================================================
-- cmd = 'ALL' counts: a `for all` policy covers DELETE too, and a hand-created policy is
-- quite likely to be one. Treating only cmd = 'DELETE' as a pass would report a working
-- setup as broken.
insert into _verify_results
select 20, '2. policies', 'DELETE policy exists: ' || t.tablename,
       coalesce(bool_or(p.cmd in ('DELETE','ALL')), false)::text,
       case when bool_or(p.cmd in ('DELETE','ALL')) then 'PASS'
            else 'FAIL - deletion will silently do nothing; run add_delete_policies.sql' end
from (values ('specimen_records'),('bioassay_results'),('clinical_case_data')) as t(tablename)
left join pg_policies p on p.schemaname = 'public' and p.tablename = t.tablename
group by t.tablename;

-- The check that separates "deletion works" from "deletion is bounded". A policy of
-- `using (true)` passes everything else in this file while leaving the door wide open.
insert into _verify_results
select 21, '2. policies', 'DELETE policy is ownership-scoped: ' || t.tablename,
       coalesce(bool_or(p.qual ilike '%auth.uid()%'), false)::text,
       case when bool_or(p.qual ilike '%auth.uid()%') then 'PASS'
            when count(p.*) > 0 then 'FAIL - still `using (true)`; run add_ownership_delete_policies.sql'
            else 'FAIL - no DELETE policy at all' end
from (values ('specimen_records'),('bioassay_results'),('clinical_case_data')) as t(tablename)
left join pg_policies p on p.schemaname = 'public' and p.tablename = t.tablename
                       and p.cmd in ('DELETE','ALL')
group by t.tablename;

insert into _verify_results
select 22, '2. policies', 'admin exemption present: ' || t.tablename,
       coalesce(bool_or(p.qual ilike '%is_app_admin%'), false)::text,
       case when bool_or(p.qual ilike '%is_app_admin%') then 'PASS'
            else 'FAIL - admins cannot delete other investigators rows' end
from (values ('specimen_records'),('bioassay_results'),('clinical_case_data')) as t(tablename)
left join pg_policies p on p.schemaname = 'public' and p.tablename = t.tablename
                       and p.cmd in ('DELETE','ALL')
group by t.tablename;

insert into _verify_results
select 23, '2. policies', 'app_admins table exists',
       (to_regclass('public.app_admins') is not null)::text,
       case when to_regclass('public.app_admins') is not null then 'PASS'
            else 'FAIL - run add_ownership_delete_policies.sql' end;

insert into _verify_results
select 24, '2. policies', 'is_app_admin() function exists',
       exists(select 1 from pg_proc where proname = 'is_app_admin'
                                      and pronamespace = 'public'::regnamespace)::text,
       case when exists(select 1 from pg_proc where proname = 'is_app_admin'
                                                and pronamespace = 'public'::regnamespace)
            then 'PASS' else 'FAIL - run add_ownership_delete_policies.sql' end;

-- If a write policy exists here, a signed-in account can add itself to the roster and then
-- delete the entire project. The absence of one is load-bearing.
insert into _verify_results
select 25, '2. policies', 'app_admins has NO write policy', count(*)::text,
       case when count(*) = 0 then 'PASS'
            else 'FAIL - a session could promote itself to admin' end
from pg_policies
where schemaname = 'public' and tablename = 'app_admins'
  and cmd in ('INSERT','UPDATE','DELETE','ALL');

insert into _verify_results
select 26, '2. policies', 'administrators registered', count(*)::text,
       case when count(*) > 0 then 'PASS'
            else 'FAIL - nobody is an admin; insert your uid into app_admins' end
from public.app_admins;

-- Photo objects are a separate policy surface from table rows — this is the one that was
-- missing originally, which is why deleting photos and deleting rows behaved differently.
insert into _verify_results
select 27, '2. policies', 'storage DELETE policy for specimen-photos', count(*)::text,
       case when count(*) > 0 then 'PASS'
            else 'FAIL - specimen photos cannot be deleted; run add_delete_policies.sql' end
from pg_policies
where schemaname = 'storage' and tablename = 'objects'
  and cmd in ('DELETE','ALL')
  and coalesce(qual,'') || coalesce(with_check,'') ilike '%specimen-photos%';

-- Deliberately NOT ownership-scoped, and recorded here so its absence is never mistaken for
-- an oversight: objects live at '{specimen_id}/{uuid}.ext' with no owner in the path, and
-- the app deletes a row before its photos, so a policy joining back to specimen_records
-- would find the row already gone and refuse every legitimate delete. See
-- docs/DELETING_ENTRIES.md, "A known gap".
insert into _verify_results
select 28, '2. policies', 'storage photos are ownership-scoped', 'false',
       'KNOWN GAP - by design, see docs/DELETING_ENTRIES.md';

-- =====================================================================================
-- 3. Is RLS even switched on?
-- =====================================================================================
-- A table with policies but RLS disabled is wide open; a table with RLS on and no policies
-- is a black hole that swallows writes.
insert into _verify_results
select 30, '3. rls', 'RLS enabled: ' || relname, relrowsecurity::text,
       case when relrowsecurity then 'PASS' else 'FAIL - policies are not being enforced' end
from pg_class
where relnamespace = 'public'::regnamespace
  and relname in ('specimen_records','bioassay_results','clinical_case_data');

-- =====================================================================================
-- 4. END-TO-END: deletion works, as the role the app actually uses
-- =====================================================================================
-- The SQL Editor runs as `postgres`, which owns these tables, and RLS does not apply to a
-- table's owner. Testing as-is would pass no matter what the policies say.
insert into public.specimen_records
  (specimen_id, collection_date, collector_id, breeding_site_type,
   field_screening_result, specimen_role)
values
  ('aaaaaaaa-0000-4000-8000-000000000001', current_date,
   '11111111-1111-4111-8111-111111111111', 'Stagnant pool',
   '{"screening_method":"manual_field_log",
     "result":{"anopheles_count":10,"culex_count":0,"aedes_count":0,
               "vialed_out":{"Anopheles":2}}}'::jsonb, 'primary');

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

insert into public.bioassay_results
  (assay_date, treatment_name, concentration_pct, replicate_number, is_control,
   mosquitoes_exposed, exposure_time_minutes, mortality_24hr, submitted_by, batch_reference)
values (current_date, 'Deltamethrin', 0.05, 1, false, 20, 60.0, 18,
        '11111111-1111-4111-8111-111111111111', 'DELETE-SMOKE-TEST');

insert into public.clinical_case_data
  (report_date, facility_name, confirmed_cases, submitted_by)
values (current_date, 'DELETE-SMOKE-TEST', 1, '11111111-1111-4111-8111-111111111111');

-- Act as investigator A, who owns everything just inserted.
set local role authenticated;
set local request.jwt.claims = '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}';

-- 4a. UPDATE — the app decrements a batch's vialed_out tally through this. Without it,
-- deleting one vialed individual leaves that collection event short by a mosquito.
update public.specimen_records
   set field_screening_result =
       jsonb_set(field_screening_result, '{result,vialed_out,Anopheles}', '1'::jsonb)
 where specimen_id = 'aaaaaaaa-0000-4000-8000-000000000001';

-- Recorded here, before the deletes below remove the row it reads. `authenticated` has no
-- rights on a temp table owned by postgres, so the role goes back and forth around each
-- group of assertions rather than writing results from inside the switched role.
reset role;

insert into _verify_results
select 40, '4. deletion works', 'batch tally UPDATE applied',
       coalesce(field_screening_result #>> '{result,vialed_out,Anopheles}', 'null'),
       case when field_screening_result #>> '{result,vialed_out,Anopheles}' = '1' then 'PASS'
            else 'FAIL - no UPDATE policy; run add_update_policies.sql' end
from public.specimen_records where specimen_id = 'aaaaaaaa-0000-4000-8000-000000000001';

-- 4b/4c. The per-entry delete, then the batch + remaining child cascade the app performs
-- itself (parent_specimen_id is `on delete set null`, so children would otherwise be
-- orphaned rather than removed).
set local role authenticated;

delete from public.specimen_records where specimen_id = 'aaaaaaaa-0000-4000-8000-000000000002';
delete from public.specimen_records
 where specimen_id in ('aaaaaaaa-0000-4000-8000-000000000001',
                       'aaaaaaaa-0000-4000-8000-000000000003');
delete from public.bioassay_results   where batch_reference = 'DELETE-SMOKE-TEST';
delete from public.clinical_case_data where facility_name  = 'DELETE-SMOKE-TEST';

-- Outcomes are asserted by what SURVIVED rather than by rows-affected: it is the same
-- question, and it stays correct even if the SELECT policy is ever narrowed so that A
-- cannot see the row it just failed to delete.
reset role;

insert into _verify_results
select 41, '4. deletion works', 'specimen_records DELETE (all 3 test rows gone)',
       count(*)::text,
       case when count(*) = 0 then 'PASS'
            else 'FAIL - no DELETE policy; run add_delete_policies.sql' end
from public.specimen_records where specimen_id::text like 'aaaaaaaa-0000-4000-8000-%';

insert into _verify_results
select 42, '4. deletion works', 'bioassay_results DELETE', count(*)::text,
       case when count(*) = 0 then 'PASS' else 'FAIL - no DELETE policy' end
from public.bioassay_results where batch_reference = 'DELETE-SMOKE-TEST';

insert into _verify_results
select 43, '4. deletion works', 'clinical_case_data DELETE', count(*)::text,
       case when count(*) = 0 then 'PASS' else 'FAIL - no DELETE policy' end
from public.clinical_case_data where facility_name = 'DELETE-SMOKE-TEST';

-- =====================================================================================
-- 5. OWNERSHIP: one investigator must not be able to delete another's data
-- =====================================================================================
-- Seeded as postgres so the starting state is guaranteed regardless of what the INSERT
-- policies say. What is under test is DELETE, not INSERT.
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

-- Act as investigator A and try everything A should not be able to do.
set local role authenticated;
set local request.jwt.claims = '{"sub":"11111111-1111-4111-8111-111111111111","role":"authenticated"}';

delete from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000a';
delete from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000b';
delete from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000c';
-- And a broad, unfiltered attempt, in case a WHERE clause was the only thing stopping it.
delete from public.specimen_records where specimen_id::text like 'bbbbbbbb-0000-4000-8000-%';

reset role;

insert into _verify_results
select 50, '5. ownership', 'A CAN delete their OWN entry', count(*)::text,
       case when count(*) = 0 then 'PASS'
            else 'FAIL - an investigator cannot delete their own data' end
from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000a';

insert into _verify_results
select 51, '5. ownership', 'A CANNOT delete B''s entry', count(*)::text,
       case when count(*) = 1 then 'PASS'
            else 'FAIL - one investigator can delete another''s field data' end
from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000b';

insert into _verify_results
select 52, '5. ownership', 'A CANNOT delete an unattributed-legacy entry', count(*)::text,
       case when count(*) = 1 then 'PASS'
            else 'FAIL - an ownerless row was deletable by a non-admin' end
from public.specimen_records where specimen_id = 'bbbbbbbb-0000-4000-8000-00000000000c';

-- Register an admin. app_admins deliberately has no write policy, so postgres is the only
-- way in — which is the property being relied on. Removed again below.
insert into public.app_admins (user_id, note)
values ('33333333-3333-4333-8333-333333333333', 'verify_deletion.sql — temporary')
on conflict (user_id) do nothing;

-- is_app_admin() depends only on auth.uid(), which reads the GUC, so these can be evaluated
-- without switching role.
set local request.jwt.claims = '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}';
insert into _verify_results
select 53, '5. ownership', 'is_app_admin() TRUE for a registered admin',
       public.is_app_admin()::text,
       case when public.is_app_admin() then 'PASS'
            else 'FAIL - check is_app_admin() is SECURITY DEFINER' end;

-- Guards against is_app_admin() being written so it returns true for everyone. A definer
-- function with a missing WHERE would do exactly that, and every other check in this file
-- would still pass.
set local request.jwt.claims = '{"sub":"22222222-2222-4222-8222-222222222222","role":"authenticated"}';
insert into _verify_results
select 54, '5. ownership', 'is_app_admin() FALSE for a normal user',
       public.is_app_admin()::text,
       case when public.is_app_admin() then 'FAIL - everyone is an admin; the rule is void'
            else 'PASS' end;

-- The admin exemption, actually exercised: delete B's row and the ownerless one.
set local role authenticated;
set local request.jwt.claims = '{"sub":"33333333-3333-4333-8333-333333333333","role":"authenticated"}';
delete from public.specimen_records
 where specimen_id in ('bbbbbbbb-0000-4000-8000-00000000000b',
                       'bbbbbbbb-0000-4000-8000-00000000000c');
reset role;

insert into _verify_results
select 55, '5. ownership', 'An admin CAN delete anyone''s entry', count(*)::text,
       case when count(*) = 0 then 'PASS'
            else 'FAIL - an admin cannot delete other investigators'' rows' end
from public.specimen_records where specimen_id::text like 'bbbbbbbb-0000-4000-8000-%';

-- =====================================================================================
-- 6. Clean up, then confirm nothing was left behind
-- =====================================================================================
-- Explicit rather than a rollback: the results table has to survive to be selected, and a
-- rollback would take it with everything else. Any statement raising above aborts the
-- transaction and undoes all of this anyway.
delete from public.specimen_records
 where specimen_id::text like 'aaaaaaaa-0000-4000-8000-%'
    or specimen_id::text like 'bbbbbbbb-0000-4000-8000-%';
delete from public.bioassay_results   where batch_reference = 'DELETE-SMOKE-TEST';
delete from public.clinical_case_data where facility_name  = 'DELETE-SMOKE-TEST';
delete from public.app_admins where user_id = '33333333-3333-4333-8333-333333333333';

insert into _verify_results
select 60, '6. cleanup', 'no test rows left behind', count(*)::text,
       case when count(*) = 0 then 'CLEAN' else 'LEFTOVERS - delete these rows' end
from (
  select 1 from public.specimen_records
   where specimen_id::text like 'aaaaaaaa-0000-4000-8000-%'
      or specimen_id::text like 'bbbbbbbb-0000-4000-8000-%'
  union all select 1 from public.bioassay_results   where batch_reference = 'DELETE-SMOKE-TEST'
  union all select 1 from public.clinical_case_data where facility_name  = 'DELETE-SMOKE-TEST'
) as leftovers;

insert into _verify_results
select 61, '6. cleanup', 'temporary admin removed', count(*)::text,
       case when count(*) = 0 then 'CLEAN' else 'LEFTOVERS - remove this app_admins row' end
from public.app_admins where user_id = '33333333-3333-4333-8333-333333333333';

commit;

-- =====================================================================================
-- THE RESULT. This must stay the last statement in the file.
-- =====================================================================================
select section, check_name, detail, verdict
from _verify_results
order by seq, check_name;
