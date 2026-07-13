"""The site-log page must survive a successful save.

The whole post-save block — success message, QR label, photo preview — was rendered
inside `with st.form(...)`, and render_specimen_qr() calls st.download_button(), which
Streamlit refuses to draw inside a form. So the entry saved to the database and the page
then crashed with StreamlitAPIException while drawing the label for it: the user saw a
traceback instead of the QR code they need to attach to the physical specimen.

Driven through AppTest because no pure-function test can see it — the exception comes
from Streamlit's own form/widget rules at render time.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


@pytest.fixture
def saved_rows(monkeypatch):
    """Capture site-log writes instead of hitting Supabase."""
    calls = []

    import components.site_log as site_log

    def fake_submit(**kwargs):
        calls.append(kwargs)
        return {"specimen_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "photo_urls": []}

    monkeypatch.setattr(site_log, "submit_site_log_entry", fake_submit)
    monkeypatch.setattr(site_log, "load_specimen_records", lambda: pd.DataFrame())
    monkeypatch.setattr(site_log, "clear_specimen_records_cache", lambda: None)
    return calls


def _site_log_app():
    import components.site_log as site_log

    site_log.render_site_log_page()


class TestSaveRendersTheQrLabel:
    def test_successful_save_does_not_crash_the_page(self, saved_rows):
        at = AppTest.from_function(_site_log_app, default_timeout=30)
        at.run()

        at.button[0].click().run()  # the form's submit button

        # The row reached the ledger, and the page rendered its QR label without
        # tripping Streamlit's "no download_button inside st.form" rule.
        assert len(saved_rows) == 1
        assert not at.exception
        assert any("aaaaaaaa" in s.value for s in at.success)

    def test_label_survives_the_rerun_a_download_click_causes(self, saved_rows):
        at = AppTest.from_function(_site_log_app, default_timeout=30)
        at.run()
        at.button[0].click().run()

        at.run()  # any later rerun, e.g. the one clicking the download button triggers

        # A label drawn once and then dropped would take its own download with it.
        assert not at.exception
        assert any("aaaaaaaa" in s.value for s in at.success)
