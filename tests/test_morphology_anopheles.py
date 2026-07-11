"""Unit tests for the Anopheles deep-key engine in utils.morphology_keys.

The single most important property under test is the taxonomy guardrail
(mirrored in models/ and utils/vision_inference.py): the *An. gambiae* complex
and *An. funestus* group are morphologically inseparable, so neither the
weighted character scorer nor the dichotomous couplet key may ever emit a bare
cryptic-complex member as a confident species — such hits must collapse to the
complex/group name with molecular_id_required=True. These tests lock that down,
plus the structural integrity of the couplet key graph.
"""

import pytest

from utils.morphology_keys import (
    ANOPHELES_COUPLET_KEY,
    ANOPHELES_KEY_PROFILES,
    ANOPHELES_KEY_ROOT,
    SPECIES_CATALOG,
    anopheles_key_node,
    anopheles_key_step,
    identify_anopheles_species,
)

# Species names that live inside a cryptic complex/group — these must NEVER be
# returned as a resolved taxon; they can only surface collapsed to their group.
CRYPTIC_MEMBER_NAMES = {
    name
    for name, prof in ANOPHELES_KEY_PROFILES.items()
    if prof.get("resolution_level") in ("complex", "group")
}

_ANOPHELES_CATALOG_NAMES = {sp["name"] for sp in SPECIES_CATALOG["Anopheles"]}


def _states(name: str) -> dict:
    """The full diagnostic character-state dict for a catalogued Anopheles."""
    return dict(ANOPHELES_KEY_PROFILES[name]["character_states"])


class TestComplexCollapse:
    def test_gambiae_pattern_collapses_to_complex(self):
        res = identify_anopheles_species(_states("Anopheles gambiae (s.s.)"))
        assert res["resolution_level"] == "complex"
        assert res["taxon"] == "An. gambiae complex"
        assert res["molecular_id_required"] is True
        # Never a bare member name.
        assert res["taxon"] not in CRYPTIC_MEMBER_NAMES
        assert "PCR" in res["next_step"]

    def test_funestus_pattern_collapses_to_group(self):
        res = identify_anopheles_species(_states("Anopheles funestus (s.s.)"))
        assert res["resolution_level"] == "group"
        assert res["taxon"] == "An. funestus group"
        assert res["molecular_id_required"] is True
        assert res["taxon"] not in CRYPTIC_MEMBER_NAMES

    def test_complex_members_listed_on_collapse(self):
        res = identify_anopheles_species(_states("Anopheles arabiensis"))
        # arabiensis is inseparable; result must be the complex, and enumerate kin.
        assert res["resolution_level"] == "complex"
        assert res["taxon"] == "An. gambiae complex"
        assert "Anopheles gambiae (s.s.)" in res.get("complex_members", [])
        assert "Anopheles arabiensis" in res.get("complex_members", [])

    def test_distinguishable_species_not_collapsed(self):
        res = identify_anopheles_species(_states("Anopheles pharoensis"))
        assert res["resolution_level"] == "species"
        assert res["taxon"] == "Anopheles pharoensis"
        # pharoensis is genuinely field-diagnostic — no PCR forced.
        assert res["molecular_id_required"] is False

    @pytest.mark.parametrize("name", sorted(ANOPHELES_KEY_PROFILES))
    def test_guardrail_never_emits_bare_cryptic_member(self, name):
        """For EVERY profile, feeding its own states must not yield a bare
        complex-member species, and any group/complex verdict forces PCR."""
        res = identify_anopheles_species(_states(name))
        assert res["taxon"] not in CRYPTIC_MEMBER_NAMES
        if res["resolution_level"] in ("complex", "group"):
            assert res["molecular_id_required"] is True
            assert "PCR" in res["next_step"]

    def test_empty_input_is_undetermined(self):
        res = identify_anopheles_species({})
        assert res["resolution_level"] == "undetermined"
        assert res["confidence"] == 0
        assert res["molecular_id_required"] is False

    def test_unknown_characters_are_ignored(self):
        # Junk keys/values must not raise and must not fabricate a match.
        res = identify_anopheles_species({"not_a_char": "nonsense", "proboscis": ""})
        assert res["resolution_level"] == "undetermined"

    def test_single_character_stays_at_genus(self):
        # One character is too little signal to commit below genus.
        res = identify_anopheles_species({"proboscis": "dark_uniform"})
        assert res["resolution_level"] == "genus"
        assert res["taxon"] == "Anopheles spp."

    def test_confidence_is_bounded(self):
        res = identify_anopheles_species(_states("Anopheles pharoensis"))
        assert 0 <= res["confidence"] <= 100


