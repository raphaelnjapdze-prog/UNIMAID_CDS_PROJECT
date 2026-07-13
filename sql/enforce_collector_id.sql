-- Migration: make collector_id actually mean something.
--
-- specimen_records.collector_id was already declared NOT NULL, and the table still
-- filled up with blank collectors. NOT NULL does not stop an empty string: Postgres
-- treats '' as a perfectly good value. utils/auth.py::get_current_user_id() returns ""
-- for a session with no user, so every unattributed write sailed straight through the
-- constraint.
--
-- The application now refuses those writes (utils/data_manager.py::require_current_user_id),
-- but the database should not depend on the application getting it right. This adds the
-- check that was actually needed.
--
-- Safe to run on an existing database. Run it in the Supabase SQL Editor.

-- 1. Backfill the rows written before identity was enforced.
--
-- Their author was never recorded anywhere — not in a log, not in a backup — so it
-- cannot be recovered. Naming a likely author would put someone's name on work that may
-- not be theirs, which is a lie in a research record. Mark them as what they are:
-- entries from before the app tracked identity. They stay honestly distinguishable from
-- properly attributed rows, and no null remains to block the constraint below.
update public.specimen_records
   set collector_id = 'unattributed-legacy'
 where collector_id is null
    or btrim(collector_id) = '';

-- 2. Reject blank collectors at the database, not just in the app.
alter table public.specimen_records
  drop constraint if exists specimen_records_collector_id_not_blank;

alter table public.specimen_records
  add constraint specimen_records_collector_id_not_blank
  check (btrim(collector_id) <> '');

-- Same hole exists on the other two tables: submitted_by is stamped from the same
-- get_current_user_id(), so it could be written blank the same way.
update public.bioassay_results
   set submitted_by = 'unattributed-legacy'
 where submitted_by is null
    or btrim(submitted_by) = '';

update public.clinical_case_data
   set submitted_by = 'unattributed-legacy'
 where submitted_by is null
    or btrim(submitted_by) = '';

alter table public.bioassay_results
  drop constraint if exists bioassay_results_submitted_by_not_blank;

alter table public.bioassay_results
  add constraint bioassay_results_submitted_by_not_blank
  check (submitted_by is null or btrim(submitted_by) <> '');

alter table public.clinical_case_data
  drop constraint if exists clinical_case_data_submitted_by_not_blank;

alter table public.clinical_case_data
  add constraint clinical_case_data_submitted_by_not_blank
  check (submitted_by is null or btrim(submitted_by) <> '');

-- 3. Confirm. Every row should now report a collector; unattributed_legacy is the count
-- of pre-fix rows, and blank should be 0.
select
  count(*)                                                  as total_rows,
  count(*) filter (where collector_id = 'unattributed-legacy') as unattributed_legacy,
  count(*) filter (where btrim(collector_id) = '')             as blank,
  count(distinct collector_id)                              as distinct_collectors
from public.specimen_records;
