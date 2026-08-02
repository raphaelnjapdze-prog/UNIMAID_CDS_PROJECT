"""Unit tests for the deterministic specimen-subsampling logic in utils.data_manager.

These cover the pure count math and row shaping behind "vialing out" individual
specimens from a batch field-count log — the parts that keep genus totals honest
(no double-counting) without needing a live Supabase backend.
"""

import json

import pandas as pd

from utils.data_manager import (
    _apply_vialed_out,
    _available_to_vial,
    _build_subsample_children,
    batch_catch_summary,
    extract_genus_counts_from_screening,
    extract_primary_genus,
    is_pending_identification,
    specimens_pending_identification,
)


class TestAvailableToVial:
    def test_raw_count_when_none_vialed(self):
        assert _available_to_vial({"anopheles_count": 500}, "Anopheles") == 500

    def test_subtracts_already_vialed(self):
        result = {"anopheles_count": 500, "vialed_out": {"Anopheles": 30}}
        assert _available_to_vial(result, "Anopheles") == 470

    def test_floors_at_zero_never_negative(self):
        result = {"culex_count": 5, "vialed_out": {"Culex": 9}}
        assert _available_to_vial(result, "Culex") == 0

    def test_untracked_genus_is_zero(self):
        # Only Anopheles/Culex/Aedes are subsamplable; "Other" is not.
        assert _available_to_vial({"other_genera_count": 10}, "Other") == 0

    def test_missing_count_is_zero(self):
        assert _available_to_vial({}, "Aedes") == 0


class TestApplyVialedOut:
    def test_records_new_tally(self):
        updated = _apply_vialed_out({"anopheles_count": 500}, "Anopheles", 30)
        assert updated["vialed_out"] == {"Anopheles": 30}

    def test_accumulates_across_calls(self):
        once = _apply_vialed_out({"anopheles_count": 500}, "Anopheles", 30)
        twice = _apply_vialed_out(once, "Anopheles", 20)
        assert twice["vialed_out"] == {"Anopheles": 50}

    def test_preserves_raw_counts(self):
        updated = _apply_vialed_out({"anopheles_count": 500, "culex_count": 12}, "Anopheles", 30)
        assert updated["anopheles_count"] == 500
        assert updated["culex_count"] == 12

    def test_does_not_mutate_input(self):
        original = {"anopheles_count": 500}
        _apply_vialed_out(original, "Anopheles", 30)
        assert "vialed_out" not in original


class TestBuildSubsampleChildren:
    def _batch(self):
        return {
            "specimen_id": "batch-uuid",
            "collection_date": "2026-07-12",
            "collector_id": "collector-1",
            "gps_lat": 11.8,
            "gps_lon": 13.1,
            "breeding_site_type": "pond",
        }

    def test_count_matches(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 3, "T", "2026-07-12T00:00:00Z")
        assert len(kids) == 3

    def test_links_to_parent_and_role(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 2, None, "2026-07-12T00:00:00Z")
        for k in kids:
            assert k["parent_specimen_id"] == "batch-uuid"
            assert k["specimen_role"] == "individual"

    def test_unique_specimen_ids(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 5, None, "2026-07-12T00:00:00Z")
        ids = [k["specimen_id"] for k in kids]
        assert len(set(ids)) == 5

    def test_carries_known_genus_pending_identification(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 1, None, "2026-07-12T00:00:00Z")
        fsr = kids[0]["field_screening_result"]
        assert fsr["screening_method"] == "field_subsample"
        assert fsr["result"]["genus"] == "Anopheles"
        assert fsr["result"]["resolution_level"] == "genus"
        assert fsr["result"]["pending_identification"] is True

    def test_inherits_collection_metadata(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 1, None, "2026-07-12T00:00:00Z")
        k = kids[0]
        assert k["collection_date"] == "2026-07-12"
        assert k["collector_id"] == "collector-1"
        assert k["gps_lat"] == 11.8
        assert k["breeding_site_type"] == "pond"

    def test_inherits_the_collector_label(self):
        """The child is the same person's work as its batch. Without the label carried over
        it falls back to a bare id, so one collector reads as a name on the batch row and a
        UUID on every specimen vialed out of it."""
        batch = self._batch()
        batch["field_screening_result"] = {
            "screening_method": "manual_field_log",
            "collector_label": "A. Musa",
            "result": {"anopheles_count": 500},
        }

        kids = _build_subsample_children(batch, "Anopheles", 2, None, "2026-07-12T00:00:00Z")

        assert all(k["field_screening_result"]["collector_label"] == "A. Musa" for k in kids)

    def test_no_collector_label_on_the_batch_is_not_invented(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 1, None, "2026-07-12T00:00:00Z")
        assert kids[0]["field_screening_result"]["collector_label"] is None

    def test_tube_labels_numbered_when_prefix_given(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 2, "LAB-001", "2026-07-12T00:00:00Z")
        assert kids[0]["tube_label"] == "LAB-001-001"
        assert kids[1]["tube_label"] == "LAB-001-002"

    def test_no_tube_label_without_prefix(self):
        kids = _build_subsample_children(self._batch(), "Anopheles", 1, None, "2026-07-12T00:00:00Z")
        assert kids[0]["tube_label"] is None


