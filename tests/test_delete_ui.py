"""The delete controls must reach the data layer, and must not fire without confirmation.

Same rerun trap this page has been bitten by twice (1497660, and the PCR form): a button
rendered inside a block gated on another widget is not instantiated on the rerun its own
click triggers, so the click is discarded. A delete that silently does nothing is exactly
the symptom that started this work, so it gets a test rather than a manual check.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest


def _row(specimen_id, *, anopheles=500, vialed=None, date="2026-07-20"):
    result: dict = {"anopheles_count": anopheles, "culex_count": 0, "aedes_count": 0}
    if vialed:
        result["vialed_out"] = dict(vialed)
    return {
        "specimen_id": specimen_id,
        "collection_date": date,
        "breeding_site_type": "Stagnant pool",
        "collector_id": "me",
        "pcr_status": "not_submitted",
        "photo_urls": [],
        "field_screening_result": {"screening_method": "manual_field_log", "result": result},
    }


@pytest.fixture
def site_log(monkeypatch):
    """The Site Log page with a fake ledger; captures what a delete click would remove."""
    deleted = []

    import components.site_log as site_log

    def fake_delete(specimen_ids, **_kwargs):
        deleted.append(list(specimen_ids))
        return {
            "requested": len(specimen_ids), "deleted": len(specimen_ids),
            "cascaded_children": 0, "photos_removed": 0,
            "batches_restored": {}, "tally_failures": [], "not_deleted": [],
        }

    monkeypatch.setattr(site_log, "delete_specimen_records", fake_delete)
    # Deletion is ownership-scoped, so the page needs to know who is looking: these rows
    # are stamped collector_id="me", and a picker that does not know it is "me" correctly
    # shows nothing at all.
    monkeypatch.setattr(site_log, "get_current_user_id", lambda: "me")
    monkeypatch.setattr(site_log, "is_current_user_admin", lambda: False)
    monkeypatch.setattr(
        site_log, "load_specimen_records",
        lambda: pd.DataFrame([_row("batch-1"), _row("batch-2", date="2026-07-19")]),
    )
    monkeypatch.setattr(site_log, "fetch_batch_children", lambda _b: pd.DataFrame())
    monkeypatch.setattr(site_log, "pending_count", lambda: 0)
    monkeypatch.setattr(site_log, "get_quarantine", lambda: [])
    return deleted


def _recent_entries_app():
    from components.site_log import _render_recent_entries

    _render_recent_entries()


def _pick_first_entry(at):
    at.multiselect(key="sitelog_delete_pick").select(
        at.multiselect(key="sitelog_delete_pick").options[0]
    ).run()
    return at


class TestDeleteReachesTheDataLayer:
    def test_confirmed_delete_removes_the_selected_entry(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        _pick_first_entry(at)
        at.text_input(key="sitelog_delete_confirm").set_value("DELETE").run()
        at.button(key="sitelog_delete_go").click().run()

        assert not at.exception
        assert len(site_log) == 1, "the delete click never reached the data layer"
        assert len(site_log[0]) == 1

    def test_only_the_selected_entries_are_deleted(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        picker = at.multiselect(key="sitelog_delete_pick")
        at.multiselect(key="sitelog_delete_pick").select(picker.options[1]).run()
        at.text_input(key="sitelog_delete_confirm").set_value("DELETE").run()
        at.button(key="sitelog_delete_go").click().run()

        assert len(site_log) == 1
        # The second entry in the list is the older one; the first must be untouched.
        assert site_log[0] == ["batch-2"]

    def test_summary_is_reported_after_the_rerun(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        _pick_first_entry(at)
        at.text_input(key="sitelog_delete_confirm").set_value("DELETE").run()
        at.button(key="sitelog_delete_go").click().run()

        # The delete triggers a rerun; the confirmation must survive it, or the user is
        # left unsure whether anything happened.
        assert any("Deleted" in s.value for s in at.success)


class TestDeleteRequiresConfirmation:
    def test_button_is_disabled_until_delete_is_typed(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        _pick_first_entry(at)

        assert at.button(key="sitelog_delete_go").disabled
        assert site_log == []

    def test_wrong_confirmation_text_keeps_it_disabled(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        _pick_first_entry(at)
        at.text_input(key="sitelog_delete_confirm").set_value("delete everything").run()

        assert at.button(key="sitelog_delete_go").disabled

    def test_confirmation_is_case_insensitive(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        _pick_first_entry(at)
        at.text_input(key="sitelog_delete_confirm").set_value(" delete ").run()

        assert not at.button(key="sitelog_delete_go").disabled

    def test_no_delete_controls_before_anything_is_selected(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        # Nothing selected: no confirmation field and no armed button to mis-click.
        assert not any(b.key == "sitelog_delete_go" for b in at.button)
        assert not any(t.key == "sitelog_delete_confirm" for t in at.text_input)


class TestFailedDeleteIsNotReportedAsSuccess:
    def test_a_refused_delete_shows_no_success_message(self, monkeypatch):
        import components.site_log as site_log

        monkeypatch.setattr(site_log, "delete_specimen_records", lambda *_a, **_k: None)
        monkeypatch.setattr(site_log, "load_specimen_records", lambda: pd.DataFrame([_row("batch-1")]))
        monkeypatch.setattr(site_log, "fetch_batch_children", lambda _b: pd.DataFrame())
        monkeypatch.setattr(site_log, "get_current_user_id", lambda: "me")
        monkeypatch.setattr(site_log, "is_current_user_admin", lambda: False)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()
        _pick_first_entry(at)
        at.text_input(key="sitelog_delete_confirm").set_value("DELETE").run()
        at.button(key="sitelog_delete_go").click().run()

        # delete_specimen_records reports its own error; the page must not add a
        # "Deleted N record(s)" on top of a deletion that did not happen.
        assert not any("Deleted" in s.value for s in at.success)


class TestVialedIndividualsAreFlaggedBeforeConfirming:
    def test_linked_specimen_count_is_shown(self, site_log, monkeypatch):
        import components.site_log as site_log_mod

        monkeypatch.setattr(
            site_log_mod, "fetch_batch_children",
            lambda _b: pd.DataFrame([{"specimen_id": f"v{i}"} for i in range(40)]),
        )

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()
        _pick_first_entry(at)

        # A batch with 40 vialed-out individuals looks like one row in the table. The user
        # must be told what else goes before typing DELETE.
        assert any("40" in w.value for w in at.warning)


class TestTheAdminBulkDeleteIsReachable:
    """The project-wide delete lived inside the entry picker, which returns early — when
    nothing is selected, and when there is nothing to select. So it only appeared after you
    had ticked an entry in the list above it, and never at all for an admin with no entries
    of their own. Caught by opening the page, not by any test, which is why these exist."""

    def _as_admin(self, monkeypatch, *, passkey_set=True, owner="me"):
        import components.site_log as site_log

        monkeypatch.setattr(site_log, "is_current_user_admin", lambda: True)
        monkeypatch.setattr(site_log, "get_current_user_id", lambda: "me")
        monkeypatch.setattr(site_log, "admin_passkey_configured", lambda: passkey_set)
        monkeypatch.setattr(site_log, "fetch_batch_children", lambda _b: pd.DataFrame())
        monkeypatch.setattr(site_log, "delete_specimen_records", lambda *_a, **_k: None)
        monkeypatch.setattr(site_log, "delete_all_specimen_records", lambda *_a, **_k: None)
        row = _row("batch-1")
        row["collector_id"] = owner
        monkeypatch.setattr(site_log, "load_specimen_records", lambda: pd.DataFrame([row]))

    def test_an_admin_sees_it_without_selecting_anything(self, monkeypatch):
        self._as_admin(monkeypatch)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert any(t.key == "sitelog_admin_passkey" for t in at.text_input)

    def test_an_admin_sees_it_when_every_entry_belongs_to_someone_else(self, monkeypatch):
        """Clearing a project you did not personally log is the whole point of the control,
        so it must not depend on the admin having entries of their own in the picker."""
        self._as_admin(monkeypatch, owner="another-investigator")

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert any(t.key == "sitelog_admin_passkey" for t in at.text_input)

    def test_a_non_admin_never_sees_it(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert not any(t.key == "sitelog_admin_passkey" for t in at.text_input)
        assert not any(b.key == "sitelog_admin_go" for b in at.button)

    def test_no_passkey_configured_disables_it_rather_than_prompting(self, monkeypatch):
        """A prompt that cannot succeed no matter what is typed is worse than saying so."""
        self._as_admin(monkeypatch, passkey_set=False)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert not any(t.key == "sitelog_admin_passkey" for t in at.text_input)
        assert any("passkey is configured" in i.value for i in at.info)

    def test_the_button_stays_disabled_until_both_gates_are_filled(self, monkeypatch):
        self._as_admin(monkeypatch)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert at.button(key="sitelog_admin_go").disabled, "armed with neither field filled"

        at.text_input(key="sitelog_admin_passkey").set_value("something").run()
        assert at.button(key="sitelog_admin_go").disabled, "armed on the passkey alone"

        at.text_input(key="sitelog_admin_confirm").set_value("DELETE EVERYTHING").run()
        assert not at.button(key="sitelog_admin_go").disabled
