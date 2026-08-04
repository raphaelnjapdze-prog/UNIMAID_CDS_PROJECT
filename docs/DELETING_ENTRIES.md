# Deleting entries — clearing a trial run

Two ways to delete, depending on how much you want gone. Both are permanent: there is no
undo and no recycle bin. **Export anything you need first** — Profile → Data & Privacy →
*Download my survey submissions (CSV)*.

## Who can delete what

> **You can delete the entries you recorded. You cannot delete anyone else's.**
> A registered administrator can delete any entry, including everyone's at once.

Ownership is the `collector_id` stamped on the row when it was saved, so it is exactly
"who logged this". The rule is enforced by the database, in the `DELETE` policy — not by
the app's screens. That distinction matters: the app's anon key plus a user's own login
token is enough to call the Supabase REST API directly, so a rule that lived only in the
UI would be no rule at all. The app applies the same check before it asks, purely so the
refusal can be *explained*; RLS on its own just matches zero rows, which looks identical
to "already deleted".

Two consequences worth knowing:

- Entries marked `unattributed-legacy` predate identity tracking. Their author was never
  recorded and cannot be recovered, so nobody can claim them — **only an admin can delete
  them.**
- `bioassay_results` and `clinical_case_data` rows written before `submitted_by` was
  populated have no owner either, and are likewise admin-only.

## One-time setup

In the Supabase SQL Editor, run in this order:

1. **`sql/add_delete_policies.sql`**
2. **`sql/add_ownership_delete_policies.sql`** — replaces the first migration's blanket
   "any authenticated user may delete anything" policies with the ownership rule above.
   On a fresh database this one is self-contained, so you can skip straight to it.
