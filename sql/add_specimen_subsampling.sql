-- Migration: individual specimen subsampling ("vialing out") from a batch field log.
--
-- Adds per-individual identity so a single mosquito subsampled from a bulk field
-- count (e.g. one of 500 Anopheles) can be barcoded, morphologically identified,
-- and PCR-confirmed on its own, while staying linked to the batch it came from.
-- See utils/data_manager.py::vial_out_specimens.
--
-- Safe to run on an existing database — all changes are additive.

alter table public.specimen_records
    add column if not exists parent_specimen_id uuid
        references public.specimen_records (specimen_id) on delete set null,
    add column if not exists tube_label text,
    add column if not exists specimen_role text not null default 'primary';

-- Fast lookup of every individual vialed out of a given batch collection event.
create index if not exists idx_specimen_records_parent
    on public.specimen_records (parent_specimen_id);

-- specimen_role values:
--   'primary'    = a batch field-count log, or a standalone identification (all existing rows)
--   'individual' = a single specimen subsampled/vialed out of a parent batch
