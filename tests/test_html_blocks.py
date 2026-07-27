"""Regression tests: hand-built HTML blocks must never leak raw markup into the UI.

Several pages draw cards and headers with `st.markdown(..., unsafe_allow_html=True)`.
Streamlit dedents the string, then markdown parses it — and a blank line *closes* a
raw-HTML block, so everything after it is escaped and rendered as literal markup on the
page. That happens whenever an interpolated fragment sits alone on its source line and
comes out empty: the line collapses to whitespace, dedent normalises it to a blank line,
and the block spills its own HTML into the UI.

Two places had exactly that shape:

- `diagnostics._render_species_candidates` — its `group_line` is empty for any species
  with no cryptic complex, which is most of the Culex and Aedes catalog, so those two
  genera spilled markup on nearly every card. Visible breakage.
- `dashboard._section` — its `caption_html` is empty on every captionless section (five
  of six call sites). Only a closing tag trailed the blank line there, so nothing
  visible leaked, but the wrapper div fell out of the block and anything added below
  the caption would have been escaped onto the page.

The fix in both is flat single-line HTML with the empty parts dropped. These tests pin
that property for every block those functions can draw, driven from real catalog and
key-profile data rather than hand-written fixtures.
"""
import textwrap

import pytest
from streamlit.testing.v1 import AppTest

from utils.morphology_keys import (
    AEDES_KEY_PROFILES,
    CULEX_KEY_PROFILES,
    SPECIES_CATALOG,
)

GENERA = ["Anopheles", "Culex", "Aedes"]


def _interior_blank_lines(body: str) -> list[int]:
    """Blank lines with content on both sides — the ones that close an HTML block.

    Applies Streamlit's own dedent first, since that is what turns an indented
    whitespace-only line into a block-terminating blank one.
    """
    lines = textwrap.dedent(body).split("\n")
    return [
        i for i, line in enumerate(lines)
        if not line.strip()
        and any(x.strip() for x in lines[:i])
        and any(x.strip() for x in lines[i + 1:])
    ]


def _assert_no_spilled_markup(at):
    assert not at.exception, [e.value for e in at.exception]
    rendered = [md.value for md in at.markdown if "<div" in md.value]
    assert rendered, "expected at least one HTML card to be rendered"
    for body in rendered:
        broken = _interior_blank_lines(body)
        assert not broken, (
            f"blank line(s) at {broken} close the raw-HTML block, so the rest of this "
            f"card renders as literal markup:\n{textwrap.dedent(body)}"
        )


def _all_markers(genus: str) -> list[str]:
    return sorted({m for sp in SPECIES_CATALOG[genus] for m in sp.get("field_markers", [])})


class TestDashboardSectionHeaders:
    """`_section` renders a title with an optional caption — the caption is the empty case."""

    def test_header_with_a_caption_does_not_spill_html(self):
        def app():
            from components.dashboard import _section

            _section("Specimen Ledger", "Every stored record.")

        at = AppTest.from_function(app, default_timeout=30)
        at.run()
        _assert_no_spilled_markup(at)

    def test_header_without_a_caption_does_not_spill_html(self):
        """The case that broke: five of six dashboard sections pass no caption."""
        def app():
            from components.dashboard import _section

            _section("Genus Distribution")

        at = AppTest.from_function(app, default_timeout=30)
        at.run()
        _assert_no_spilled_markup(at)
        # The title must sit in the same block as its wrapper, not be split off by a
        # blank line — which is what the interior-blank-line check above enforces.
        assert any("Genus Distribution" in md.value for md in at.markdown)


