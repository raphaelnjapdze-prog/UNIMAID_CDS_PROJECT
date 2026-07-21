"""Tests for the trained-classifier boundary (utils.classifier_inference).

The classifier ships as code only; the .pth weights are trained and placed by
the operator. These lock the two properties that hold regardless of whether
torch/weights are present:

  1. Honest degradation — with no torch or no checkpoints it reports itself
     unavailable and returns no prediction, never a fabricated species.
  2. When the pipeline does produce a raw verdict, the mapping preserves the
     cryptic-complex ceiling: a complex/group result flags
     molecular_id_required and never reads as a bare member species. It also
     flows correctly through PCR-accuracy extraction and genus aggregation.
"""

from utils.classifier_inference import (
    _build_result,
    _expand_taxon,
    classifier_status,
    process_adult_image_classification,
)


class TestHonestDegradation:
    def test_status_unavailable_without_weights(self):
        # No .pth checkpoints ship in the repo (and CI has no torch either), so
        # the classifier must report itself unavailable, with a reason.
        s = classifier_status()
        assert s["available"] is False
        assert isinstance(s["reason"], str) and s["reason"]

    def test_process_returns_error_not_fabrication(self):
        r = process_adult_image_classification(None)
        assert "error" in r
        assert "predicted_species" not in r  # never invents a species


class TestGenusExpansion:
    def test_expands_abbreviated_genera(self):
        assert _expand_taxon("An. gambiae complex") == "Anopheles gambiae complex"
        assert _expand_taxon("Cx. quinquefasciatus") == "Culex quinquefasciatus"
        assert _expand_taxon("Ae. aegypti") == "Aedes aegypti"

    def test_leaves_full_names_untouched(self):
        assert _expand_taxon("Anopheles") == "Anopheles"
        assert _expand_taxon("Culex pipiens complex") == "Culex pipiens complex"


class TestResultMapping:
    def test_complex_flags_pcr_and_expands(self):
        raw = {"genus": "Anopheles", "species": "An. gambiae complex",
               "resolution_level": "complex", "stage1_confidence": 0.9,
               "stage2_confidence": 0.88, "stage1_uncertain": False, "stage2_uncertain": False}
        r = _build_result(raw)
        assert r["predicted_species"] == "Anopheles gambiae complex"
        assert r["resolution_level"] == "complex"
        assert r["molecular_id_required"] is True
        assert r["confidence"] == 0.88  # stage-2 preferred when present

    def test_species_no_pcr(self):
        raw = {"genus": "Aedes", "species": "Ae. aegypti", "resolution_level": "species",
               "stage1_confidence": 0.8, "stage2_confidence": 0.7}
        r = _build_result(raw)
        assert r["predicted_species"] == "Aedes aegypti"
        assert r["molecular_id_required"] is False

    def test_genus_fallback_uses_stage1_confidence(self):
        raw = {"genus": "Culex", "species": "Culex", "resolution_level": "genus",
               "stage1_confidence": 0.6, "stage2_confidence": None}
        r = _build_result(raw)
        assert r["genus"] == "Culex"
        assert r["resolution_level"] == "genus"
        assert r["molecular_id_required"] is False
        assert r["confidence"] == 0.6


class TestAccuracyAndAggregationIntegration:
    def test_result_flows_through_extraction_and_matching(self):
        from utils.pcr_and_accuracy import _extract_predicted_label, _is_correct_match
        r = _build_result({"genus": "Anopheles", "species": "An. gambiae complex",
                           "resolution_level": "complex", "stage1_confidence": 0.9,
                           "stage2_confidence": 0.9})
        fsr = {"screening_method": "trained_classifier", "result": r}
        label = _extract_predicted_label(fsr)
        assert label == "Anopheles gambiae complex"
        assert _is_correct_match(label, "Anopheles coluzzii")
        assert not _is_correct_match(label, "Anopheles funestus")

    def test_genus_extraction_for_aggregation(self):
        from utils.data_manager import extract_genus_counts_from_screening, extract_primary_genus
        r = _build_result({"genus": "Aedes", "species": "Ae. aegypti", "resolution_level": "species",
                           "stage1_confidence": 0.9, "stage2_confidence": 0.9})
        fsr = {"screening_method": "trained_classifier", "result": r}
        assert extract_primary_genus(fsr) == "Aedes"
        assert extract_genus_counts_from_screening(fsr) == {"Aedes": 1}
