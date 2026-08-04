"""Move specimen photos onto the owner-prefixed path that sql/add_photo_ownership.sql scopes by.

    python scripts/migrate_photo_paths.py            # dry run — reports, changes nothing
    python scripts/migrate_photo_paths.py --apply    # actually move the objects
    python scripts/migrate_photo_paths.py --apply --limit 50

Objects used to be stored at '{specimen_id}/{uuid}.ext'. Nothing in that path says who
owns the object, so the bucket's DELETE policy could not be scoped and stayed open to
every authenticated user. Uploads now write '{collector_id}/{specimen_id}/{uuid}.ext'
(utils/data_manager.py::_upload_photo_bytes); this script moves everything already in the
bucket into the same shape, and rewrites the photo_urls that point at it.

Run this BEFORE sql/add_photo_ownership.sql. The order is not destructive either way, but
applying the policy first leaves every un-migrated object admin-only to delete, which
looks like deletion having broken.

Requires SUPABASE_SERVICE_ROLE_KEY. The migration moves objects belonging to other
investigators and rewrites their rows, which is exactly what RLS is there to stop a user
doing — so it runs with the service role or not at all.

Safe to re-run: objects already owner-prefixed are skipped, and the move is per-object, so
an interrupted run resumes where it stopped. Nothing is deleted — move() is a rename, and
a row's photo_urls are rewritten only after its object has actually moved.

Exit codes: 0 nothing left to do (or the dry run completed), 1 some objects could not be
migrated, 2 usage/configuration error (no service role key, bucket unreachable).
"""

import argparse
import sys
from collections import defaultdict
from pathlib import Path

# The script lives in scripts/, so the repo root isn't on sys.path when run directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from utils.auth import get_supabase_service_client  # noqa: E402
from utils.config import SUPABASE_SERVICE_ENABLED  # noqa: E402
from utils.data_manager import _PHOTO_BUCKET, _storage_path_from_public_url  # noqa: E402

# The bucket is listed a page at a time; the API caps what one call returns.
_PAGE = 100


def _is_owner_prefixed(path: str) -> bool:
    """Whether `path` already opens with an owner segment.

    Three segments means '{owner}/{specimen_id}/{uuid.ext}' — the shape uploads write now.
    Two means the legacy '{specimen_id}/{uuid.ext}'. Anything else (a stray object at the
    bucket root, a hand-made deeper path) is left alone rather than guessed at: this script
    moves objects, and a wrong guess about which segment is the owner would file someone
    else's photo under a prefix that lets them delete it.
    """
    return len(path.split("/")) >= 3


def _list_all_objects(storage) -> list[str]:
    """Every object path in the bucket, walked one directory level down.

    The storage list API is not recursive: listing the bucket root returns the top-level
    "folders" (the specimen ids, or the owner ids once migrated), and each has to be listed
    in turn. Objects are identified by carrying an `id` — folder placeholders come back
    with a null one, which is how a prefix is told from a file.
    """
    paths: list[str] = []

    def _page(prefix: str) -> list[dict]:
        out, offset = [], 0
        while True:
            batch = storage.list(prefix, {"limit": _PAGE, "offset": offset})
            if not batch:
                return out
            out.extend(batch)
            if len(batch) < _PAGE:
                return out
            offset += len(batch)

    for top in _page(""):
        name = top.get("name")
        if not name:
            continue
        if top.get("id"):
            paths.append(name)  # a file sitting at the bucket root
            continue
        for entry in _page(name):
            child = entry.get("name")
            if not child:
                continue
            if entry.get("id"):
                paths.append(f"{name}/{child}")
                continue
            # One level deeper: already-migrated objects live at owner/specimen/file.
            for leaf in _page(f"{name}/{child}"):
                if leaf.get("id") and leaf.get("name"):
                    paths.append(f"{name}/{child}/{leaf['name']}")
    return paths


def _owner_by_specimen(client, specimen_ids: set[str]) -> dict[str, str]:
    """collector_id for each specimen id, read with the service role so RLS does not hide
    other investigators' rows — the ones that most need migrating."""
    owners: dict[str, str] = {}
    ids = sorted(specimen_ids)
    for start in range(0, len(ids), 80):  # the ids go in the query string; keep it short
        chunk = ids[start:start + 80]
        response = (
            client.table("specimen_records")
            .select("specimen_id, collector_id")
            .in_("specimen_id", chunk)
            .execute()
        )
        for row in getattr(response, "data", None) or []:
            owner = str(row.get("collector_id") or "").strip()
            # 'unattributed-legacy' rows predate identity tracking and belong to nobody.
            # Prefixing an object with that string would invent an owner; leave them where
            # they are, admin-only to delete, which is the honest answer.
            if owner and owner != "unattributed-legacy":
                owners[row["specimen_id"]] = owner
    return owners


