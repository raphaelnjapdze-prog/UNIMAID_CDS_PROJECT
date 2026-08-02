"""Tests for deleting specimen entries — the trial-data cleanup path.

Three things have to happen together, and the reported bug was that only the first did:

  1. The Storage objects behind photo_urls go. Deleting rows alone leaves them orphaned:
     still counting against storage, still reachable by their public URL.
  2. A batch's vialed-out children go with the batch. parent_specimen_id is declared
     "on delete set null", so a plain DELETE detaches them into individuals whose
     collection event no longer exists instead of removing them.
  3. Deleting a child alone gives its specimen back to the batch. The batch reports
     raw − vialed_out, so a child that vanishes without its tally being decremented takes
     a real, caught mosquito out of every total — the no-double-count invariant in
     CLAUDE.md, running in reverse.

And under RLS a DELETE with no matching policy matches zero rows *without raising*, which
is what let the app appear to clear a trial run while every row stayed in the table. The
fake client below can simulate that, because "reports success, deleted nothing" is the
failure mode these functions exist to refuse.
"""
import pandas as pd
import pytest

from utils import data_manager as dm

BUCKET = "specimen-photos"


# --- A minimal in-memory stand-in for the Supabase client ---------------------------
class _Resp:
    def __init__(self, data):
        self.data = data


class _Query:
    def __init__(self, store, table):
        self.store, self.table = store, table
        self.op = "select"
        self.payload = None
        self.filters: list[tuple] = []
        self.limit_n = None

    def select(self, *_cols):
        self.op = "select"
        return self

    def delete(self):
        self.op = "delete"
        return self

    def update(self, payload):
        self.op, self.payload = "update", payload
        return self

    def eq(self, column, value):
        self.filters.append(("eq", column, value))
        return self

    def in_(self, column, values):
        self.filters.append(("in", column, list(values)))
        return self

    def limit(self, n):
        self.limit_n = n
        return self

    def _matches(self, row) -> bool:
        for kind, column, value in self.filters:
            if kind == "eq" and row.get(column) != value:
                return False
            if kind == "in" and row.get(column) not in value:
                return False
        return True

    def execute(self):
        rows = self.store.tables.setdefault(self.table, [])
        hit = [r for r in rows if self._matches(r)]
        if self.limit_n is not None:
            hit = hit[:self.limit_n]

        if self.op == "select":
            return _Resp([dict(r) for r in hit])
        if self.op == "delete":
            if self.table in self.store.blocked_deletes:
                return _Resp([])  # RLS: matches nothing, raises nothing
            self.store.tables[self.table] = [r for r in rows if not self._matches(r)]
            return _Resp([dict(r) for r in hit])
        if self.op == "update":
            if self.table in self.store.blocked_updates:
                return _Resp([])
            for row in hit:
                row.update(self.payload or {})
            return _Resp([dict(r) for r in hit])
        raise AssertionError(f"unsupported op {self.op}")


class _Bucket:
    def __init__(self, store, name):
        self.store, self.name = store, name

    def remove(self, paths):
        # Storage answers with the list of objects it deleted. Blocking is modelled as an
        # empty list, NOT an exception, because that is what the real API does: RLS on
        # storage.objects turns a delete with no matching policy into 200 [] — verified
        # against the live bucket. A fake that raised instead made the silent-no-op case
        # untestable, which is how the app came to report photos removed that were not.
        if self.store.storage_unreachable:
            raise RuntimeError("storage is unreachable")
        if self.store.blocked_storage:
            return []
        deleted = [p for p in paths if p in self.store.objects]
        for path in deleted:
            self.store.objects.discard(path)
        self.store.removed.extend(deleted)
        return [{"name": p} for p in deleted]


class _Storage:
    def __init__(self, store):
        self.store = store

    def from_(self, name):
        return _Bucket(self.store, name)


class FakeSupabase:
    def __init__(self, tables=None, objects=None):
        self.tables = {name: [dict(r) for r in rows] for name, rows in (tables or {}).items()}
        self.objects = set(objects or [])
        self.removed: list[str] = []
        self.blocked_deletes: set[str] = set()
        self.blocked_updates: set[str] = set()
        self.blocked_storage = False
        self.storage_unreachable = False
        self.storage = _Storage(self)

    def table(self, name):
        return _Query(self, name)

    def ids(self, table="specimen_records"):
        return sorted(r["specimen_id"] for r in self.tables.get(table, []))

    def row(self, specimen_id, table="specimen_records"):
        return next(r for r in self.tables[table] if r["specimen_id"] == specimen_id)


