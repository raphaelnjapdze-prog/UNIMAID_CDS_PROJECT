-- Schema for bioassay_results — WHO tube bioassay mortality/knockdown replicates.
--
-- Run this in the Supabase SQL Editor. Safe to run on an existing database: the table
-- creation is `if not exists`, and the reconciliation section below adds only missing
-- columns. The CHECK constraints in section 4 are the one part that can fail on existing
-- data — read the note there before running it.
--
-- IMPORTANT — this file is a reconstruction, not the origin of the live table.
-- bioassay_results was created by hand in the Supabase dashboard before this file existed,
-- so the live table is the authority on what is actually there and may have drifted from
-- this. Every column below is one the application reads or writes:
--
--   utils/data_manager.py::submit_bioassay_result  — writes every column except id/created_at
--   utils/data_manager.py::load_bioassay_results   — select *
--   utils/resistance_ml_engine.py                  — is_control, assay_date, mosquitoes_exposed,
--                                                    mortality_24hr, species_tested
--   components/bioassay_entry.py                   — orders by created_at
--   components/reports.py                          — groups by treatment_name, concentration_pct,
--                                                    is_control; sums mosquitoes_exposed, mortality_24hr
--
-- Section 6's query prints the live column list so you can diff it against this file.

create extension if not exists "uuid-ossp";

-- 1. Table -------------------------------------------------------------------------
create table if not exists public.bioassay_results (
    id uuid primary key default uuid_generate_v4(),

    assay_date date not null,
    treatment_name text not null,
    -- double precision, not numeric: PostgREST serialises numeric as a JSON *string*, and
    -- the reports page groups by concentration_pct and the ML engine does arithmetic on
    -- these columns straight off the loaded DataFrame. A string would silently split
    -- "0.05" from 0.05 into separate treatment groups.
    concentration_pct double precision not null,
    replicate_number integer not null,
    is_control boolean not null default false,

    mosquitoes_exposed integer not null,
    exposure_time_minutes double precision not null default 60.0,
    -- Nullable: the entry form offers "-1 if not recorded" and stores NULL for it. A
    -- knockdown reading that was never taken is not a knockdown of zero.
    knockdown_60min integer,
    mortality_24hr integer not null,

    species_tested text,
    batch_reference text,
    -- Nullable to match sql/enforce_collector_id.sql, which allows NULL here but forbids
    -- blank. require_current_user_id() refuses the write when there is no user, so new
    -- rows always carry one; pre-fix rows were backfilled to 'unattributed-legacy'.
    submitted_by text,
    notes text,

    -- Required, not decorative: both the entry page and the reports page order by it.
    created_at timestamptz not null default now()
);

-- No updated_at and no trigger, unlike specimen_records. Nothing in the app edits a
-- bioassay replicate — it is inserted, read, and (since sql/add_delete_policies.sql)
-- deleted. That file deliberately grants no UPDATE policy on this table for the same
-- reason. Add both together if an edit feature ever lands.

-- 2. Reconcile an existing table ---------------------------------------------------
-- No-ops on a table already holding these columns; fills the gap on one that drifted.
--
-- These deliberately omit the NOT NULL that section 1 declares. Adding NOT NULL to a
-- column that already holds nulls fails outright, and a column added here is null in
-- every existing row by definition. Section 1 is the shape a fresh database gets; this
-- section only makes an older table readable by the app. If you want the constraints on a
-- drifted table, backfill the column first, then add NOT NULL by hand.
alter table public.bioassay_results add column if not exists assay_date date;
alter table public.bioassay_results add column if not exists treatment_name text;
alter table public.bioassay_results add column if not exists concentration_pct double precision;
alter table public.bioassay_results add column if not exists replicate_number integer;
alter table public.bioassay_results add column if not exists is_control boolean default false;
alter table public.bioassay_results add column if not exists mosquitoes_exposed integer;
alter table public.bioassay_results add column if not exists exposure_time_minutes double precision default 60.0;
alter table public.bioassay_results add column if not exists knockdown_60min integer;
alter table public.bioassay_results add column if not exists mortality_24hr integer;
alter table public.bioassay_results add column if not exists species_tested text;
alter table public.bioassay_results add column if not exists batch_reference text;
alter table public.bioassay_results add column if not exists submitted_by text;
alter table public.bioassay_results add column if not exists notes text;
alter table public.bioassay_results add column if not exists created_at timestamptz not null default now();

-- 3. Indexes ----------------------------------------------------------------------
create index if not exists idx_bioassay_results_assay_date on public.bioassay_results (assay_date);
create index if not exists idx_bioassay_results_created_at on public.bioassay_results (created_at desc);
create index if not exists idx_bioassay_results_treatment on public.bioassay_results (treatment_name);
create index if not exists idx_bioassay_results_batch_ref on public.bioassay_results (batch_reference);

