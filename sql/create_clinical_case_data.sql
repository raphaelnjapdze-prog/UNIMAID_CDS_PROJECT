-- Schema for clinical_case_data — confirmed malaria case counts per facility per period.
--
-- Run this in the Supabase SQL Editor. Safe to run on an existing database: the table
-- creation is `if not exists`, and the reconciliation section below adds only missing
-- columns. The CHECK constraints in section 4 are the one part that can fail on existing
-- data — read the note there before running it.
--
-- IMPORTANT — this file is a reconstruction, not the origin of the live table.
-- clinical_case_data was created by hand in the Supabase dashboard before this file
-- existed, so the live table is the authority on what is actually there and may have
-- drifted from this. Every column below is one the application reads or writes:
--
--   utils/data_manager.py::submit_clinical_case_record — writes every column except id/created_at
--   utils/data_manager.py::load_clinical_case_data     — select *
--   utils/epidemiology_engine.py                       — report_date, confirmed_cases
--                                                        (weekly series for the larval-density
--                                                         vs. case-count correlation)
--   components/clinical_case_entry.py                  — orders by created_at
--
-- Section 6's query prints the live column list so you can diff it against this file.
--
-- This table is the *only* source of case counts in the app. Nothing here is estimated or
-- simulated: if it is empty, the Epidemiology page says correlation is unavailable rather
-- than inventing a series.

create extension if not exists "uuid-ossp";

-- 1. Table -------------------------------------------------------------------------
create table if not exists public.clinical_case_data (
    id uuid primary key default uuid_generate_v4(),

    -- Start of the reporting period, not the date of an individual case. The epidemiology
    -- engine buckets these into weeks.
    report_date date not null,
    facility_name text not null,
    lga_district text,

    confirmed_cases integer not null,
    -- Nullable: the entry form offers "-1 if unknown" and stores NULL for it. A facility
    -- that did not report how many it tested is not a facility that tested zero.
    suspected_cases integer,

    -- Free text, deliberately. The form offers fixed options (RDT / Microscopy /
    -- RDT + Microscopy / Clinical diagnosis only; All ages / Under 5 / 5 and older /
    -- Pregnant women), but pinning them in an enum or CHECK means every future option
    -- needs a migration before it can be logged, and would reject rows already stored
    -- under earlier wording.
    diagnostic_method text,
    patient_age_group text,

    -- Nullable to match sql/enforce_collector_id.sql, which allows NULL here but forbids
    -- blank. require_current_user_id() refuses the write when there is no user, so new
    -- rows always carry one; pre-fix rows were backfilled to 'unattributed-legacy'.
    submitted_by text,
    notes text,

    -- Required, not decorative: the entry page orders by it.
    created_at timestamptz not null default now()
);

-- No updated_at and no trigger, unlike specimen_records. Nothing in the app edits a case
-- record — it is inserted, read, and (since sql/add_delete_policies.sql) deleted. That
-- file deliberately grants no UPDATE policy on this table for the same reason.

-- 2. Reconcile an existing table ---------------------------------------------------
-- No-ops on a table already holding these columns; fills the gap on one that drifted.
--
-- These deliberately omit the NOT NULL that section 1 declares. Adding NOT NULL to a
-- column that already holds nulls fails outright, and a column added here is null in
-- every existing row by definition. Section 1 is the shape a fresh database gets; this
-- section only makes an older table readable by the app. If you want the constraints on a
-- drifted table, backfill the column first, then add NOT NULL by hand.
alter table public.clinical_case_data add column if not exists report_date date;
alter table public.clinical_case_data add column if not exists facility_name text;
alter table public.clinical_case_data add column if not exists lga_district text;
alter table public.clinical_case_data add column if not exists confirmed_cases integer;
alter table public.clinical_case_data add column if not exists suspected_cases integer;
alter table public.clinical_case_data add column if not exists diagnostic_method text;
alter table public.clinical_case_data add column if not exists patient_age_group text;
alter table public.clinical_case_data add column if not exists submitted_by text;
alter table public.clinical_case_data add column if not exists notes text;
alter table public.clinical_case_data add column if not exists created_at timestamptz not null default now();

