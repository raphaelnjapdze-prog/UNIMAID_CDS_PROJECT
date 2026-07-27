# Deleting entries — clearing a trial run

Two ways to delete, depending on how much you want gone. Both are permanent: there is no
undo and no recycle bin. **Export anything you need first** — Profile → Data & Privacy →
*Download my survey submissions (CSV)*.

## One-time setup

Run **`sql/add_delete_policies.sql`** once in the Supabase SQL Editor.

Without it, deletion silently does nothing. Supabase row-level security makes a `DELETE`
with no matching policy match zero rows *without raising an error*, so the app has no way
to tell "deleted" from "refused". Photo objects are a separate policy surface from table
rows, which is why deleting photos could appear to work while every row stayed put — the
bucket had a delete policy and the tables did not. The migration adds both.

The delete helpers now check the rows the database actually returned, so if the policies
are missing you will see:

> The database accepted no deletions — check that a DELETE policy exists on
> specimen_records (run sql/add_delete_policies.sql in the Supabase SQL Editor).

The migration ends with a `select` that lists the policies; you should see a `DELETE` row
for `specimen_records`, `bioassay_results`, `clinical_case_data`, and one on
`storage.objects` for the `specimen-photos` bucket.

Then run **`sql/verify_deletion.sql`** to confirm it worked. It checks the policies, then
actually inserts a batch with two vialed-out individuals, deletes them **as the
`authenticated` role** — the role your logged-in users get, not the `postgres` role the SQL
Editor runs as, which bypasses RLS entirely and would pass regardless — and rolls the whole
thing back. Read the PASS/FAIL column of each result. Nothing it does persists.

> **Note:** the *Provision Remote Tables* button on Profile → Security cannot do any of
> this. It needs `SUPABASE_SERVICE_ROLE_KEY` (not currently set) **and** a `public.sql(sql
> text)` function in the database, which does not exist — `data_manager.py::attempt_create_supabase_table`
> calls `rpc("sql", …)` and gets a `PGRST202 could not find the function` back. Migrations
> are run by hand in the SQL Editor.

## Deleting individual entries

**Site Log → Recently Logged Entries → 🗑️ Delete entries**

1. Pick one or more collection events from the list.
2. If any of them have specimens vialed out for PCR, a warning names how many. Those
   individuals are deleted too — an individual specimen cannot outlive the collection
   event it came from.
3. Type `DELETE` and press **Delete permanently**.

Use this when a few test rows need to go and the rest of the data is real.

## Clearing everything for a fresh trial

**Profile → Danger Zone → Reset Logged Data**

1. Choose the scope:
   - **Only records I collected** (default) — leaves other investigators' data alone.
   - **Every record in the project** — everything, whoever logged it.
2. Optionally also tick **bioassay results** and **clinical case records**. These two are
   always project-wide; they carry no per-collector scoping.
3. Type `RESET` and press **Delete logged data permanently**.

This is the "clean slate before a presentation" path.

The Dashboard reads through a 60-second cache, so give it up to a minute or reload the
page before screenshotting the cleared state.

## What a delete actually removes

Deleting a specimen row is not just one `DELETE`. Three things travel with it, and getting
any of them wrong is what left the half-cleaned state behind:

| | Why it matters |
|---|---|
| **Its photos** | They live in the `specimen-photos` Storage bucket, not in the row. Dropping the row alone orphans the objects — they keep counting against your storage quota and stay publicly reachable by URL. |
| **Its vialed-out individuals** | `parent_specimen_id` is declared `on delete set null`, so a plain `DELETE` on a batch does not remove its children — it detaches them into individuals whose collection event no longer exists. They are deleted with the batch instead. |
| **The batch's tally** | A batch reports `raw count − vialed_out`. Deleting one vialed individual decrements that tally, so the specimen returns to the batch and becomes available to vial again. Without this, deleting a vial would quietly remove a real, caught mosquito from every total. |

That last point is the no-double-count invariant from `CLAUDE.md`, running in reverse:
**batch + children always conserve the original catch total**, before and after a delete.
`tests/test_deletion.py::TestDeletingAChildRestoresItToItsBatch::test_catch_total_is_conserved`
pins it.

## When something does not go cleanly

The app reports partial failures rather than showing a clean-looking success:

- *"N record(s) were not deleted — the database refused them."* Row-level security is
  hiding them from this account. They belong to another collector; sign in as that account
  or delete them from the Supabase table editor.
- *"N batch tall(y/ies) could not be corrected."* The rows were deleted but a batch's
  `vialed_out` count could not be decremented, so that collection event now reports fewer
  specimens than were caught. Check that `sql/add_update_policies.sql` has been run, then
  fix the batch's count in the Supabase table editor.
- *"Could not identify the primary-key column on `bioassay_results`."* That table's key
  column isn't one the app recognises. It looks for `id` first — see
  `sql/create_bioassay_results.sql` / `sql/create_clinical_case_data.sql` for the expected
  shape, and run each file's closing query to see what the live table actually has. Those
  two schemas were reconstructed from the app's reads and writes, because both tables were
  created by hand in the dashboard before the files existed; the live tables win, so update
  the file if they differ. Until then, clear those rows from the Supabase table editor.
- A photo that fails to delete never blocks the row — otherwise an unreachable bucket
  would make the ledger impossible to clean up. The row goes; the object is left and
  logged.

## Doing it straight from Supabase

For a full wipe outside the app (Supabase SQL Editor):

```sql
-- Rows. Children first: parent_specimen_id references the batch.
delete from public.specimen_records where specimen_role = 'individual';
delete from public.specimen_records;
delete from public.bioassay_results;
delete from public.clinical_case_data;
```

Then empty the `specimen-photos` bucket under **Storage** in the dashboard — SQL does not
touch storage objects, and this is the step that gets skipped. Rows deleted in SQL are gone
before the app can decrement any tally, which is fine for a total wipe but not for
deleting a subset: for that, use the in-app paths above so the batch counts stay honest.
