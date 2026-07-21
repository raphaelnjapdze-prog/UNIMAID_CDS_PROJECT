"""Unit tests for the extended morphology engines in utils.morphology_keys:
the genus-agnostic character scorer wired up for adult *Culex* and *Aedes*, and
the 4th-instar larval deep key.

The property under test is the same taxonomy guardrail the Anopheles engine
enforces (mirrored in models/ and utils/vision_inference.py): cryptic
complexes/groups — Culex pipiens complex, Vishnui subgroup, Cx. decens group,
Ae. simpsoni complex, Ae. furcifer-taylori group, Ae. caballus-juppi pair — are
morphologically inseparable, so the scorer must collapse any such hit to the
complex/group name with molecular_id_required=True and never emit a bare member
species. Genuinely diagnostic species (aegypti, albopictus, tigripes) still
resolve. The larval key never claims species.
"""

import pytest

from utils.morphology_keys import (
    AEDES_KEY_PROFILES,
    CULEX_KEY_PROFILES,
    SPECIES_CATALOG,
    SPECIES_COMPLEXES,
    complex_membership_by_trigger,
    evaluate_larval_deepkey,
    get_aedes_character_schema,
    get_culex_character_schema,
    get_larval_character_schema,
    identify_aedes_species,
    identify_culex_species,
)

# Names that live inside a cryptic complex/group — must NEVER be a resolved
# taxon; they can only surface collapsed to their complex/group.
_CULEX_CRYPTIC = {n for n, p in CULEX_KEY_PROFILES.items()
                  if p.get("resolution_level") in ("complex", "group")}
_AEDES_CRYPTIC = {n for n, p in AEDES_KEY_PROFILES.items()
                  if p.get("resolution_level") in ("complex", "group")}


def _culex_states(name: str) -> dict:
    return dict(CULEX_KEY_PROFILES[name]["character_states"])


def _aedes_states(name: str) -> dict:
    return dict(AEDES_KEY_PROFILES[name]["character_states"])


class TestCulexEngine:
    def test_pipiens_collapses_to_complex(self):
        res = identify_culex_species(_culex_states("Culex quinquefasciatus"))
        assert res["resolution_level"] == "complex"
        assert res["taxon"] == "Culex pipiens complex"
        assert res["molecular_id_required"] is True
        assert res["taxon"] not in _CULEX_CRYPTIC
        assert "PCR" in res["next_step"]

    def test_tritaeniorhynchus_collapses_to_vishnui(self):
        res = identify_culex_species(_culex_states("Culex tritaeniorhynchus"))
        assert res["resolution_level"] == "group"
        assert res["taxon"] == "Vishnui Subgroup"
        assert res["molecular_id_required"] is True

    def test_decens_group_collapses(self):
        res = identify_culex_species(_culex_states("Culex guiarti"))
        assert res["resolution_level"] == "group"
        assert res["taxon"] == "Cx. decens group"
        assert res["molecular_id_required"] is True

    def test_tigripes_resolves_to_species_biocontrol(self):
        res = identify_culex_species(_culex_states("Culex tigripes"))
        assert res["resolution_level"] == "species"
        assert res["taxon"] == "Culex tigripes"
        assert res["molecular_id_required"] is False
        assert res["biocontrol_indicator"] is True

    def test_empty_input_is_undetermined(self):
        res = identify_culex_species({})
        assert res["resolution_level"] == "undetermined"
        assert res["confidence"] == 0

    def test_single_character_stays_at_genus(self):
        res = identify_culex_species({"body_size": "medium"})
        assert res["resolution_level"] == "genus"
        assert res["taxon"] == "Culex spp."

    @pytest.mark.parametrize("name", sorted(CULEX_KEY_PROFILES))
    def test_guardrail_never_emits_bare_cryptic_member(self, name):
        res = identify_culex_species(_culex_states(name))
        assert res["taxon"] not in _CULEX_CRYPTIC
        if res["resolution_level"] in ("complex", "group"):
            assert res["molecular_id_required"] is True
            assert "PCR" in res["next_step"]


