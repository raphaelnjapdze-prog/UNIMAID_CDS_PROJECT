"""Unit tests for the Gemini vision guardrail's taxonomy layer.

The cryptic-complex membership the vision path matches against is derived from
the single source of truth (morphology_keys.SPECIES_COMPLEXES), not duplicated.
These tests lock that derivation, and confirm the guardrail still caps a
complex-member guess at complex level while letting genuinely diagnostic single
species (e.g. invasive An. stephensi) resolve. No network / Gemini call is made
— only the deterministic guardrail layer is exercised.
"""

from utils.morphology_keys import SPECIES_COMPLEXES
from utils.vision_inference import (
    _COMPLEX_PRESENTATION,
    _CRYPTIC_COMPLEXES,
    _apply_adult_guardrails,
)


class TestVisionComplexDerivation:
    def test_match_terms_are_derived_from_single_source(self):
        for name, entry in _CRYPTIC_COMPLEXES.items():
            assert entry["match_terms"] == SPECIES_COMPLEXES[name]["members"], name

    def test_all_vision_complexes_are_registered(self):
        for name in _CRYPTIC_COMPLEXES:
            assert name in SPECIES_COMPLEXES, name

    def test_presentation_and_built_table_keys_align(self):
        assert set(_CRYPTIC_COMPLEXES) == set(_COMPLEX_PRESENTATION)

    def test_every_complex_entry_has_presentation_fields(self):
        for entry in _CRYPTIC_COMPLEXES.values():
            assert entry["resolved_name"]
            assert entry["citation"]
            assert entry["molecular_confirmation_recommended"] is True
            assert entry["invasive_species_alert"] is False

    def test_shared_list_extends_vision_reach(self):
        # molestus lives in SPECIES_COMPLEXES pipiens membership; the vision path
        # now recognises it for free because it derives from the shared source.
        assert "molestus" in _CRYPTIC_COMPLEXES["Culex pipiens complex"]["match_terms"]


def _adult(guess: str) -> dict:
    return _apply_adult_guardrails({
        "raw_best_guess": guess,
        "genus_guess": "Anopheles",
        "image_quality_ok": True,
        "key_features_observed": [],
        "raw_caveats": "",
    })


class TestVisionGuardrailBehaviour:
    def test_complex_member_guess_capped_at_complex(self):
        result = _adult("I think this is Anopheles arabiensis")
        assert result["best_match"] == "Anopheles gambiae complex (s.l.)"
        assert result["confidence_tier"] == "Group-level match"
        assert result["molecular_confirmation_recommended"] is True

    def test_funestus_member_capped_at_group(self):
        result = _adult("possibly Anopheles rivulorum")
        assert result["best_match"] == "Anopheles funestus group"
        assert result["molecular_confirmation_recommended"] is True

    def test_diagnostic_species_wins_over_complex(self):
        result = _adult("Anopheles stephensi")
        assert result["best_match"] == "Anopheles stephensi (Invasive Strain)"
        assert result["invasive_species_alert"] is True

    def test_unknown_guess_stays_at_genus(self):
        result = _adult("some Anopheles I can't place")
        assert result["confidence_tier"] == "Genus-level only"
        assert result["molecular_confirmation_recommended"] is True

    def test_poor_image_quality_short_circuits(self):
        result = _apply_adult_guardrails({"image_quality_ok": False, "raw_caveats": "blurry"})
        assert result["confidence_tier"] == "Insufficient image quality"
