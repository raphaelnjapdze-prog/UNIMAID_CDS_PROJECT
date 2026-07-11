"""Unit tests for PCR accuracy scoring in utils.pcr_and_accuracy.

Covers the two functions that decide whether a field prediction counts as
correct against PCR ground truth:

  * _extract_predicted_label — normalises each screening method's differently
    shaped result into one predicted label, including the Anopheles deep-key
    engine's rich taxon (so accuracy credits complex/species precision, not
    just genus).
  * _is_correct_match — rank-aware matching: complex/group predictions are
    credited against any member, genus-only predictions against any species of
    that genus, but species-level predictions must actually match the species
    (no free genus-level credit).
"""

from utils.morphology_keys import (
    ANOPHELES_KEY_PROFILES,
    SPECIES_COMPLEXES,
    complex_membership_by_trigger,
    identify_anopheles_species,
)
from utils.pcr_and_accuracy import COMPLEX_MEMBERSHIP, _extract_predicted_label, _is_correct_match


def _states(name: str) -> dict:
    return dict(ANOPHELES_KEY_PROFILES[name]["character_states"])


class TestIsCorrectMatchComplex:
    def test_gambiae_complex_credits_any_member(self):
        assert _is_correct_match("An. gambiae complex", "Anopheles coluzzii")
        assert _is_correct_match("An. gambiae complex", "Anopheles arabiensis")
        assert _is_correct_match("An. gambiae complex", "Anopheles gambiae")

    def test_gambiae_complex_wrong_against_other_taxa(self):
        assert not _is_correct_match("An. gambiae complex", "Anopheles funestus")
        assert not _is_correct_match("An. gambiae complex", "Anopheles pharoensis")

    def test_funestus_group_credits_any_member(self):
        assert _is_correct_match("An. funestus group", "Anopheles rivulorum")
        assert _is_correct_match("An. funestus group", "Anopheles leesoni")

    def test_coustani_group_credits_ziemanni(self):
        assert _is_correct_match("An. coustani group", "Anopheles ziemanni")

    def test_marshallii_group_credits_demeilloni(self):
        assert _is_correct_match("An. marshallii group", "Anopheles demeilloni")


class TestIsCorrectMatchGenus:
    def test_bare_genus_credits_any_species(self):
        assert _is_correct_match("Anopheles", "Anopheles coustani")
        assert _is_correct_match("Anopheles spp.", "Anopheles pharoensis")

    def test_bare_genus_wrong_across_genera(self):
        assert not _is_correct_match("Anopheles", "Culex quinquefasciatus")

    def test_culex_genus_level(self):
        assert _is_correct_match("Culex", "Culex pipiens")


class TestIsCorrectMatchSpecies:
    def test_species_matches_itself(self):
        assert _is_correct_match("Anopheles pharoensis", "Anopheles pharoensis")

    def test_species_not_credited_against_different_species(self):
        # The core regression: a species-level prediction must NOT get free
        # genus-level credit against a different Anopheles species.
        assert not _is_correct_match("Anopheles pharoensis", "Anopheles coustani")
        assert not _is_correct_match("Anopheles squamosus", "Anopheles pharoensis")

    def test_species_matches_when_lab_omits_genus(self):
        assert _is_correct_match("Anopheles pharoensis", "pharoensis")


class TestIsCorrectMatchEdges:
    def test_empty_inputs_are_not_matches(self):
        assert not _is_correct_match("", "Anopheles gambiae")
        assert not _is_correct_match("Anopheles gambiae", "")
        assert not _is_correct_match(None, None)


class TestExtractPredictedLabel:
    def test_deep_key_character_scoring_taxon(self):
        fsr = {
            "screening_method": "manual_checklist",
            "result": {
                "genus_triage": {"genus": "Anopheles"},
                "anopheles_deep_key": {"taxon": "An. gambiae complex", "resolution_level": "complex"},
            },
        }
        assert _extract_predicted_label(fsr) == "An. gambiae complex"

    def test_deep_key_couplet_taxon(self):
        fsr = {
            "screening_method": "manual_checklist",
            "result": {
                "genus_triage": {"genus": "Anopheles"},
                "anopheles_couplet_key": {"taxon": "Anopheles pharoensis", "resolution_level": "species"},
            },
        }
        assert _extract_predicted_label(fsr) == "Anopheles pharoensis"

    def test_checklist_species_candidate_group(self):
        fsr = {
            "screening_method": "manual_checklist",
            "result": {"species_candidates": [{"group_complex": "An. funestus group", "species_name": "Anopheles funestus (s.s.)"}]},
        }
        assert _extract_predicted_label(fsr) == "An. funestus group"

    def test_checklist_genus_triage_fallback(self):
        fsr = {"screening_method": "manual_checklist", "result": {"genus_triage": {"genus": "Culex"}}}
        assert _extract_predicted_label(fsr) == "Culex"

    def test_ai_vision_best_match(self):
        fsr = {"screening_method": "ai_vision", "result": {"best_match": "An. gambiae complex", "genus": "Anopheles"}}
        assert _extract_predicted_label(fsr) == "An. gambiae complex"

    def test_empty_returns_none(self):
        assert _extract_predicted_label({}) is None
        assert _extract_predicted_label(None) is None


class TestComplexMembershipSingleSource:
    """The complex-membership data has one owner (morphology_keys.SPECIES_COMPLEXES);
    PCR scoring derives from it and must never carry a divergent copy."""

    def test_pcr_map_is_derived_not_hardcoded(self):
        assert COMPLEX_MEMBERSHIP == complex_membership_by_trigger()

    def test_every_profiled_complex_is_registered(self):
        for name, prof in ANOPHELES_KEY_PROFILES.items():
            complex_name = prof.get("complex")
            if complex_name and not complex_name.startswith("None"):
                assert complex_name in SPECIES_COMPLEXES, f"{name}: {complex_name} unregistered"

    def test_trigger_word_appears_in_its_complex_label(self):
        for label, data in SPECIES_COMPLEXES.items():
            assert data["trigger"] in label.lower(), label

    def test_members_are_lowercase_and_nonempty(self):
        for label, data in SPECIES_COMPLEXES.items():
            assert data["members"], f"{label} has no members"
            assert all(m == m.lower() for m in data["members"]), label
            # A complex's members should include its own trigger species.
            assert data["trigger"] in data["members"], label


class TestDeepKeyToAccuracyEndToEnd:
    """The improvement: a deep-key verdict flows through extraction + matching
    with its real resolution, not collapsed to genus."""

    def test_distinguishable_species_scored_strictly(self):
        res = identify_anopheles_species(_states("Anopheles pharoensis"))
        fsr = {
            "screening_method": "manual_checklist",
            "result": {"genus_triage": {"genus": "Anopheles"}, "anopheles_deep_key": res},
        }
        label = _extract_predicted_label(fsr)
        assert label == "Anopheles pharoensis"
        assert _is_correct_match(label, "Anopheles pharoensis")
        # Would have been wrongly credited as correct under the old genus-level rule.
        assert not _is_correct_match(label, "Anopheles coustani")

    def test_cryptic_complex_still_credited_against_members(self):
        res = identify_anopheles_species(_states("Anopheles gambiae (s.s.)"))
        fsr = {
            "screening_method": "manual_checklist",
            "result": {"genus_triage": {"genus": "Anopheles"}, "anopheles_deep_key": res},
        }
        label = _extract_predicted_label(fsr)
        assert label == "An. gambiae complex"
        assert _is_correct_match(label, "Anopheles arabiensis")
        assert _is_correct_match(label, "Anopheles coluzzii")
        assert not _is_correct_match(label, "Anopheles funestus")