def _collect_key_terminals():
    """Depth-first walk of the whole couplet key; returns every terminal result.
    Also asserts there are no cycles and no dead 'goto' targets en route."""
    terminals = []

    def visit(node_id, seen):
        assert node_id not in seen, f"cycle detected at node {node_id}"
        node = anopheles_key_node(node_id)
        assert node is not None, f"missing key node {node_id}"
        for i in range(len(node["leads"])):
            step = anopheles_key_step(node_id, i)
            assert step["type"] != "error", f"error stepping {node_id}[{i}]: {step}"
            if step["type"] == "couplet":
                visit(step["node_id"], seen | {node_id})
            else:
                terminals.append(step["result"])

    visit(ANOPHELES_KEY_ROOT, set())
    return terminals


class TestCoupletKeyIntegrity:
    def test_all_goto_targets_exist(self):
        for node_id, node in ANOPHELES_COUPLET_KEY.items():
            for lead in node["leads"]:
                if "goto" in lead:
                    assert lead["goto"] in ANOPHELES_COUPLET_KEY, (
                        f"{node_id} points to missing node {lead['goto']}"
                    )

    def test_every_terminal_taxon_is_catalogued(self):
        for node in ANOPHELES_COUPLET_KEY.values():
            for lead in node["leads"]:
                if "taxon" in lead:
                    assert lead["taxon"] in ANOPHELES_KEY_PROFILES, lead["taxon"]
                    assert lead["taxon"] in _ANOPHELES_CATALOG_NAMES, lead["taxon"]

    def test_key_reaches_at_least_twelve_terminals(self):
        # Locks the expansion in — regressions that shrink the key will fail.
        terminals = _collect_key_terminals()
        assert len(terminals) >= 12

    def test_invalid_lead_index_returns_error(self):
        step = anopheles_key_step(ANOPHELES_KEY_ROOT, 99)
        assert step["type"] == "error"

    def test_unknown_node_returns_error(self):
        step = anopheles_key_step("does-not-exist", 0)
        assert step["type"] == "error"


class TestCoupletKeyGuardrail:
    def test_every_terminal_respects_the_guardrail(self):
        for result in _collect_key_terminals():
            # Never a bare cryptic member as the headline taxon.
            assert result["taxon"] not in CRYPTIC_MEMBER_NAMES
            assert isinstance(result["molecular_id_required"], bool)
            if result["resolution_level"] in ("complex", "group"):
                assert result["molecular_id_required"] is True
                assert "PCR" in result["next_step"]
            # The species the key actually terminated on is always catalogued.
            assert result["matched_species"] in ANOPHELES_KEY_PROFILES

    def test_gambiae_terminal_collapses_to_complex(self):
        # Walk: not broad/speckled → narrow rings → not speckled palps →
        # not pale-tipped → spotted wing → lowland → standard breeder.
        node = ANOPHELES_KEY_ROOT
        for choice in (1, 1, 1, 1, 1, 1, 1):
            step = anopheles_key_step(node, choice)
            if step["type"] == "terminal":
                result = step["result"]
                break
            node = step["node_id"]
        else:
            pytest.fail("did not reach a terminal walking the gambiae path")
        assert result["taxon"] == "An. gambiae complex"
        assert result["resolution_level"] == "complex"
        assert result["molecular_id_required"] is True

    def test_pharoensis_terminal_is_species_no_pcr(self):
        # Couplet 1 lead a (broad/speckled) → couplet 2 lead a (4 bands, large).
        step = anopheles_key_step(ANOPHELES_KEY_ROOT, 0)
        assert step["type"] == "couplet"
        step = anopheles_key_step(step["node_id"], 0)
        assert step["type"] == "terminal"
        result = step["result"]
        assert result["taxon"] == "Anopheles pharoensis"
        assert result["resolution_level"] == "species"
        assert result["molecular_id_required"] is False