def _photo_url(specimen_id, name="a.jpg"):
    return f"https://proj.supabase.co/storage/v1/object/public/{BUCKET}/{specimen_id}/{name}"


def _batch(specimen_id="batch-1", *, anopheles=500, vialed=None, collector="me", photos=None):
    result = {"anopheles_count": anopheles, "culex_count": 0, "aedes_count": 0}
    if vialed:
        result["vialed_out"] = dict(vialed)
    return {
        "specimen_id": specimen_id,
        "parent_specimen_id": None,
        "specimen_role": "primary",
        "collector_id": collector,
        "collection_date": "2026-07-20",
        "photo_urls": list(photos or []),
        "field_screening_result": {"screening_method": "manual_field_log", "result": result},
    }


def _child(specimen_id, parent="batch-1", *, genus="Anopheles", identified=False,
           collector="me", photos=None):
    if identified:
        # An identified child no longer carries a field_subsample result; the genus it was
        # vialed as survives only under "subsampled_genus".
        screening = {
            "screening_method": "manual_checklist",
            "result": {"genus_triage": {"genus": genus}},
            "subsampled_genus": genus,
        }
    else:
        screening = {
            "screening_method": "field_subsample",
            "result": {"genus": genus, "pending_identification": True},
        }
    return {
        "specimen_id": specimen_id,
        "parent_specimen_id": parent,
        "specimen_role": "individual",
        "collector_id": collector,
        "collection_date": "2026-07-20",
        "photo_urls": list(photos or []),
        "field_screening_result": screening,
    }


@pytest.fixture
def fake(monkeypatch):
    """Point data_manager at an in-memory database. Returns a factory.

    Identity is part of the setup now that deletion is ownership-scoped: the caller is
    "me" unless told otherwise, which is the collector the row builders above stamp by
    default, and is not an admin. Tests about the ownership rule itself pass `user=` or
    `admin=` explicitly rather than relying on the default.
    """
    def build(tables=None, objects=None, *, user="me", admin=False):
        client = FakeSupabase(tables, objects)
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm, "get_current_user_id", lambda: user)
        monkeypatch.setattr(dm, "is_current_user_admin", lambda: admin)
        monkeypatch.setattr(dm, "clear_specimen_records_cache", lambda: None)
        monkeypatch.setattr(dm, "clear_bioassay_results_cache", lambda: None)
        monkeypatch.setattr(dm, "clear_clinical_case_data_cache", lambda: None)
        return client
    return build


def _total_specimens(client) -> dict:
    """Genus totals across the whole ledger, exactly as the dashboard aggregates them."""
    totals: dict[str, int] = {}
    for row in client.tables["specimen_records"]:
        for genus, count in dm.extract_genus_counts_from_screening(
            row.get("field_screening_result")
        ).items():
            totals[genus] = totals.get(genus, 0) + count
    return totals


class TestPhotoUrlParsing:
    def test_extracts_bucket_relative_path(self):
        assert dm._storage_path_from_public_url(_photo_url("s1")) == "s1/a.jpg"

    def test_strips_a_query_string(self):
        url = _photo_url("s1") + "?token=abc"
        assert dm._storage_path_from_public_url(url) == "s1/a.jpg"

    def test_url_from_another_bucket_is_left_alone(self):
        # Guessing a path here would delete somebody else's object.
        url = "https://proj.supabase.co/storage/v1/object/public/profile-avatars/u/av.png"
        assert dm._storage_path_from_public_url(url) is None

    @pytest.mark.parametrize("value", [None, "", 123, "not a url"])
    def test_junk_yields_no_path(self, value):
        assert dm._storage_path_from_public_url(value) is None


