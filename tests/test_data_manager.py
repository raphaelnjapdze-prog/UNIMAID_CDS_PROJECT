"""Unit tests for the pure data-layer logic in utils.data_manager.

These cover the deterministic functions that surveillance/reporting depend on:
genus resolution from stored screening results and the WHO bioassay math.
"""

import pytest

from utils.data_manager import (
    _genus_from_label,
    classify_resistance_status,
    compute_mortality_percentage,
    extract_genus_counts_from_screening,
    extract_primary_genus,
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
