# scripts/

Standalone developer utilities — run by hand from the repo root, not imported by the
app and not collected by `pytest` (they live outside `tests/`). Each script puts the
repo root on `sys.path` so `utils.*` imports resolve when run directly.

## `test_image_qc.py`

Runs the image quality-control check — the same `utils.image_quality_control.assess_image_quality()`
the Diagnostics page runs before AI screening — against a specimen photo, so you can
see why a given image is (or isn't) flagged.

```bash
python scripts/test_image_qc.py path/to/specimen.jpg
python scripts/test_image_qc.py path/to/specimen.jpg --save enhanced.jpg
```

Prints `Passed`, the reason, and the blur/exposure scores when the report carries them.
`--save` writes the enhanced/processed image for inspection. Exit codes: `0` pass,
`1` fail, `2` usage/IO error (e.g. the image can't be opened) — usable in a pipeline.

## `migrate_photo_paths.py`

One-time migration: moves objects in the `specimen-photos` bucket from the legacy
`{specimen_id}/{uuid}.ext` onto `{collector_id}/{specimen_id}/{uuid}.ext`, and rewrites the
`photo_urls` pointing at them. The leading segment is what the bucket's ownership policies
read — see `sql/add_photo_ownership.sql` and `docs/DELETING_ENTRIES.md`.

```bash
python scripts/migrate_photo_paths.py            # dry run — reports, changes nothing
python scripts/migrate_photo_paths.py --apply
python scripts/migrate_photo_paths.py --apply --limit 50
```

**Run this before `sql/add_photo_ownership.sql`.** Neither order is destructive, but
applying the policy first leaves every un-migrated object admin-only to delete, which looks
like deletion having broken.

Requires `SUPABASE_SERVICE_ROLE_KEY`: it moves other investigators' objects and rewrites
their rows, which RLS correctly refuses to a normal session. Safe to re-run — already
prefixed objects are skipped, nothing is deleted (the move is a rename), and a row's URLs
are rewritten only after its objects have moved. Objects with no resolvable owner (row
gone, or `unattributed-legacy`) are left alone rather than filed under an invented owner.
Exit codes: `0` nothing left to do or dry run complete, `1` some objects could not be
migrated, `2` usage/configuration error.
