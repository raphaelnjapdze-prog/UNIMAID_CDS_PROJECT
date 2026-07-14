"""PCR confirmation: the specimen picker, and the save surviving its own rerun.

The whole form used to live inside `if st.button("Look up specimen"):`. A form's Submit
click triggers a rerun, on which that button evaluates False — so the form was never
instantiated, the submitted values went nowhere, and the PCR result was silently
discarded. The identical bug was fixed on the Diagnostics page (commit 1497660); this one
survived because nothing exercised it.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from utils.data_manager import pcr_specimen_label, specimens_ready_for_pcr


def _row(specimen_id, method, tube=None, genus="Anopheles", pcr="not_submitted", date="2026-07-13"):
    if method == "field_subsample":
        screening = {"screening_method": method, "result": {"genus": genus, "pending_identification": True}}
    elif method == "manual_field_log":
        screening = {"screening_method": method, "result": {"anopheles_count": 500}}
    else:
        screening = {"screening_method": method, "result": {"genus": genus}}
    return {
        "specimen_id": specimen_id,
        "tube_label": tube,
        "collection_date": date,
        "pcr_status": pcr,
        "field_screening_result": screening,
    }


class TestOnlyIdentifiedSpecimensAreOfferedForPcr:
    def test_batch_logs_and_unidentified_vials_are_excluded(self):
        df = pd.DataFrame([
            _row("batch-1", "manual_field_log"),          # a bulk count, not an individual
            _row("vial-1", "field_subsample", tube="T-1"),  # vialed but nobody identified it
            _row("ident-1", "ai_vision", tube="T-2"),       # identified — PCR can confirm this
            _row("ident-2", "manual_checklist"),
        ])

        ready = specimens_ready_for_pcr(df)

        # PCR confirms or overturns an identification. A batch is a night's catch, not one
        # mosquito; an unidentified vial has nothing for PCR to confirm against.
        assert sorted(ready["specimen_id"]) == ["ident-1", "ident-2"]

    def test_empty_ledger(self):
        assert specimens_ready_for_pcr(pd.DataFrame()).empty


class TestSpecimenLabelIsReadable:
    def test_leads_with_the_tube_label(self):
        label = pcr_specimen_label(_row("aaaabbbbcccc", "manual_checklist", tube="LAB-1"))
        # Lab staff hold a tube, not a UUID.
        assert label.startswith("LAB-1")
        assert "Anopheles" in label
        assert "aaaabbbb" in label

    def test_confirmed_specimens_are_marked(self):
        label = pcr_specimen_label(_row("x", "ai_vision", tube="T-9", pcr="confirmed"))
        assert label.startswith("✔")

    def test_untubed_specimen_still_labelled(self):
        label = pcr_specimen_label(_row("ddddeeee", "ai_vision"))
        assert "Anopheles" in label and "ddddeeee" in label


@pytest.fixture
def pcr_app(monkeypatch):
    """The PCR page with a fake Supabase; captures what a Submit click would write."""
    saved = []

    import utils.pcr_and_accuracy as pcr

    record = {
        "specimen_id": "vial-1",
        "tube_label": "LAB-1",
        "collection_date": "2026-07-13",
        "pcr_status": "not_submitted",
        "pcr_confirmed_species": None,
        "pcr_lab_reference": None,
        "pcr_confirmed_date": None,
        "field_screening_result": {"screening_method": "manual_checklist", "result": {"genus": "Anopheles"}},
    }

    monkeypatch.setattr(pcr, "get_supabase_client", lambda: object())
    monkeypatch.setattr(pcr, "load_specimen_records", lambda: pd.DataFrame([record]))
    monkeypatch.setattr(pcr, "fetch_specimen_by_id", lambda _c, _i: dict(record))

    def fake_update(_client, specimen_id, fields):
        saved.append({"specimen_id": specimen_id, **fields})
        return {**record, **fields}

    monkeypatch.setattr(pcr, "update_specimen_pcr", fake_update)
    return saved


def _pcr_page():
    from utils.pcr_and_accuracy import render_pcr_confirmation_form

    render_pcr_confirmation_form()


class TestSubmitSurvivesItsOwnRerun:
    def test_pcr_result_reaches_the_database(self, pcr_app):
        at = AppTest.from_function(_pcr_page, default_timeout=30)
        at.run()

        # Pick the identified specimen from the dropdown.
        at.selectbox[0].select_index(1).run()

        # Fill the form and submit. The submit triggers a rerun; the form must still be
        # rendered on it, or the click is discarded and the result silently lost.
        at.selectbox[1].set_value("confirmed").run()
        at.text_input[0].set_value("Anopheles coluzzii").run()
        at.button[0].click().run()

        assert not at.exception
        assert len(pcr_app) == 1, "the PCR submission never reached the database"
        assert pcr_app[0]["specimen_id"] == "vial-1"
        assert pcr_app[0]["pcr_status"] == "confirmed"
        assert pcr_app[0]["pcr_confirmed_species"] == "Anopheles coluzzii"

    def test_only_pcr_columns_are_written(self, pcr_app):
        """The write must be an UPDATE of the PCR columns, carrying nothing else.

        It used to be an upsert (INSERT … ON CONFLICT DO UPDATE). Postgres validates the
        proposed insert row against NOT NULL *before* it detects the conflict, so a payload
        holding only the PCR columns was rejected outright:

            null value in column "collection_date" ... violates not-null constraint

        Confirming a PCR result must never create a specimen either: a mosquito nobody
        collected cannot have a PCR result.
        """
        at = AppTest.from_function(_pcr_page, default_timeout=30)
        at.run()
        at.selectbox[0].select_index(1).run()
        at.selectbox[1].set_value("confirmed").run()
        at.button[0].click().run()

        written = pcr_app[0]
        assert set(written) == {
            "specimen_id",            # the .eq() filter, not part of the payload
            "pcr_status",
            "pcr_confirmed_species",
            "pcr_lab_reference",
            "pcr_confirmed_date",
        }
        # Nothing about the collection event may be touched by a lab form.
        for column in ("collection_date", "collector_id", "field_screening_result"):
            assert column not in written

    def test_nothing_is_written_before_a_specimen_is_chosen(self, pcr_app):
        at = AppTest.from_function(_pcr_page, default_timeout=30)
        at.run()

        # Nothing selected: no form, no write.
        assert not pcr_app
        assert not at.exception
