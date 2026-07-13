"""Every specimen row must carry the identity of the user who created it.

submit_screening_result() used to take collector_id as an optional argument, and the
Diagnostics page — its only caller — never passed one. So every identification saved
from that page (checklist, AI vision, trained classifier) landed with a null collector:
invisible to the author's own "Export my data", which filters on collector_id, and with
no record of who made the call on the specimen.

These tests pin the identity stamp onto the write paths, not the callers, so a new save
path cannot reintroduce an anonymous row simply by forgetting an argument.
"""
import pytest
import streamlit as st

import utils.data_manager as data_manager
import utils.specimen_submission as specimen_submission


class FakeTable:
    """Records what would have been written to specimen_records."""

    def __init__(self, sink):
        self.sink = sink

    def insert(self, record):
        self.sink.append(record)
        return self

    def execute(self):
        return type("Resp", (), {"data": [dict(self.sink[-1], specimen_id="saved-id")]})()


class FakeClient:
    def __init__(self, sink):
        self.sink = sink

    def table(self, _name):
        return FakeTable(self.sink)


@pytest.fixture
def written(monkeypatch):
    """Capture the row handed to Supabase, with a signed-in user in session."""
    rows = []
    monkeypatch.setattr(specimen_submission, "get_supabase_client", lambda: FakeClient(rows))
    monkeypatch.setattr(specimen_submission, "clear_specimen_records_cache", lambda: None)
    st.session_state["auth_user_id"] = "user-uuid-123"
    st.session_state["auth_user_name"] = "A. Musa"
    st.session_state["auth_user_email"] = "a.musa@unimaid.edu.ng"
    yield rows
    st.session_state.clear()


class TestIdentificationsAreAttributed:
    def test_collector_id_defaults_to_the_signed_in_user(self, written):
        saved = specimen_submission.submit_screening_result(
            screening_method="manual_checklist", result={"genus": "Anopheles"}
        )

        assert saved is not None
        # The caller passed no collector_id at all — exactly how diagnostics.py calls it.
        assert written[0]["collector_id"] == "user-uuid-123"

    def test_human_readable_name_travels_with_the_id(self, written):
        specimen_submission.submit_screening_result(
            screening_method="ai_vision", result={"genus": "Culex"}
        )

        # A bare UUID is useless in an exported CSV; the name rides alongside it.
        assert written[0]["field_screening_result"]["collector_label"] == "A. Musa"

    def test_explicit_collector_id_still_wins(self, written):
        specimen_submission.submit_screening_result(
            screening_method="manual_checklist",
            result={"genus": "Aedes"},
            collector_id="someone-else",
        )

        assert written[0]["collector_id"] == "someone-else"

    def test_unauthenticated_save_is_refused(self, monkeypatch, written):
        st.session_state.clear()  # nobody signed in
        errors = []
        monkeypatch.setattr(data_manager.st, "error", errors.append)

        saved = specimen_submission.submit_screening_result(
            screening_method="manual_checklist", result={"genus": "Anopheles"}
        )

        # An unattributed identification is refused outright, not written anonymously.
        assert saved is None
        assert not written
        assert errors


class TestBlankIdIsNotAnIdentity:
    """The live table declares collector_id NOT NULL — and still accumulated blank
    collectors, because get_current_user_id() returns "" for a session with no user and
    Postgres considers an empty string a perfectly good NOT NULL value. The constraint
    never fired. The guard has to reject the blank itself, not rely on the database."""

    def test_empty_string_user_id_is_refused(self, monkeypatch):
        errors = []
        monkeypatch.setattr(data_manager.st, "error", errors.append)
        st.session_state.clear()
        st.session_state["auth_user_id"] = ""

        assert data_manager.require_current_user_id() is None
        assert errors
        st.session_state.clear()

    def test_whitespace_only_user_id_is_refused(self, monkeypatch):
        monkeypatch.setattr(data_manager.st, "error", lambda *_: None)
        st.session_state.clear()
        st.session_state["auth_user_id"] = "   "

        assert data_manager.require_current_user_id() is None
        st.session_state.clear()

    def test_real_id_passes_through_stripped(self, monkeypatch):
        monkeypatch.setattr(data_manager.st, "error", lambda *_: None)
        st.session_state.clear()
        st.session_state["auth_user_id"] = " user-uuid-123 "

        assert data_manager.require_current_user_id() == "user-uuid-123"
        st.session_state.clear()


class TestCollectorIsShownReadably:
    """collector_id is a UUID. Tables and exports have to show a person."""

    def test_prefers_the_stamped_label(self):
        row = {
            "collector_id": "9f3c1e88-1111-2222-3333-444455556666",
            "field_screening_result": {"collector_label": "A. Musa"},
        }
        assert data_manager.extract_collector_display(row) == "A. Musa"

    def test_legacy_rows_say_so_rather_than_naming_anyone(self):
        # The author of these was never recorded and cannot be recovered. Showing a guess
        # would put someone's name on work that may not be theirs.
        row = {"collector_id": "unattributed-legacy", "field_screening_result": {}}
        assert data_manager.extract_collector_display(row) == "Unattributed (pre-identity record)"

    def test_row_without_a_label_falls_back_to_a_short_id(self):
        # Written after collector_id was enforced but before the label existed: the cell
        # must still say something, never sit blank.
        row = {
            "collector_id": "9f3c1e88-1111-2222-3333-444455556666",
            "field_screening_result": {},
        }
        assert data_manager.extract_collector_display(row) == "ID 9f3c1e88…"

    def test_json_string_column_is_parsed(self):
        row = {
            "collector_id": "abc",
            "field_screening_result": '{"collector_label": "A. Musa"}',
        }
        assert data_manager.extract_collector_display(row) == "A. Musa"

    def test_dataframe_gets_a_collector_column(self):
        import pandas as pd

        df = pd.DataFrame([
            {"collector_id": "u1", "field_screening_result": {"collector_label": "A. Musa"}},
            {"collector_id": "unattributed-legacy", "field_screening_result": {}},
        ])
        out = data_manager.add_collector_column(df)

        assert list(out["Collector"]) == ["A. Musa", "Unattributed (pre-identity record)"]
        # The source frame is not mutated — callers reuse it for exports.
        assert "Collector" not in df.columns


class TestCollectorLabelFallback:
    def test_falls_back_to_email_when_no_display_name(self):
        # Supabase accounts created without full_name in user_metadata have no name.
        st.session_state.clear()
        st.session_state["auth_user_id"] = "user-uuid-123"
        st.session_state["auth_user_email"] = "a.musa@unimaid.edu.ng"

        assert data_manager.get_collector_label() == "a.musa@unimaid.edu.ng"
        st.session_state.clear()

    def test_empty_when_nobody_is_signed_in(self):
        st.session_state.clear()
        assert data_manager.get_collector_label() == ""
