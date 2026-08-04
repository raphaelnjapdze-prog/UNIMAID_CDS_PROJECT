"""The delete controls must reach the data layer, and must not fire without confirmation.

Same rerun trap this page has been bitten by twice (1497660, and the PCR form): a button
rendered inside a block gated on another widget is not instantiated on the rerun its own
click triggers, so the click is discarded. A delete that silently does nothing is exactly
the symptom that started this work, so it gets a test rather than a manual check.
"""
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from components.profile import _RESET_SCOPE_ALL as _ALL


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


class TestSiteLogHasNoProjectWideDelete:
    """The Site Log page deletes what you picked, and nothing else.

    It used to carry a project-wide "delete every entry" control of its own, next to the
    picker. That made two irreversible controls for the same action, gated differently —
    the Site Log one asked for the delete passkey, and the Profile one (reachable by
    choosing "Every record in the project") did not. The passkey-gated version is the one
    that survived, on Profile; these assert the duplicate is gone rather than merely
    hidden, since a control that reappears for admins is the failure worth catching."""

    def test_a_non_admin_sees_no_project_wide_control(self, site_log):
        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert not any(t.key == "sitelog_admin_passkey" for t in at.text_input)
        assert not any(b.key == "sitelog_admin_go" for b in at.button)

    def test_an_admin_sees_no_project_wide_control_either(self, site_log, monkeypatch):
        import components.site_log as site_log_mod

        monkeypatch.setattr(site_log_mod, "is_current_user_admin", lambda: True)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert not any(t.key == "sitelog_admin_passkey" for t in at.text_input)
        assert not any(b.key == "sitelog_admin_go" for b in at.button)

    def test_an_admin_is_told_where_the_project_wide_delete_went(self, site_log, monkeypatch):
        """Moving a control without saying so just makes it look deleted."""
        import components.site_log as site_log_mod

        monkeypatch.setattr(site_log_mod, "is_current_user_admin", lambda: True)

        at = AppTest.from_function(_recent_entries_app, default_timeout=30)
        at.run()

        assert any("Profile" in c.value for c in at.caption)


def _trial_reset_app():
    from components.profile import _render_trial_data_reset

    _render_trial_data_reset("me")


def _profile_page_app():
    from components.profile import render_profile_page

    render_profile_page()