-- 4. Constraints ------------------------------------------------------------------
-- The application already validates all of this in submit_bioassay_result(). The database
-- should not depend on the application getting it right — the same argument
-- sql/enforce_collector_id.sql makes about blank collector_ids.
--
-- ⚠ ADDING A CHECK TO A TABLE WITH EXISTING ROWS FAILS IF ANY ROW VIOLATES IT.
-- Run this first and confirm it returns 0 rows before running the section below:
--
--   select count(*) from public.bioassay_results
--    where mosquitoes_exposed is null or mosquitoes_exposed <= 0
--       or mortality_24hr is null or mortality_24hr < 0
--       or mortality_24hr > mosquitoes_exposed
--       or (knockdown_60min is not null
--           and (knockdown_60min < 0 or knockdown_60min > mosquitoes_exposed))
--       or replicate_number is null or replicate_number <= 0
--       or concentration_pct is null or concentration_pct < 0;
--
-- If it returns rows, fix or delete them first — a violating row is a bad measurement
-- (more dead mosquitoes than were exposed), not a constraint to relax.

alter table public.bioassay_results
  drop constraint if exists bioassay_results_exposed_positive;
alter table public.bioassay_results
  add constraint bioassay_results_exposed_positive
  check (mosquitoes_exposed > 0);

-- A replicate cannot kill more mosquitoes than it exposed.
alter table public.bioassay_results
  drop constraint if exists bioassay_results_mortality_within_exposed;
alter table public.bioassay_results
  add constraint bioassay_results_mortality_within_exposed
  check (mortality_24hr >= 0 and mortality_24hr <= mosquitoes_exposed);

-- Nor knock down more. NULL stays allowed: "not recorded" is not "zero".
alter table public.bioassay_results
  drop constraint if exists bioassay_results_knockdown_within_exposed;
alter table public.bioassay_results
  add constraint bioassay_results_knockdown_within_exposed
  check (knockdown_60min is null
         or (knockdown_60min >= 0 and knockdown_60min <= mosquitoes_exposed));

alter table public.bioassay_results
  drop constraint if exists bioassay_results_replicate_positive;
alter table public.bioassay_results
  add constraint bioassay_results_replicate_positive
  check (replicate_number > 0);

alter table public.bioassay_results
  drop constraint if exists bioassay_results_concentration_non_negative;
alter table public.bioassay_results
  add constraint bioassay_results_concentration_non_negative
  check (concentration_pct >= 0);

-- Deliberately NOT added: a uniqueness constraint over
-- (assay_date, treatment_name, concentration_pct, replicate_number, is_control).
-- The app does not enforce it, and re-running a replicate on the same day with the same
-- label is a real thing that happens in a lab. A constraint the app does not know about
-- would surface as an opaque insert failure at the bench.

-- 5. Row-level security -----------------------------------------------------------
-- Insert, read, delete — matching what the app does. No UPDATE policy, by the same
-- reasoning as sql/add_delete_policies.sql. Under RLS a statement with no matching policy
-- matches zero rows *without raising*, so a missing policy here looks like an empty table
-- or a silently discarded save.
alter table public.bioassay_results enable row level security;

drop policy if exists "Authenticated users can insert bioassay results" on public.bioassay_results;
create policy "Authenticated users can insert bioassay results"
  on public.bioassay_results
  for insert
  to authenticated
  with check (true);

drop policy if exists "Authenticated users can read bioassay results" on public.bioassay_results;
create policy "Authenticated users can read bioassay results"
  on public.bioassay_results
  for select
  to authenticated
  using (true);

drop policy if exists "Authenticated users can delete bioassay results" on public.bioassay_results;
create policy "Authenticated users can delete bioassay results"
  on public.bioassay_results
  for delete
  to authenticated
  using (true);

-- 6. Verify ------------------------------------------------------------------------
-- Diff this against the table definition above. A column here that is missing from this
-- file means the live table drifted; update the file rather than dropping the column.
select column_name, data_type, is_nullable, column_default
from information_schema.columns
where table_schema = 'public' and table_name = 'bioassay_results'
order by ordinal_position;

-- Policies should list INSERT, SELECT and DELETE. If you see duplicates under other
-- names, they are hand-created leftovers — policies are OR'd, so extras only widen
-- access. Drop the ones you did not intend.
select policyname, cmd as command, roles
from pg_policies
where schemaname = 'public' and tablename = 'bioassay_results'
order by cmd, policyname;