class TestBatchCatchSummary:
    """The batch's original catch — what extract_genus_counts_from_screening deliberately
    does not report, because totals need the netted figure and descriptions need this one."""

    def _log(self, vialed=None, **counts):
        result = {f"{g}_count": n for g, n in counts.items()}
        if vialed:
            result["vialed_out"] = vialed
        return {"screening_method": "manual_field_log", "result": result}

    def test_reports_the_raw_catch_not_the_remainder(self):
        summary = batch_catch_summary(self._log(anopheles=100, culex=70,
                                                vialed={"Anopheles": 100, "Culex": 70}))
        assert summary["collected"] == 170
        assert summary["vialed_out"] == 170
        assert summary["remaining"] == 0

    def test_breaks_the_raw_catch_down_by_genus(self):
        summary = batch_catch_summary(self._log(anopheles=100, culex=70,
                                                vialed={"Anopheles": 100, "Culex": 70}))
        assert summary["by_genus"] == {"Anopheles": 100, "Culex": 70, "Aedes": 0, "Other": 0}

    def test_counts_other_genera_in_the_catch(self):
        # "Other" is caught but cannot be vialed out, so it belongs in the total only.
        assert batch_catch_summary(self._log(anopheles=5, other_genera=3))["collected"] == 8

    def test_remaining_never_goes_negative(self):
        summary = batch_catch_summary(self._log(anopheles=5, vialed={"Anopheles": 9}))
        assert summary["remaining"] == 0

    def test_an_identification_row_has_no_catch(self):
        assert batch_catch_summary({"screening_method": "field_subsample",
                                    "result": {"genus": "Anopheles"}}) is None

    def test_decodes_a_json_string(self):
        raw = json.dumps(self._log(anopheles=12))
        assert batch_catch_summary(raw)["collected"] == 12