class TestSubsampledGenusIsRecoverable:
    def test_from_a_pending_vial(self):
        screening = _child("v1")["field_screening_result"]
        assert dm.subsampled_genus_of(screening) == "Anopheles"

    def test_from_an_identified_vial(self):
        screening = _child("v1", genus="Culex", identified=True)["field_screening_result"]
        assert dm.subsampled_genus_of(screening) == "Culex"

    def test_a_batch_is_not_a_subsample(self):
        assert dm.subsampled_genus_of(_batch()["field_screening_result"]) is None

    def test_junk_is_none(self):
        assert dm.subsampled_genus_of(None) is None
        assert dm.subsampled_genus_of("not json") is None


class TestDeletingAChildRestoresItToItsBatch:
    def test_tally_is_decremented(self, fake):
        client = fake({"specimen_records": [
            _batch(vialed={"Anopheles": 2}),
            _child("v1"), _child("v2"),
        ]})

        summary = dm.delete_specimen_records(["v1"])

        assert summary is not None and summary["deleted"] == 1
        batch = client.row("batch-1")
        assert batch["field_screening_result"]["result"]["vialed_out"] == {"Anopheles": 1}
        # The raw count is never touched — it is the collection event's record of the catch.
        assert batch["field_screening_result"]["result"]["anopheles_count"] == 500

    def test_catch_total_is_conserved(self, fake):
        """The property that matters: deleting an individual must not lose a mosquito."""
        client = fake({"specimen_records": [
            _batch(anopheles=500, vialed={"Anopheles": 2}),
            _child("v1"), _child("v2"),
        ]})
        before = _total_specimens(client)
        assert before == {"Anopheles": 500}  # 498 in the batch + 2 individuals

        dm.delete_specimen_records(["v1"])

        assert _total_specimens(client) == {"Anopheles": 500}

    def test_identified_child_credits_the_genus_it_was_vialed_as(self, fake):
        """An identification overwrites the child's screening result; the batch tally is
        keyed by the pile it came out of, which must still be found."""
        client = fake({"specimen_records": [
            _batch(vialed={"Culex": 1}),
            _child("v1", genus="Culex", identified=True),
        ]})

        dm.delete_specimen_records(["v1"])

        assert client.row("batch-1")["field_screening_result"]["result"]["vialed_out"] == {"Culex": 0}

    def test_tally_never_goes_negative(self, fake):
        client = fake({"specimen_records": [_batch(vialed={"Anopheles": 0}), _child("v1")]})

        dm.delete_specimen_records(["v1"])

        assert client.row("batch-1")["field_screening_result"]["result"]["vialed_out"]["Anopheles"] == 0

    def test_a_blocked_tally_update_is_reported_not_swallowed(self, fake):
        client = fake({"specimen_records": [_batch(vialed={"Anopheles": 1}), _child("v1")]})
        client.blocked_updates.add("specimen_records")

        summary = dm.delete_specimen_records(["v1"])

        # The row is gone but the batch is now short by one. Silence here would mean a
        # quietly wrong total for that collection event.
        assert summary is not None
        assert summary["tally_failures"] == ["batch-1"]
        assert summary["batches_restored"] == {}


class TestDeletingABatchTakesItsChildren:
    def test_children_are_cascaded(self, fake):
        client = fake({"specimen_records": [
            _batch(vialed={"Anopheles": 2}), _child("v1"), _child("v2"),
        ]})

        summary = dm.delete_specimen_records(["batch-1"])

        assert summary is not None
        assert client.ids() == []
        assert summary["deleted"] == 3
        assert summary["cascaded_children"] == 2

    def test_no_tally_restore_when_the_batch_goes_too(self, fake):
        client = fake({"specimen_records": [
            _batch(vialed={"Anopheles": 2}), _child("v1"), _child("v2"),
        ]})

        summary = dm.delete_specimen_records(["batch-1", "v1"])

        assert summary is not None
        assert summary["batches_restored"] == {}
        assert summary["tally_failures"] == []
        assert client.ids() == []

    def test_other_batches_children_are_untouched(self, fake):
        client = fake({"specimen_records": [
            _batch("batch-1", vialed={"Anopheles": 1}), _child("v1", parent="batch-1"),
            _batch("batch-2", vialed={"Anopheles": 1}), _child("v2", parent="batch-2"),
        ]})

        dm.delete_specimen_records(["batch-1"])

        assert client.ids() == ["batch-2", "v2"]