class TestTheProjectWideDeleteIsGatedByThePasskey:
    """Profile's "Every record in the project" reset deletes everyone's data, and before
    the Site Log control was folded into it, it asked only for the word RESET — the passkey
    lived on the other page, guarding the other copy of the same action. These pin that the
    project-wide path cannot run without it, and that the scoped path is not burdened by
    it: clearing your own trial run is not an administrative act."""

    def _profile(self, monkeypatch, *, admin=True, passkey_set=True, passkey_ok=True):
        import components.profile as profile

        monkeypatch.setattr(profile, "is_current_user_admin", lambda: admin)
        monkeypatch.setattr(profile, "admin_passkey_configured", lambda: passkey_set)
        monkeypatch.setattr(profile, "verify_admin_passkey", lambda _p: passkey_ok)

        calls = []
        import utils.data_manager as dm

        def fake_delete_all(*, collector_id=None):
            calls.append(collector_id)
            return {
                "requested": 1, "deleted": 1, "cascaded_children": 0, "photos_removed": 0,
                "photos_orphaned": 0, "batches_restored": {}, "tally_failures": [],
                "not_deleted": [], "refused_not_yours": [],
            }

        monkeypatch.setattr(dm, "delete_all_specimen_records", fake_delete_all)
        return calls

    def _arm(self, at, *, passkey=None):
        if passkey is not None:
            at.text_input(key="reset_passkey").set_value(passkey).run()
        at.text_input(key="reset_confirm").set_value("RESET").run()
        return at

    def test_choosing_project_wide_asks_for_the_passkey(self, monkeypatch):
        self._profile(monkeypatch)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()
        at.radio(key="reset_scope").set_value(_ALL).run()

        assert any(t.key == "reset_passkey" for t in at.text_input)

    def test_the_scoped_reset_does_not_ask_for_it(self, monkeypatch):
        """Deleting only what you recorded is an ordinary action, not an administrative one."""
        self._profile(monkeypatch)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()

        assert not any(t.key == "reset_passkey" for t in at.text_input)

    def test_button_stays_disabled_until_the_passkey_is_entered(self, monkeypatch):
        self._profile(monkeypatch)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()
        at.radio(key="reset_scope").set_value(_ALL).run()
        at.text_input(key="reset_confirm").set_value("RESET").run()

        assert at.button(key="reset_go").disabled, "armed on the typed word alone"

        at.text_input(key="reset_passkey").set_value("something").run()
        assert not at.button(key="reset_go").disabled

    def test_a_wrong_passkey_deletes_nothing(self, monkeypatch):
        calls = self._profile(monkeypatch, passkey_ok=False)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()
        at.radio(key="reset_scope").set_value(_ALL).run()
        self._arm(at, passkey="wrong")
        at.button(key="reset_go").click().run()

        assert calls == [], "a rejected passkey still reached the data layer"
        assert any("not correct" in e.value for e in at.error)

    def test_a_correct_passkey_deletes_project_wide(self, monkeypatch):
        calls = self._profile(monkeypatch)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()
        at.radio(key="reset_scope").set_value(_ALL).run()
        self._arm(at, passkey="right")
        at.button(key="reset_go").click().run()

        assert calls == [None], "project-wide delete must pass collector_id=None"

    def test_a_non_admin_is_not_offered_the_project_wide_scope(self, monkeypatch):
        self._profile(monkeypatch, admin=False)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()

        assert _ALL not in at.radio(key="reset_scope").options

    def test_an_unconfigured_passkey_withholds_the_scope_rather_than_prompting(self, monkeypatch):
        """Fails closed: verify_admin_passkey refuses everything when the hash is unset, so
        offering the option would present a control that cannot succeed."""
        self._profile(monkeypatch, passkey_set=False)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()

        assert _ALL not in at.radio(key="reset_scope").options
        assert any("no delete passkey is configured" in i.value.lower() for i in at.info)

    def test_the_passkey_field_is_reachable_from_the_whole_page(self, monkeypatch):
        """Rendering the section directly proves it works, not that anyone can get to it.

        That is the exact gap that hid the previous project-wide control: every test drove
        it in isolation, it passed, and the button was invisible in the running app because
        the code path reaching it returned early. So this one renders render_profile_page()
        itself and looks for the field through the real page.
        """
        self._profile(monkeypatch)

        import components.profile as profile

        # Stub the two things that reach the network — the profile store and the Supabase
        # client — and let the rest of the page run for real. Stubbing the intermediate
        # helpers instead means hand-writing the dicts they return, which drifts from the
        # keys the page actually indexes and fails for reasons that are not the point here.
        monkeypatch.setattr(profile, "load_profile", lambda _uid: None)
        monkeypatch.setattr(profile, "get_supabase_client", lambda: None)
        monkeypatch.setattr(profile, "get_current_user_id", lambda: "me")
        monkeypatch.setattr(profile, "get_current_user_email", lambda: "t@example.com")

        at = AppTest.from_function(_profile_page_app, default_timeout=60)
        at.run()

        assert not at.exception, [str(e) for e in at.exception]
        assert _ALL in at.radio(key="reset_scope").options, "admin scope missing from the page"

        at.radio(key="reset_scope").set_value(_ALL).run()
        assert any(t.key == "reset_passkey" for t in at.text_input)

    def test_a_side_table_alone_is_project_wide_and_needs_the_passkey(self, monkeypatch):
        """bioassay_results and clinical_case_data have no scoped form — ticking either
        clears everyone's, even while the radio still reads "only records I collected"."""
        self._profile(monkeypatch)

        at = AppTest.from_function(_trial_reset_app, default_timeout=30)
        at.run()
        at.checkbox(key="reset_bioassay").set_value(True).run()

        assert any(t.key == "reset_passkey" for t in at.text_input)
