"""The ledger grouped into collection events, with vialed individuals nested under their batch.

A flat ledger lists a vialed mosquito as an unrelated new specimen ID, which hides the very
relationship subsampling exists to record. These tests pin the arithmetic the grouped view
puts on screen — in particular that `caught = vialed + in_batch` for every genus, so the
no-double-count invariant is visible and not merely true.
"""
import pandas as pd

from utils.data_manager import build_collection_events


def _batch(specimen_id="batch-1", anopheles=500, culex=20, vialed=None, date="2026-07-13"):
    result = {
        "anopheles_count": anopheles,
        "culex_count": culex,
        "aedes_count": 0,
        "other_genera_count": 5,
        "field_notes": "Roadside puddle",
    }
    if vialed:
        result["vialed_out"] = vialed
    return {
        "specimen_id": specimen_id,
        "parent_specimen_id": None,
        "collection_date": date,
        "breeding_site_type": "Stagnant pool",
        "collector_id": "user-1",
        "pcr_status": "not_submitted",
        "pcr_confirmed_species": None,
        "tube_label": None,
        "field_screening_result": {
            "screening_method": "manual_field_log",
            "result": result,
            "collector_label": "A. Musa",
        },
    }


def _child(specimen_id, parent="batch-1", genus="Anopheles", tube="T-1", identified=None):
    if identified:
        screening = {
            "screening_method": "manual_checklist",
            # The shape attach_identification_to_specimen actually writes.
            "result": {"genus_triage": {"genus": identified}},
            "subsampled_genus": genus,
            "identified_by_label": "A. Musa",
        }
    else:
        screening = {
            "screening_method": "field_subsample",
            "result": {"genus": genus, "pending_identification": True},
        }
    return {
        "specimen_id": specimen_id,
        "parent_specimen_id": parent,
        "collection_date": "2026-07-13",
        "breeding_site_type": "Stagnant pool",
        "collector_id": "user-1",
        "pcr_status": "not_submitted",
        "pcr_confirmed_species": None,
        "tube_label": tube,
        "field_screening_result": screening,
    }


class TestCountsReconcile:
    def test_caught_equals_vialed_plus_in_batch(self):
        df = pd.DataFrame([
            _batch(vialed={"Anopheles": 3}),
            _child("c1"), _child("c2", tube="T-2"), _child("c3", tube="T-3"),
        ])
        events, _ = build_collection_events(df)

        an = events[0]["genus_counts"]["Anopheles"]
        assert an["caught"] == 500          # raw count, never mutated
        assert an["vialed"] == 3
        assert an["in_batch"] == 497
        # The invariant, stated on screen: nothing is counted twice, nothing goes missing.
        assert an["caught"] == an["vialed"] + an["in_batch"]

    def test_untouched_genus_has_nothing_vialed(self):
        df = pd.DataFrame([_batch(vialed={"Anopheles": 3}), _child("c1")])
        events, _ = build_collection_events(df)

        cx = events[0]["genus_counts"]["Culex"]
        assert (cx["caught"], cx["vialed"], cx["in_batch"]) == (20, 0, 20)

    def test_other_genera_cannot_be_vialed_so_all_remain(self):
        df = pd.DataFrame([_batch()])
        events, _ = build_collection_events(df)

        other = events[0]["genus_counts"]["Other"]
        assert (other["caught"], other["vialed"], other["in_batch"]) == (5, 0, 5)


class TestChildrenNestUnderTheirBatch:
    def test_children_are_attached_to_the_right_batch(self):
        df = pd.DataFrame([
            _batch("batch-1", vialed={"Anopheles": 1}),
            _batch("batch-2", date="2026-07-12", vialed={"Anopheles": 2}),
            _child("c1", parent="batch-1"),
            _child("c2", parent="batch-2"),
            _child("c3", parent="batch-2"),
        ])
        events, _ = build_collection_events(df)

        by_id = {e["specimen_id"]: e for e in events}
        assert len(by_id["batch-1"]["children"]) == 1
        assert len(by_id["batch-2"]["children"]) == 2

    def test_child_carries_its_genus_before_identification(self):
        df = pd.DataFrame([_batch(vialed={"Anopheles": 1}), _child("c1")])
        events, _ = build_collection_events(df)

        child = events[0]["children"][0]
        # The genus is known from the pile it came from, even though nobody has
        # identified it yet — that distinction is the whole point of the column.
        assert child["genus"] == "Anopheles"
        assert child["identified_as"] is None
        assert child["tube_label"] == "T-1"

    def test_identified_child_keeps_its_subsampled_genus(self):
        df = pd.DataFrame([
            _batch(vialed={"Anopheles": 1}),
            _child("c1", identified="Anopheles"),
        ])
        events, _ = build_collection_events(df)

        child = events[0]["children"][0]
        assert child["genus"] == "Anopheles"
        assert child["identified_as"] == "Anopheles"

    def test_events_are_newest_first(self):
        df = pd.DataFrame([
            _batch("old", date="2026-07-01"),
            _batch("new", date="2026-07-13"),
        ])
        events, _ = build_collection_events(df)
        assert [e["specimen_id"] for e in events] == ["new", "old"]


class TestNothingIsSilentlyDropped:
    def test_standalone_identification_is_returned_separately(self):
        standalone = {
            "specimen_id": "solo-1",
            "parent_specimen_id": None,
            "collection_date": "2026-07-13",
            "breeding_site_type": None,
            "collector_id": "user-1",
            "pcr_status": "not_submitted",
            "pcr_confirmed_species": None,
            "tube_label": None,
            "field_screening_result": {
                "screening_method": "ai_vision",
                "result": {"genus": "Culex"},
            },
        }
        df = pd.DataFrame([_batch(vialed={"Anopheles": 1}), _child("c1"), standalone])
        events, others = build_collection_events(df)

        # A row that belongs to no batch must still surface somewhere — a record that
        # vanishes from every view is worse than one shown out of context.
        assert len(events) == 1
        assert list(others["specimen_id"]) == ["solo-1"]

    def test_batches_and_children_are_not_in_the_leftovers(self):
        df = pd.DataFrame([_batch(vialed={"Anopheles": 1}), _child("c1")])
        _, others = build_collection_events(df)
        assert others.empty

    def test_empty_ledger(self):
        events, others = build_collection_events(pd.DataFrame())
        assert events == []
        assert others.empty