class TestPhotosGoWithTheRow:
    def test_objects_are_removed_from_the_bucket(self, fake):
        client = fake(
            {"specimen_records": [_batch(photos=[_photo_url("batch-1", "one.jpg"),
                                                 _photo_url("batch-1", "two.jpg")])]},
            objects={"batch-1/one.jpg", "batch-1/two.jpg"},
        )

        summary = dm.delete_specimen_records(["batch-1"])

        assert summary is not None and summary["photos_removed"] == 2
        assert client.objects == set()

    def test_cascaded_children_photos_go_too(self, fake):
        client = fake(
            {"specimen_records": [
                _batch(vialed={"Anopheles": 1}),
                _child("v1", photos=[_photo_url("v1", "lab.jpg")]),
            ]},
            objects={"v1/lab.jpg"},
        )

        dm.delete_specimen_records(["batch-1"])

        assert client.objects == set()

    def test_an_unreachable_bucket_does_not_block_the_row(self, fake):
        """Otherwise an unreachable bucket would make the ledger impossible to clean up."""
        client = fake(
            {"specimen_records": [_batch(photos=[_photo_url("batch-1")])]},
            objects={"batch-1/a.jpg"},
        )
        client.storage_unreachable = True

        summary = dm.delete_specimen_records(["batch-1"])

        assert summary is not None and summary["deleted"] == 1
        assert client.ids() == []
        assert summary["photos_removed"] == 0
        assert summary["photos_orphaned"] == 1

    def test_a_silently_blocked_remove_is_not_counted_as_removed(self, fake):
        """The bug this pins: RLS makes a blocked remove look like a successful one.

        Storage returns 200 with an empty list when no DELETE policy matches — no
        exception. Counting the paths we asked about reported every photo cleaned up while
        all of them were still in the bucket, unreferenced by any row and still served at
        their public URL. Nothing about the response distinguishes that from success
        except the list itself, so the list is what gets counted.
        """
        client = fake(
            {"specimen_records": [_batch(photos=[_photo_url("batch-1", "one.jpg"),
                                                 _photo_url("batch-1", "two.jpg")])]},
            objects={"batch-1/one.jpg", "batch-1/two.jpg"},
        )
        client.blocked_storage = True

        summary = dm.delete_specimen_records(["batch-1"])

        assert summary is not None
        assert summary["photos_removed"] == 0, "claimed a photo cleanup that never happened"
        assert summary["photos_orphaned"] == 2
        assert client.objects == {"batch-1/one.jpg", "batch-1/two.jpg"}

    def test_a_partial_remove_reports_only_what_went(self, fake):
        """One object already gone, one refused: the count follows the bucket, not the ask."""
        fake(
            {"specimen_records": [_batch(photos=[_photo_url("batch-1", "one.jpg"),
                                                 _photo_url("batch-1", "two.jpg")])]},
            objects={"batch-1/one.jpg"},
        )

        summary = dm.delete_specimen_records(["batch-1"])

        assert summary is not None
        assert summary["photos_removed"] == 1
        assert summary["photos_orphaned"] == 1

    def test_photos_can_be_kept(self, fake):
        client = fake(
            {"specimen_records": [_batch(photos=[_photo_url("batch-1")])]},
            objects={"batch-1/a.jpg"},
        )

        dm.delete_specimen_records(["batch-1"], remove_photos=False)

        assert client.objects == {"batch-1/a.jpg"}


class TestRefusesToClaimADeletionItDidNotMake:
    def test_a_blocked_delete_returns_none(self, fake):
        """The reported bug: rows survive and the app says the trial run was cleared."""
        client = fake({"specimen_records": [_batch()]})
        client.blocked_deletes.add("specimen_records")

        assert dm.delete_specimen_records(["batch-1"]) is None
        assert client.ids() == ["batch-1"]

    def test_no_client_returns_none(self, monkeypatch):
        monkeypatch.setattr(dm, "get_supabase_client", lambda: None)
        assert dm.delete_specimen_records(["batch-1"]) is None

    @pytest.mark.parametrize("ids", [[], None, ["", "  "]])
    def test_empty_selection_returns_none(self, fake, ids):
        fake({"specimen_records": [_batch()]})
        assert dm.delete_specimen_records(ids) is None

    def test_unknown_ids_return_none(self, fake):
        client = fake({"specimen_records": [_batch()]})
        assert dm.delete_specimen_records(["does-not-exist"]) is None
        assert client.ids() == ["batch-1"]