class TestSpeciesCandidateCards:
    @pytest.mark.parametrize("genus", GENERA)
    def test_candidate_cards_do_not_spill_html(self, genus):
        def app():
            import streamlit as st

            from components.diagnostics import _render_species_candidates
            from utils.morphology_keys import search_species_reference

            candidates = search_species_reference(st.session_state["genus"], st.session_state["markers"])
            _render_species_candidates(candidates, markers_ticked=True)

        at = AppTest.from_function(app, default_timeout=30)
        at.session_state["genus"] = genus
        at.session_state["markers"] = _all_markers(genus)
        at.run()
        _assert_no_spilled_markup(at)

    @pytest.mark.parametrize("genus", GENERA)
    def test_cards_render_for_species_with_no_complex(self, genus):
        """The case that broke: `group_line` empty. Culex/Aedes are mostly complex-free."""
        def app():
            import streamlit as st

            from components.diagnostics import _render_species_candidates
            from utils.morphology_keys import search_species_reference

            candidates = [
                c for c in search_species_reference(st.session_state["genus"], st.session_state["markers"])
                if c.get("group_complex") in (None, "None")
            ]
            st.session_state["n_complex_free"] = len(candidates)
            _render_species_candidates(candidates, markers_ticked=True)

        at = AppTest.from_function(app, default_timeout=30)
        at.session_state["genus"] = genus
        at.session_state["markers"] = _all_markers(genus)
        at.run()
        assert at.session_state["n_complex_free"] > 0, f"no complex-free {genus} to exercise"
        _assert_no_spilled_markup(at)


class TestGenusTriageCard:
    def test_genus_card_does_not_spill_html(self):
        def app():
            from components.diagnostics import _render_genus_result

            _render_genus_result({"genus": "Culex", "confidence": 88, "reason": "Blunt abdomen tip."})

        at = AppTest.from_function(app, default_timeout=30)
        at.run()
        _assert_no_spilled_markup(at)

    def test_genus_card_survives_a_missing_reason(self):
        def app():
            from components.diagnostics import _render_genus_result

            _render_genus_result({"genus": "Aedes", "confidence": 71})

        at = AppTest.from_function(app, default_timeout=30)
        at.run()
        _assert_no_spilled_markup(at)


class TestDeepKeyVerdictCards:
    """The Culex/Aedes engine feeds the shared character-identification renderer.

    Driven from the real key profiles, so every verdict shape the engine can emit —
    species, complex, group, biosecurity-flagged — gets its card checked.
    """

    @pytest.mark.parametrize(
        ("genus", "species"),
        [("Culex", name) for name in CULEX_KEY_PROFILES]
        + [("Aedes", name) for name in AEDES_KEY_PROFILES],
    )
    def test_verdict_card_does_not_spill_html(self, genus, species):
        def app():
            import streamlit as st

            import components.diagnostics as diagnostics
            from utils.morphology_keys import (
                AEDES_KEY_PROFILES,
                CULEX_KEY_PROFILES,
                identify_aedes_species,
                identify_culex_species,
            )

            if st.session_state["genus"] == "Culex":
                profiles, identify = CULEX_KEY_PROFILES, identify_culex_species
            else:
                profiles, identify = AEDES_KEY_PROFILES, identify_aedes_species

            result = identify(dict(profiles[st.session_state["species"]]["character_states"]))
            diagnostics._render_character_identification(
                result,
                default_taxon=f"{st.session_state['genus']} spp.",
                caption=diagnostics._CULICINE_ENGINE_CAPTION,
            )

        at = AppTest.from_function(app, default_timeout=30)
        at.session_state["genus"] = genus
        at.session_state["species"] = species
        at.run()
        _assert_no_spilled_markup(at)

    @pytest.mark.parametrize("genus", ["Culex", "Aedes"])
    def test_undetermined_verdict_does_not_spill_html(self, genus):
        """Empty reason/next_step/badges — the worst case for the flat-HTML rule."""
        def app():
            import streamlit as st

            import components.diagnostics as diagnostics

            diagnostics._render_character_identification(
                {"resolution_level": "undetermined", "confidence": 0, "candidates": []},
                default_taxon=f"{st.session_state['genus']} spp.",
                caption=diagnostics._CULICINE_ENGINE_CAPTION,
            )

        at = AppTest.from_function(app, default_timeout=30)
        at.session_state["genus"] = genus
        at.run()
        _assert_no_spilled_markup(at)