-- 3. Indexes ----------------------------------------------------------------------
create index if not exists idx_clinical_case_data_report_date on public.clinical_case_data (report_date);
create index if not exists idx_clinical_case_data_created_at on public.clinical_case_data (created_at desc);
create index if not exists idx_clinical_case_data_facility on public.clinical_case_data (facility_name);

-- 4. Constraints ------------------------------------------------------------------
-- submit_clinical_case_record() already validates all of this, and the entry page requires
-- a facility name. The database should not depend on the application getting it right —
-- the same argument sql/enforce_collector_id.sql makes about blank collector_ids.
--
-- ⚠ ADDING A CHECK TO A TABLE WITH EXISTING ROWS FAILS IF ANY ROW VIOLATES IT.
-- Run this first and confirm it returns 0 before running the section below:
--
--   select count(*) from public.clinical_case_data
--    where confirmed_cases is null or confirmed_cases < 0
--       or (suspected_cases is not null and suspected_cases < confirmed_cases)
--       or facility_name is null or btrim(facility_name) = '';
--
-- A row where suspected < confirmed is a data-entry error, not a constraint to relax:
-- every confirmed case was necessarily tested.

alter table public.clinical_case_data
  drop constraint if exists clinical_case_data_confirmed_non_negative;
alter table public.clinical_case_data
  add constraint clinical_case_data_confirmed_non_negative
  check (confirmed_cases >= 0);

alter table public.clinical_case_data
  drop constraint if exists clinical_case_data_suspected_at_least_confirmed;
alter table public.clinical_case_data
  add constraint clinical_case_data_suspected_at_least_confirmed
  check (suspected_cases is null or suspected_cases >= confirmed_cases);

-- A case count nobody can attribute to a facility cannot be checked against that
-- facility's records, so it is not usable surveillance data.
alter table public.clinical_case_data
  drop constraint if exists clinical_case_data_facility_not_blank;
alter table public.clinical_case_data
  add constraint clinical_case_data_facility_not_blank
  check (btrim(facility_name) <> '');

-- Deliberately NOT added: unique (report_date, facility_name). A facility legitimately
-- re-reports a period — a correction, or a split by age group, both of which the app
-- allows. A constraint the app does not know about would surface as an opaque insert
-- failure to whoever is entering the data.

-- 5. Row-level security -----------------------------------------------------------
-- Insert, read, delete — matching what the app does. No UPDATE policy, by the same
-- reasoning as sql/add_delete_policies.sql. Under RLS a statement with no matching policy
-- matches zero rows *without raising*, so a missing policy here looks like an empty table
-- or a silently discarded save.
alter table public.clinical_case_data enable row level security;

drop policy if exists "Authenticated users can insert clinical case data" on public.clinical_case_data;
create policy "Authenticated users can insert clinical case data"
  on public.clinical_case_data
  for insert
  to authenticated
  with check (true);

drop policy if exists "Authenticated users can read clinical case data" on public.clinical_case_data;
create policy "Authenticated users can read clinical case data"
  on public.clinical_case_data
  for select
  to authenticated
  using (true);

drop policy if exists "Authenticated users can delete clinical case data" on public.clinical_case_data;
create policy "Authenticated users can delete clinical case data"
  on public.clinical_case_data
  for delete
  to authenticated
  using (true);

-- 6. Verify ------------------------------------------------------------------------
-- Diff this against the table definition above. A column here that is missing from this
-- file means the live table drifted; update the file rather than dropping the column.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'clinical_case_data'
order by ordinal_position;

-- Policies should list INSERT, SELECT and DELETE. If you see duplicates under other
-- names, they are hand-created leftovers — policies are OR'd, so extras only widen
-- access. Drop the ones you did not intend.
select policyname, cmd as command, roles
from pg_policies
where schemaname = 'public' and tablename = 'clinical_case_data'
order by cmd, policyname;