class TestGenusCountsWithSubsampling:
    def test_field_log_nets_out_vialed_specimens(self):
        # 500 caught, 30 vialed out -> aggregate should report the remaining 470,
        # because those 30 are now counted as individual child rows.
        r = {
            "screening_method": "manual_field_log",
            "result": {"anopheles_count": 500, "vialed_out": {"Anopheles": 30}},
        }
        assert extract_genus_counts_from_screening(r) == {"Anopheles": 470}

    def test_fully_vialed_genus_drops_out(self):
        r = {
            "screening_method": "manual_field_log",
            "result": {"anopheles_count": 5, "vialed_out": {"Anopheles": 5}, "culex_count": 2},
        }
        assert extract_genus_counts_from_screening(r) == {"Culex": 2}

    def test_child_specimen_contributes_one(self):
        r = {
            "screening_method": "field_subsample",
            "result": {"genus": "Anopheles", "resolution_level": "genus", "pending_identification": True},
        }
        assert extract_genus_counts_from_screening(r) == {"Anopheles": 1}

    def test_identified_child_still_counts_when_genus_undetermined(self):
        # The batch was already decremented for this specimen, so if its identification
        # comes back undetermined it must fall back to the genus of the pile it was
        # vialed out of — otherwise a real, caught mosquito vanishes from the totals.
        r = {
            "screening_method": "manual_checklist",
            "result": {"genus_triage": {"genus": "Undetermined"}},
            "subsampled_genus": "Anopheles",
        }
        assert extract_genus_counts_from_screening(r) == {"Anopheles": 1}

    def test_identification_overrides_subsampled_genus(self):
        # A confident ID that contradicts the field pile is a correction, not a fallback:
        # the identified genus wins.
        r = {
            "screening_method": "ai_vision",
            "result": {"genus": "Culex"},
            "subsampled_genus": "Anopheles",
        }
        assert extract_genus_counts_from_screening(r) == {"Culex": 1}

    def test_conservation_holds_after_identification(self):
        # 500 caught, 1 vialed out and then identified as undetermined: still 500.
        batch = {
            "screening_method": "manual_field_log",
            "result": {"anopheles_count": 500, "vialed_out": {"Anopheles": 1}},
        }
        identified_child = {
            "screening_method": "manual_checklist",
            "result": {"genus_triage": {"genus": "Undetermined"}},
            "subsampled_genus": "Anopheles",
        }
        total = extract_genus_counts_from_screening(batch)["Anopheles"]
        total += extract_genus_counts_from_screening(identified_child)["Anopheles"]
        assert total == 500

    def test_batch_plus_children_conserve_total(self):
        # 470 aggregate + 30 children of 1 each == 500 originally caught.
        batch = {
            "screening_method": "manual_field_log",
            "result": {"anopheles_count": 500, "vialed_out": {"Anopheles": 30}},
        }
        child = {"screening_method": "field_subsample", "result": {"genus": "Anopheles"}}
        total = extract_genus_counts_from_screening(batch)["Anopheles"]
        total += sum(extract_genus_counts_from_screening(child)["Anopheles"] for _ in range(30))
        assert total == 500


class TestPrimaryGenusSubsample:
    def test_field_subsample_reports_known_genus(self):
        r = {"screening_method": "field_subsample", "result": {"genus": "Culex"}}
        assert extract_primary_genus(r) == "Culex"


def _pending_row(specimen_id="s1", genus="Anopheles"):
    return {
        "specimen_id": specimen_id,
        "field_screening_result": {
            "screening_method": "field_subsample",
            "result": {"genus": genus, "pending_identification": True},
        },
    }


class TestIsPendingIdentification:
    def test_vialed_specimen_awaiting_id_is_pending(self):
        assert is_pending_identification(_pending_row()) is True

    def test_identified_specimen_is_not_pending(self):
        # Once identified, field_screening_result is replaced by the ID method.
        row = {
            "specimen_id": "s1",
            "field_screening_result": {
                "screening_method": "manual_checklist",
                "result": {"genus_triage": {"genus": "Anopheles"}},
            },
        }
        assert is_pending_identification(row) is False

    def test_batch_field_log_is_not_pending(self):
        # A batch is never an individual awaiting identification — it must not show up
        # as a scannable tube, because identifying it would clobber its raw counts.
        row = {
            "specimen_id": "b1",
            "field_screening_result": {
                "screening_method": "manual_field_log",
                "result": {"anopheles_count": 500},
            },
        }
        assert is_pending_identification(row) is False

    def test_subsample_with_flag_cleared_is_not_pending(self):
        row = _pending_row()
        row["field_screening_result"]["result"]["pending_identification"] = False
        assert is_pending_identification(row) is False