class TestBulkReset:
    def test_scoped_to_one_collector(self, fake):
        client = fake({"specimen_records": [
            _batch("mine-1", collector="me"),
            _batch("theirs-1", collector="someone-else"),
        ]})

        summary = dm.delete_all_specimen_records(collector_id="me")

        assert summary is not None and summary["deleted"] == 1
        assert client.ids() == ["theirs-1"]

    def test_unscoped_clears_everything(self, fake):
        """Unscoped means everyone's, so it is an admin action."""
        client = fake({"specimen_records": [
            _batch("mine-1", collector="me"),
            _batch("theirs-1", collector="someone-else"),
        ]}, admin=True)

        dm.delete_all_specimen_records()

        assert client.ids() == []

    def test_scoped_reset_still_cascades_children(self, fake):
        """A child inherits its batch's collector_id, but do not rely on that: the batch
        is selected by collector and the cascade must pick the children up regardless."""
        client = fake({"specimen_records": [
            _batch("mine-1", collector="me", vialed={"Anopheles": 1}),
            _child("v1", parent="mine-1", collector="someone-else"),
        ]})

        dm.delete_all_specimen_records(collector_id="me")

        assert client.ids() == []

    def test_empty_ledger_is_not_an_error(self, fake):
        fake({"specimen_records": []}, admin=True)
        summary = dm.delete_all_specimen_records()
        assert summary == {
            "requested": 0, "deleted": 0, "cascaded_children": 0, "photos_removed": 0,
            "photos_orphaned": 0,
            "batches_restored": {}, "tally_failures": [], "not_deleted": [],
            "refused_not_yours": [],
        }


class TestSideTables:
    """These clear a table wholesale — there is no per-investigator form — so they are
    admin-only. The admin=True on each build is that rule, not incidental setup."""

    def test_bioassay_rows_are_deleted(self, fake):
        client = fake({"bioassay_results": [
            {"id": 1, "treatment_name": "Permethrin"},
            {"id": 2, "treatment_name": "DDT"},
        ]}, admin=True)

        assert dm.delete_all_bioassay_results() == 2
        assert client.tables["bioassay_results"] == []

    def test_clinical_rows_are_deleted(self, fake):
        client = fake({"clinical_case_data": [{"id": "a"}, {"id": "b"}, {"id": "c"}]}, admin=True)

        assert dm.delete_all_clinical_case_data() == 3
        assert client.tables["clinical_case_data"] == []

    def test_an_already_empty_table_is_zero_not_a_failure(self, fake):
        fake({"bioassay_results": []}, admin=True)
        assert dm.delete_all_bioassay_results() == 0

    def test_an_unrecognised_key_column_deletes_nothing(self, fake):
        """Both side tables predate their schema file and may have drifted from it, so the
        key column is discovered at runtime. Guessing one would either raise on every
        delete or silently match nothing — so it refuses instead."""
        client = fake({"bioassay_results": [{"assay_date": "2026-07-01", "treatment_name": "x"}]}, admin=True)

        assert dm.delete_all_bioassay_results() is None
        assert len(client.tables["bioassay_results"]) == 1

    def test_a_blocked_delete_returns_none(self, fake):
        client = fake({"clinical_case_data": [{"id": "a"}]}, admin=True)
        client.blocked_deletes.add("clinical_case_data")

        assert dm.delete_all_clinical_case_data() is None
        assert len(client.tables["clinical_case_data"]) == 1


class TestLedgerStaysReadableAfterADelete:
    def test_remaining_rows_still_aggregate(self, fake):
        client = fake({"specimen_records": [
            _batch("batch-1", anopheles=100, vialed={"Anopheles": 1}), _child("v1"),
            _batch("batch-2", anopheles=40),
        ]})

        dm.delete_specimen_records(["batch-1"])

        df = pd.DataFrame(client.tables["specimen_records"])
        assert len(df) == 1
        assert _total_specimens(client) == {"Anopheles": 40}