def _rewrite_row_urls(client, specimen_id: str, moves: dict[str, str]) -> bool:
    """Point a row's photo_urls at the objects' new paths.

    Done per row after its objects have moved. The stored value is a full public URL, so
    the old bucket-relative path is swapped inside it rather than the URL rebuilt — that
    keeps whatever host and query string the row already had.
    """
    response = (
        client.table("specimen_records")
        .select("photo_urls")
        .eq("specimen_id", specimen_id)
        .execute()
    )
    rows = getattr(response, "data", None) or []
    if not rows:
        return True  # row gone; its objects are orphans either way
    current = rows[0].get("photo_urls") or []
    updated, changed = [], False
    for url in current:
        path = _storage_path_from_public_url(url)
        if path and path in moves:
            updated.append(url.replace(path, moves[path], 1))
            changed = True
        else:
            updated.append(url)
    if not changed:
        return True
    result = (
        client.table("specimen_records")
        .update({"photo_urls": updated})
        .eq("specimen_id", specimen_id)
        .execute()
    )
    # RLS makes an UPDATE with no matching policy affect zero rows without raising. The
    # service role is not subject to it, but verify rather than assume — a row whose
    # objects moved while its URLs did not is a record pointing at 400s.
    if getattr(result, "data", None):
        return True
    print(f"  ! photo_urls not updated for {specimen_id} — its URLs still point at the old paths")
    return False


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Move specimen photos onto owner-prefixed storage paths.",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="Perform the moves. Without it the script reports what it would do and exits.",
    )
    parser.add_argument(
        "--limit", type=int, default=0,
        help="Stop after this many objects (0 = no limit). Useful for a first cautious run.",
    )
    args = parser.parse_args(argv)

    if not SUPABASE_SERVICE_ENABLED:
        print(
            "SUPABASE_SERVICE_ROLE_KEY is not configured.\n"
            "This migration moves other investigators' objects and rewrites their rows, "
            "which RLS correctly refuses to a normal session. Set the service role key in "
            "your secrets and re-run.",
            file=sys.stderr,
        )
        return 2

    client = get_supabase_service_client()
    if client is None:
        print("Could not build a service-role Supabase client.", file=sys.stderr)
        return 2

    storage = client.storage.from_(_PHOTO_BUCKET)
    try:
        paths = _list_all_objects(storage)
    except Exception as e:
        print(f"Could not list the {_PHOTO_BUCKET} bucket: {e}", file=sys.stderr)
        return 2

    legacy = [p for p in paths if not _is_owner_prefixed(p)]
    print(f"{len(paths)} object(s) in {_PHOTO_BUCKET}: "
          f"{len(paths) - len(legacy)} already owner-prefixed, {len(legacy)} to migrate.")
    if not legacy:
        return 0

    # Group by the specimen id the legacy path opens with, so each row's URLs are
    # rewritten once, after all of its objects have moved.
    by_specimen: dict[str, list[str]] = defaultdict(list)
    for path in legacy:
        by_specimen[path.split("/")[0]].append(path)

    owners = _owner_by_specimen(client, set(by_specimen))
    unresolved = sorted(set(by_specimen) - set(owners))
    if unresolved:
        print(
            f"\n{len(unresolved)} specimen id(s) have no usable collector_id — no row, or "
            "'unattributed-legacy'. Their objects are left where they are (admin-only to "
            f"delete): {', '.join(unresolved[:5])}"
            + (" …" if len(unresolved) > 5 else "")
        )

    planned = [
        (path, f"{owners[specimen_id]}/{path}")
        for specimen_id, group in sorted(by_specimen.items())
        if specimen_id in owners
        for path in sorted(group)
    ]
    if args.limit:
        planned = planned[:args.limit]

    if not args.apply:
        print(f"\nDry run — {len(planned)} object(s) would move. Sample:")
        for old, new in planned[:10]:
            print(f"  {old}\n    -> {new}")
        if len(planned) > 10:
            print(f"  … and {len(planned) - 10} more")
        print("\nRe-run with --apply to perform the moves.")
        return 0

    moved: dict[str, dict[str, str]] = defaultdict(dict)
    failures = 0
    for old, new in planned:
        try:
            storage.move(old, new)
            moved[old.split("/")[0]][old] = new
        except Exception as e:
            failures += 1
            print(f"  ! could not move {old}: {e}")

    total_moved = sum(len(m) for m in moved.values())
    print(f"\nMoved {total_moved} object(s).")

    url_failures = 0
    for specimen_id, moves in sorted(moved.items()):
        if not _rewrite_row_urls(client, specimen_id, moves):
            url_failures += 1
    if url_failures:
        print(f"{url_failures} row(s) still cite the old paths — re-run to retry.")

    remaining = len(legacy) - total_moved
    if remaining:
        print(f"{remaining} object(s) were not migrated (unresolved owner, or a failed move).")
    if failures or url_failures or unresolved:
        return 1
    print("\nAll objects are owner-prefixed. Now run sql/add_photo_ownership.sql.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