class TestSpecimensPendingIdentification:
    def test_selects_only_pending_individuals(self):
        df = pd.DataFrame([
            _pending_row("s1"),
            _pending_row("s2", genus="Culex"),
            {
                "specimen_id": "b1",
                "field_screening_result": {
                    "screening_method": "manual_field_log",
                    "result": {"anopheles_count": 500},
                },
            },
        ])
        pending = specimens_pending_identification(df)
        assert sorted(pending["specimen_id"]) == ["s1", "s2"]

    def test_empty_frame_returns_empty(self):
        assert specimens_pending_identification(pd.DataFrame()).empty

    def test_frame_without_screening_column_returns_empty(self):
        df = pd.DataFrame([{"specimen_id": "s1"}])
        assert specimens_pending_identification(df).empty


class TestVialOutRefusesASilentlyBlockedTally:
    """RLS makes an unpermitted UPDATE a no-op, not an error: it matches zero rows and
    raises nothing. vial_out_specimens trusted the call, so the children were created,
    the batch kept its full raw counts, and the same mosquitoes were counted twice —
    reported to the user as a success. The batch tally must be verified, not assumed."""

    def _client(self, tally_rows):
        """Fake Supabase where the batch tally UPDATE returns `tally_rows`."""
        state = {"deleted": [], "inserted": []}

        class Resp:
            def __init__(self, data):
                self.data = data

        batch = self._batch()

        class Table:
            def __init__(self):
                self.op = None
                self.payload = None

            def select(self, *_a, **_k):
                self.op = "select"
                return self

            def insert(self, rows):
                self.op = "insert"
                self.payload = rows
                return self

            def update(self, _payload):
                self.op = "update"
                return self

            def delete(self):
                self.op = "delete"
                return self

            def eq(self, *_a, **_k):
                return self

            def in_(self, _col, ids):
                self.payload = ids
                return self

            def execute(self):
                if self.op == "select":
                    return Resp([batch])
                if self.op == "insert":
                    state["inserted"] = self.payload
                    return Resp(self.payload)
                if self.op == "update":
                    return Resp(tally_rows)          # [] == silently blocked by RLS
                if self.op == "delete":
                    state["deleted"] = self.payload
                    return Resp([])
                return Resp([])

        class Client:
            def table(self, _name): return Table()

        return Client(), state

    def _batch(self):
        return {
            "specimen_id": "batch-1",
            "collection_date": "2026-07-13",
            "collector_id": "user-1",
            "breeding_site_type": "Puddle",
            "gps_lat": None, "gps_lon": None,
            "field_screening_result": {
                "screening_method": "manual_field_log",
                "result": {"anopheles_count": 500},
            },
        }

    def test_blocked_tally_update_rolls_back_and_reports_failure(self, monkeypatch):
        import utils.data_manager as dm

        client, state = self._client(tally_rows=[])   # RLS silently blocks the UPDATE
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm.st, "error", lambda *_a, **_k: None)
        monkeypatch.setattr(dm, "clear_specimen_records_cache", lambda: None)

        result = dm.vial_out_specimens("batch-1", "Anopheles", 3)

        # No success is reported for a batch whose tally never moved, and the children
        # created a moment earlier are deleted — otherwise they double-count.
        assert result is None
        assert len(state["deleted"]) == 3

    def test_successful_tally_update_keeps_the_children(self, monkeypatch):
        import utils.data_manager as dm

        client, state = self._client(tally_rows=[{"specimen_id": "batch-1"}])
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm.st, "error", lambda *_a, **_k: None)
        monkeypatch.setattr(dm, "clear_specimen_records_cache", lambda: None)

        result = dm.vial_out_specimens("batch-1", "Anopheles", 3)

        assert result is not None and len(result) == 3
        assert state["deleted"] == []
