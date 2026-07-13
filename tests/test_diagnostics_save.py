"""Regression tests for the Diagnostics save paths, driven through Streamlit's AppTest.

These cover rerun behaviour, which no pure-function test can see:

1. A Save button rendered *inside* a block gated on another st.button is never
   instantiated on the rerun its own click triggers, so the click is discarded and the
   identification is silently lost. Every checklist save on this page had that shape.
2. st.file_uploader keeps its value across reruns, so calling the vision model
   unconditionally re-invokes it on every interaction — including the rerun a Save click
   causes. The model is non-deterministic, so the row saved could differ from the result
   the user actually reviewed.

AppTest.from_function runs the app without module globals, so each app body imports what
it needs and communicates through session_state.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def submitted(monkeypatch):
    """Capture writes to the specimen ledger instead of hitting Supabase."""
    calls = []

    import components.diagnostics as diagnostics

    def fake_submit(screening_method, result, **kwargs):
        calls.append((screening_method, result))
        return {"specimen_id": "new-specimen-uuid"}

    monkeypatch.setattr(diagnostics, "submit_screening_result", fake_submit)
    monkeypatch.setattr(diagnostics, "load_specimen_records", lambda: pd.DataFrame())
    return calls


def _diagnostics_app():
    import components.diagnostics as diagnostics

    diagnostics.render_diagnostics_page()


class TestChecklistSaveReachesTheLedger:
    def test_larval_checklist_save_persists(self, submitted):
        at = AppTest.from_function(_diagnostics_app, default_timeout=30)
        at.run()

        at.button(key="larval_resolve").click().run()
        at.button(key="save_checklist_larval").click().run()

        # The click must survive the rerun it triggers and reach the ledger exactly once.
        assert len(submitted) == 1
        method, result = submitted[0]
        assert method == "manual_checklist"
        assert result["genus"] == "Anopheles"

    def test_result_panel_resets_so_save_cannot_double_insert(self, submitted):
        at = AppTest.from_function(_diagnostics_app, default_timeout=30)
        at.run()

        at.button(key="larval_resolve").click().run()
        at.button(key="save_checklist_larval").click().run()

        # A working button on an already-saved result would insert a second record for
        # the same mosquito, so the panel clears once the write lands.
        assert not any(b.key == "save_checklist_larval" for b in at.button)
        assert any("new-specimen-uuid" in s.value for s in at.success)


class TestVisionInferenceRunsOncePerImage:
    def test_model_not_reinvoked_on_rerun(self):
        def app():
            import io

            import streamlit as st

            from components.diagnostics import _screen_image_once

            st.session_state.setdefault("n_calls", 0)

            def counting_infer(uploaded):
                st.session_state["n_calls"] += 1
                return {"genus": f"call-{st.session_state['n_calls']}"}

            result = _screen_image_once(
                io.BytesIO(b"photo-bytes"), "vision_cache", counting_infer
            )
            st.write(result["genus"])

        at = AppTest.from_function(app, default_timeout=30)
        at.run()
        at.run()
        at.run()

        # Three reruns, one image: the model runs once and the shown result never drifts.
        assert at.session_state["n_calls"] == 1
        assert any("call-1" in m.value for m in at.markdown)