3. `python scripts/migrate_photo_paths.py --apply` — moves existing photo objects onto the
   owner-prefixed path (see [Photo objects](#photo-objects-carry-their-owner) below).
   Needs `SUPABASE_SERVICE_ROLE_KEY`.
4. **`sql/add_photo_ownership.sql`** — applies the same ownership rule to the
   `specimen-photos` bucket.

Steps 3 and 4 are in that order on purpose. Neither is destructive the other way round, but
applying the policy before moving the objects leaves every un-migrated photo admin-only to
delete, which looks like deletion having broken.

### Registering an administrator

`sql/add_ownership_delete_policies.sql` creates a `public.app_admins` table. It starts
empty, so **until you add yourself, nobody is an admin** and the project-wide controls
stay hidden. Find your user id under *Authentication → Users* in the Supabase dashboard
(or `select id, email from auth.users;`), then:

```sql
insert into public.app_admins (user_id, note)
values ('<your-uuid>', 'Raphael — project owner')
on conflict (user_id) do nothing;
```

The table has deliberately **no** insert/update/delete policy, so admins can only be added
here, with the service role. A compromised login cannot promote itself.

### Setting the delete passkey

The admin "delete every entry" control asks for a passkey on top of being an admin.
Generate one and store its hash — the passkey itself is never written anywhere:

```bash
python scripts/hash_admin_passkey.py
```

Paste the printed `ADMIN_DELETE_PASSKEY_HASH = "..."` into `.streamlit/secrets.toml` (or
the environment). Keep the passkey itself in a password manager; it cannot be recovered
from the app or this repository.

**Until this is set, the project-wide delete is disabled** — it fails closed rather than
defaulting to open. It is also a *separate* credential from your login password, on
purpose: otherwise anyone who can sign in as the admin can also empty the project.

To be clear about what the passkey is and is not: it is a confirmation step, not the
security boundary. A registered admin holding their own token could delete through the API
without ever seeing the prompt. What it buys is that an unattended admin session, a
borrowed laptop, or a misclick cannot wipe the project.

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

Its **section 5 proves the ownership rule**, which is the opposite property from the rest
of the file: everything else checks that deletion *works*, and a blanket `using (true)`
policy passes all of it while letting anyone wipe a colleague's field season. Section 5
acts as two different investigators and an admin — by setting `request.jwt.claims`, which
is where `auth.uid()` looks, since the SQL Editor sets no JWT of its own — and asserts:

| Check | Expected |
|---|---|
| A deletes their own entry | 1 row — the rule must not lock people out of their own data |
| A deletes B's entry | **0 rows** |
| A deletes an `unattributed-legacy` entry | **0 rows** |
| An unfiltered `DELETE` as A | **0 rows** — no way around it via a broad `WHERE` |
| An admin deletes B's and the legacy entry | 2 rows |
| `is_app_admin()` for an unregistered user | **false** — catches a definer function that returns true for everyone |

Zero rows is the pass for the negative cases, and it has to be asserted rather than
eyeballed: RLS refuses by matching nothing, not by raising, so "refused" and "already
deleted" look identical from outside.

> **Note:** the *Provision Remote Tables* button on Profile → Security cannot do any of
> this. It needs `SUPABASE_SERVICE_ROLE_KEY` (not currently set) **and** a `public.sql(sql
> text)` function in the database, which does not exist — `data_manager.py::attempt_create_supabase_table`
> calls `rpc("sql", …)` and gets a `PGRST202 could not find the function` back. Migrations
> are run by hand in the SQL Editor.

## Deleting individual entries

**Site Log → Recently Logged Entries → 🗑️ Delete entries**

1. Pick one or more collection events from the list. **The list shows only your own
   entries** (an admin sees everyone's). If entries by other investigators were filtered
   out, a line beneath the picker says how many.
2. If any of them have specimens vialed out for PCR, a warning names how many. Those
   individuals are deleted too — an individual specimen cannot outlive the collection
   event it came from.
3. Type `DELETE` and press **Delete permanently**.

Use this when a few test rows need to go and the rest of the data is real.

## Clearing everything for a fresh trial

**Profile → Danger Zone → Reset Logged Data**

1. Choose the scope:
   - **Only records I collected** (default) — leaves other investigators' data alone.
   - **Every record in the project** — everything, whoever logged it. *Admins only; the
     option is not shown to anyone else.*
2. Optionally also tick **bioassay results** and **clinical case records**. These two are
   always project-wide; they carry no per-collector scoping, which is why they are
   **admin-only** and the checkboxes do not appear otherwise.
3. If anything you picked reaches beyond your own records — the project-wide scope, or
   either side table — an **Administrator delete passkey** field appears. Enter it.
4. Type `RESET` and press **Delete logged data permanently**.

This is the "clean slate before a presentation" path, and it is the **only** project-wide
delete in the app.

The Site Log page used to carry a second one (*🛑 Administrator: delete every entry in the
project*). It has been removed. There were two controls doing the same irreversible thing
with different confirmations, and the split was worse than redundant: the Site Log copy
asked for the delete passkey, while this one — reachable just by picking "Every record in
the project" from the radio — did not. The passkey now guards the single remaining path.

Scoping the reset to your own records does **not** ask for the passkey. Clearing a trial
run you logged yourself is an ordinary action; the passkey is there for the administrative
one.

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

- *"N selected entr(y/ies) were left alone because another investigator recorded them."*
  Working as intended — you can only delete your own. Ask that investigator to delete
  them, or ask an admin.
- *"Only a registered administrator can delete every entry in the project."* Nobody has
  been added to `public.app_admins` yet, or you are not one of them. See
  *Registering an administrator* above.
- *"No delete passkey is configured, so this is disabled."* `ADMIN_DELETE_PASSKEY_HASH` is
  not set. Generate one with `python scripts/hash_admin_passkey.py`.
- *"N record(s) were not deleted — the database refused them."* Row-level security is
  hiding them from this account. They belong to another collector; sign in as that account
  or delete them from the Supabase table editor. If you *are* an admin and still see this,
  check that `public.app_admins` contains your uid and that
  `sql/add_ownership_delete_policies.sql` has been run.
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
- **"N photo(s) are still in storage"** means the bucket refused to remove them. It does
  not refuse loudly: a delete with no matching policy comes back as an empty success, so
  the app counts the objects the bucket confirms and reports the difference rather than
  taking the call at its word. The records are already gone, so nothing points at those
  files any more, but they still use quota and are still served at their public URL. Two
  causes, in likelihood order: the objects predate the ownership migration and are not yet
  owner-prefixed (run `python scripts/migrate_photo_paths.py --apply`), or the bucket has
  no DELETE policy at all (run `sql/add_photo_ownership.sql`). Then clear any leftovers
  under **Storage** in the dashboard.

## Photo objects carry their owner

The ownership rule covers the `specimen-photos` bucket too, and the mechanism is worth
knowing because it constrains where photos may be stored.

Objects live at **`{collector_id}/{specimen_id}/{uuid}.ext`**. The leading segment is the
whole point: it is the only thing a storage policy can read to decide who owns an object.
`storage.objects` has no foreign key back to `specimen_records`, and the app deletes a row
*before* its photos — deliberately, so a blocked photo delete can never leave a row citing
a URL that no longer resolves. A policy that joined back to `specimen_records` to find the
owner would therefore find the row already gone and refuse every legitimate delete. With
the owner in the path the check is local to the object and needs nothing else to still
exist:

```sql
(storage.foldername(name))[1] = auth.uid()::text or public.is_app_admin()
```

The upload policy is scoped the same way, to your own prefix. Without that half the
ownership would be decorative — anyone could upload into someone else's prefix and then
delete it, since the DELETE policy would read that prefix and agree it was theirs.

Reading is still public, matching the bucket: the stored URLs are fetched by the browser
with no token, from the reports and dashboard pages. Nothing here changes who may *look*
at a specimen photo.

### Legacy objects

Objects uploaded before this migration sit at `{specimen_id}/{uuid}.ext`. Their first path
segment is a specimen id, not a uid, so they match no user and become **admin-only to
delete** until moved. That is the safe direction to fail — nothing is deleted that should
not be, and the app reports what the bucket declined rather than claiming a cleanup that
did not happen — but a non-admin clearing their own old entries will see *"N photo(s) are
still in storage"* until you run:

```bash
python scripts/migrate_photo_paths.py            # dry run, changes nothing
python scripts/migrate_photo_paths.py --apply
```

It moves each object and rewrites the `photo_urls` that point at it. Safe to re-run:
already-prefixed objects are skipped and nothing is deleted — the move is a rename, and a
row's URLs are rewritten only after its objects have actually moved. It needs
`SUPABASE_SERVICE_ROLE_KEY`, because it moves other investigators' objects and rewrites
their rows, which is exactly what RLS is there to stop a normal session doing.

Objects whose specimen row is gone, or whose collector is `unattributed-legacy`, are left
where they are: there is no owner to file them under, and inventing one would hand
somebody the right to delete them. `sql/add_photo_ownership.sql` ends with a query that
counts what is left.

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
