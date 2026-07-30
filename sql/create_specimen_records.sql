-- Supabase/Postgres-compatible migration for specimen_records
-- Creates a table for linking field-screened specimens to PCR confirmation results.

create extension if not exists "uuid-ossp";

create type pcr_status as enum (
  'not_submitted',
  'pending',
  'confirmed'
);

create table if not exists public.specimen_records (
    specimen_id uuid primary key default uuid_generate_v4(),
    collection_date date not null,
    collector_id text not null,
    gps_lat double precision,
    gps_lon double precision,
    breeding_site_type text,
    -- Administrative area of the collection event, and the DHIS2 org unit dimension.
    -- See sql/add_lga_column.sql (migration for existing databases).
    lga text,
    photo_urls text[] default array[]::text[],
    field_screening_result jsonb not null default '{}'::jsonb,
    pcr_status pcr_status not null default 'not_submitted',
    pcr_confirmed_species text,
    pcr_lab_reference text,
    pcr_confirmed_date date,
    -- Subsampling: an individual specimen vialed out of a batch links back to it here.
    -- See sql/add_specimen_subsampling.sql (migration for existing databases).
    parent_specimen_id uuid references public.specimen_records (specimen_id) on delete set null,
    tube_label text,
    specimen_role text not null default 'primary',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists idx_specimen_records_collection_date on public.specimen_records (collection_date);
create index if not exists idx_specimen_records_collector_id on public.specimen_records (collector_id);
create index if not exists idx_specimen_records_pcr_status on public.specimen_records (pcr_status);
create index if not exists idx_specimen_records_parent on public.specimen_records (parent_specimen_id);
create index if not exists idx_specimen_records_lga on public.specimen_records (lga);

create or replace function public.set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_specimen_records_updated_at
before update on public.specimen_records
for each row
execute function public.set_updated_at();