class TestAedesEngine:
    def test_aegypti_resolves_to_species(self):
        res = identify_aedes_species(_aedes_states("Aedes aegypti"))
        assert res["resolution_level"] == "species"
        assert res["taxon"] == "Aedes aegypti"
        assert res["molecular_id_required"] is False

    def test_albopictus_flags_biosecurity(self):
        res = identify_aedes_species(_aedes_states("Aedes albopictus"))
        assert res["resolution_level"] == "species"
        assert res["biosecurity_alert"] is True

    def test_simpsoni_collapses_to_complex(self):
        res = identify_aedes_species(_aedes_states("Aedes bromeliae"))
        assert res["resolution_level"] == "complex"
        assert res["taxon"] == "Aedes simpsoni complex"
        assert res["molecular_id_required"] is True
        assert res["taxon"] not in _AEDES_CRYPTIC

    def test_furcifer_collapses_to_group(self):
        res = identify_aedes_species(_aedes_states("Aedes furcifer"))
        assert res["resolution_level"] == "group"
        assert res["taxon"] == "Ae. furcifer-taylori group"
        assert res["molecular_id_required"] is True

    def test_caballus_collapses_to_pair(self):
        res = identify_aedes_species(_aedes_states("Aedes caballus"))
        assert res["resolution_level"] == "group"
        assert res["taxon"] == "Ae. caballus-juppi pair"
        assert res["molecular_id_required"] is True

    @pytest.mark.parametrize("name", sorted(AEDES_KEY_PROFILES))
    def test_guardrail_never_emits_bare_cryptic_member(self, name):
        res = identify_aedes_species(_aedes_states(name))
        assert res["taxon"] not in _AEDES_CRYPTIC
        if res["resolution_level"] in ("complex", "group"):
            assert res["molecular_id_required"] is True
            assert "PCR" in res["next_step"]


class TestLarvalDeepKey:
    def test_palmate_hairs_is_anopheles(self):
        res = evaluate_larval_deepkey({"float_hairs": "palmate_present"})
        assert res["resolved_genus"] == "Anopheles"
        assert res["resolution_level"] == "genus"

    def test_parallel_posture_is_anopheles(self):
        res = evaluate_larval_deepkey({"posture": "parallel", "siphon": "absent"})
        assert res["resolved_genus"] == "Anopheles"

    def test_long_slender_siphon_is_culex(self):
        res = evaluate_larval_deepkey({"siphon": "long_slender", "posture": "angled"})
        assert res["resolved_genus"] == "Culex"

    def test_short_stout_siphon_is_aedes(self):
        res = evaluate_larval_deepkey({"siphon": "short_stout", "posture": "angled"})
        assert res["resolved_genus"] == "Aedes"

    def test_striped_predator_flags_tigripes_biocontrol(self):
        res = evaluate_larval_deepkey({
            "siphon": "long_slender", "predator_habitus": "large_striped_predator"})
        assert res["resolved_genus"] == "Culex"
        assert res["biocontrol_candidate"] is True

    def test_never_claims_species(self):
        for chars in ({"float_hairs": "palmate_present"},
                      {"siphon": "long_slender"},
                      {"siphon": "short_stout", "posture": "angled"}):
            res = evaluate_larval_deepkey(chars)
            assert res["resolution_level"] in ("genus", "undetermined")

    def test_no_characters_is_inconclusive(self):
        res = evaluate_larval_deepkey({})
        assert res["resolution_level"] == "undetermined"


class TestExtendedCatalogAndComplexes:
    def test_catalog_counts_grew(self):
        assert len(SPECIES_CATALOG["Anopheles"]) == 37
        assert len(SPECIES_CATALOG["Culex"]) == 30
        assert len(SPECIES_CATALOG["Aedes"]) == 30

    def test_new_complexes_registered(self):
        for name in ("Vishnui Subgroup", "Cx. decens group",
                     "Ae. furcifer-taylori group", "Ae. caballus-juppi pair"):
            assert name in SPECIES_COMPLEXES, name

    def test_new_complex_triggers_reach_membership(self):
        trig = complex_membership_by_trigger()
        assert "amharicus" in trig["gambiae"]
        assert "longipalpis" in trig["marshallii"]
        assert "guiarti" in trig["decens"]
        assert "juppi" in trig["caballus"]
        assert "taylori" in trig["furcifer"]

    def test_every_profiled_culicine_complex_is_registered(self):
        for profiles in (CULEX_KEY_PROFILES, AEDES_KEY_PROFILES):
            for name, prof in profiles.items():
                cx = prof.get("complex")
                if cx and cx != "None":
                    assert cx in SPECIES_COMPLEXES, f"{name}: {cx} unregistered"

    def test_character_schemas_are_ui_ready(self):
        for schema in (get_culex_character_schema(), get_aedes_character_schema(),
                       get_larval_character_schema()):
            assert schema
            for ch in schema:
                assert ch["id"] and ch["label"] and ch["states"]
                assert all("id" in s and "label" in s for s in ch["states"])
