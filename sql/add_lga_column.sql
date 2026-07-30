-- Migration: record which LGA a collection event happened in.
--
-- Run this in the Supabase SQL Editor. Safe to re-run.
--
-- Why this exists
-- ---------------
-- specimen_records could say what *kind* of place a specimen came from
-- (breeding_site_type: "Rice Field", "Drain") and its coordinates, but not what
-- administrative area it was in. The DHIS2 export needs the latter: DHIS2 org units are
-- places — LGAs, wards, facilities — and a habitat category is not a place. Lacking one,
-- the export derived its org unit from breeding_site_type, which produced identifiers no
-- DHIS2 instance could match to anything.
--
-- gps_lat/gps_lon are not a substitute. They are optional in the Site Log, they say
-- nothing on their own without a boundary lookup, and a point near an LGA border is
-- exactly the case you do not want resolved by guesswork.
--
-- Nullable on purpose: rows logged before this migration have no LGA and must not be
-- rewritten to claim one. The export reports them as unmapped rather than inventing a
-- location, and they can be corrected by hand if it matters.

alter table public.specimen_records
  add column if not exists lga text;

comment on column public.specimen_records.lga is
  'Local Government Area of the collection event. Maps to a DHIS2 org unit; see '
  'utils/dhis2_client.py. Null for rows logged before this column existed.';

-- The DHIS2 export groups by (collection_date, lga, genus), and the dashboard filters by
-- area. Both scan on this.
create index if not exists idx_specimen_records_lga on public.specimen_records (lga);

-- ---------------------------------------------------------------------------
-- Confirm.
-- ---------------------------------------------------------------------------
-- Expect one row: lga | text | YES (nullable).
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'specimen_records' and column_name = 'lga';

-- How many existing rows predate the column. These export as unmapped until an LGA is set;
-- that is the honest outcome, not a bug to paper over.
select count(*) filter (where lga is null) as rows_without_lga,
       count(*)                            as rows_total
from public.specimen_records;
