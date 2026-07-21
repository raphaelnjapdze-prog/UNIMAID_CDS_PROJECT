"""Unit tests for the pure data-layer logic in utils.data_manager.

These cover the deterministic functions that surveillance/reporting depend on:
genus resolution from stored screening results and the WHO bioassay math.
"""

import pandas as pd
import pytest

from utils.data_manager import (
    _genus_from_label,
    classify_resistance_status,
    compute_mortality_percentage,
    extract_genus_counts_from_screening,
    extract_primary_genus,
    pcr_specimen_label,
)


class TestExtractPrimaryGenus:
    def test_ai_vision_genus(self):
        r = {"screening_method": "ai_vision", "result": {"genus": "Anopheles"}}
        assert extract_primary_genus(r) == "Anopheles"

    def test_manual_checklist_triage(self):
        r = {"screening_method": "manual_checklist", "result": {"genus_triage": {"genus": "Culex"}}}
        assert extract_primary_genus(r) == "Culex"

    def test_manual_checklist_resolved_genus_fallback(self):
        r = {"screening_method": "manual_checklist", "result": {"resolved_genus": "Aedes"}}
        assert extract_primary_genus(r) == "Aedes"

    def test_trained_classifier(self):
        r = {"screening_method": "trained_classifier", "result": {"genus": "Aedes"}}
        assert extract_primary_genus(r) == "Aedes"

    def test_field_log_returns_none(self):
        # Raw multi-genus counts are aggregated via extract_genus_counts, not here.
        r = {"screening_method": "manual_field_log", "result": {"anopheles_count": 3}}
        assert extract_primary_genus(r) is None

    def test_json_string_input(self):
        assert extract_primary_genus('{"screening_method": "ai_vision", "result": {"genus": "Culex"}}') == "Culex"

    def test_bad_json_returns_none(self):
        assert extract_primary_genus("{not valid json") is None

    def test_empty_inputs_return_none(self):
        assert extract_primary_genus(None) is None
        assert extract_primary_genus({}) is None


class TestExtractGenusCounts:
    def test_field_log_counts_drops_zeroes(self):
        r = {
            "screening_method": "manual_field_log",
            "result": {"anopheles_count": 2, "culex_count": 1, "aedes_count": 0},
        }
        assert extract_genus_counts_from_screening(r) == {"Anopheles": 2, "Culex": 1}

    def test_field_log_other_genera(self):
        r = {"screening_method": "manual_field_log", "result": {"other_genera_count": 4}}
        assert extract_genus_counts_from_screening(r) == {"Other": 4}

    def test_single_specimen_contributes_one(self):
        r = {"screening_method": "ai_vision", "result": {"genus": "Aedes"}}
        assert extract_genus_counts_from_screening(r) == {"Aedes": 1}

    def test_undetermined_returns_empty(self):
        assert extract_genus_counts_from_screening({"screening_method": "ai_vision", "result": {}}) == {}

    def test_empty_input_returns_empty(self):
        assert extract_genus_counts_from_screening(None) == {}


class TestGenusFromLabel:
    def test_matches_known_genus_substring(self):
        assert _genus_from_label("Anopheles gambiae complex") == "Anopheles"
        assert _genus_from_label("Culex quinquefasciatus") == "Culex"
        assert _genus_from_label("aedes aegypti") == "Aedes"

    def test_none_and_unmatched(self):
        assert _genus_from_label(None) is None
        assert _genus_from_label("Mansonia africana") is None


class TestBioassayMortality:
    @pytest.mark.parametrize(
        "dead,exposed,expected",
        [(0, 100, 0.0), (50, 100, 50.0), (100, 100, 100.0), (49, 98, 50.0)],
    )
    def test_percentage(self, dead, exposed, expected):
        assert compute_mortality_percentage(dead, exposed) == expected

    def test_zero_exposed_is_none(self):
        assert compute_mortality_percentage(0, 0) is None


class TestResistanceClassification:
    @pytest.mark.parametrize(
        "pct,expected",
        [
            (100.0, "Susceptible"),
            (98.0, "Susceptible"),
            (97.9, "Possible resistance (confirm with additional testing)"),
            (90.0, "Possible resistance (confirm with additional testing)"),
            (89.9, "Resistant"),
            (0.0, "Resistant"),
        ],
    )
    def test_who_thresholds(self, pct, expected):
        assert classify_resistance_status(pct) == expected

    def test_none_is_unknown(self):
        assert classify_resistance_status(None) == "Unknown"


class TestPcrSpecimenLabel:
    """The PCR picker builds each option label from a DataFrame record. A missing
    tube_label comes back as float NaN (truthy), which used to crash the join
    with 'expected str instance, float found' — every identified-but-not-vialed
    specimen hit this."""

    def _row(self, **over):
        base = {
            "field_screening_result": {
                "screening_method": "trained_classifier",
                "result": {"genus": "Anopheles", "predicted_species": "Anopheles gambiae complex",
                           "resolution_level": "complex"},
            },
            "specimen_id": "abcd1234-5678-90ab",
            "collection_date": "2026-07-20",
            "tube_label": "VS-01",
            "pcr_status": "not_submitted",
        }
        base.update(over)
        return base

    def test_includes_tube_genus_and_id(self):
        label = pcr_specimen_label(self._row())
        assert "VS-01" in label
        assert "Anopheles" in label
        assert "abcd1234" in label

    def test_missing_tube_label_nan_does_not_crash(self):
        label = pcr_specimen_label(self._row(tube_label=float("nan")))
        assert isinstance(label, str)
        assert "nan" not in label.lower()   # the NaN is dropped, not rendered
        assert "Anopheles" in label

    def test_dataframe_roundtrip_with_missing_tube(self):
        # Faithful reproduction: records with differing keys -> the row lacking
        # tube_label gets float NaN after DataFrame.to_dict("records").
        df = pd.DataFrame([
            {"specimen_id": "has-tube-000", "tube_label": "VS-9", "collection_date": "2026-07-20",
             "pcr_status": "not_submitted",
             "field_screening_result": {"screening_method": "ai_vision",
                                        "result": {"genus": "Culex", "best_match": "Culex pipiens complex"}}},
            {"specimen_id": "no-tube-00000", "collection_date": "2026-07-20",
             "pcr_status": "not_submitted",
             "field_screening_result": {"screening_method": "ai_vision",
                                        "result": {"genus": "Culex", "best_match": "Culex pipiens complex"}}},
        ])
        row = df.to_dict("records")[1]
        label = pcr_specimen_label(row)  # must not raise
        assert isinstance(label, str)
        assert "Culex" in label
        assert "nan" not in label.lower()

    def test_confirmed_gets_check_prefix(self):
        assert pcr_specimen_label(self._row(pcr_status="confirmed")).startswith("✔")

    def test_nan_date_falls_back_to_undated(self):
        label = pcr_specimen_label(self._row(collection_date=float("nan"), tube_label=None))
        assert "undated" in label
