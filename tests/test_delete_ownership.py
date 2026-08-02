"""Deletion is scoped to whoever recorded the entry.

Before this, `sql/add_delete_policies.sql` granted DELETE to every authenticated user with
`using (true)`: any signed-in account could delete anyone's field data. The UI never
offered it, but the UI is not what stops it — the anon key plus a user's own JWT is enough
to call the REST API directly.

The rule now:

    you may delete a row if you recorded it, or if you are a registered admin.

The database enforces it in the DELETE policy (sql/add_ownership_delete_policies.sql).
What is tested here is the application half, which exists for a different reason: RLS
refuses by matching zero rows *without raising*, which arrives looking exactly like
"already deleted". Refusing in Python first is what lets the refusal be explained instead
of reported as a silent partial success.
"""
import pytest

from tests.test_deletion import FakeSupabase, _batch, _child
from utils import auth
from utils import data_manager as dm


@pytest.fixture
def ledger(monkeypatch):
    """An in-memory ledger plus an identity for the caller."""
    def build(rows, *, user="me", admin=False):
        client = FakeSupabase({"specimen_records": rows})
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm, "get_current_user_id", lambda: user)
        monkeypatch.setattr(dm, "is_current_user_admin", lambda: admin)
        monkeypatch.setattr(dm, "clear_specimen_records_cache", lambda: None)
        return client
    return build


class TestOwnsRow:
    def test_the_collector_owns_their_row(self):
        assert dm.owns_row(_batch(collector="me"), "me")

    def test_someone_else_does_not(self):
        assert not dm.owns_row(_batch(collector="them"), "me")

    def test_whitespace_does_not_change_the_answer(self):
        assert dm.owns_row({"collector_id": " me "}, "me")

    def test_an_unattributed_legacy_row_belongs_to_nobody(self):
        """Their author was never recorded and cannot be recovered, so no one can claim
        them — which leaves them admin-only to delete. That is the honest answer."""
        row = {"collector_id": dm.UNATTRIBUTED_LEGACY}
        assert not dm.owns_row(row, "me")
        assert not dm.owns_row(row, "someone-else")

    def test_no_signed_in_user_owns_nothing(self):
        assert not dm.owns_row(_batch(collector="me"), "")

    def test_junk_is_not_ownership(self):
        assert not dm.owns_row(None, "me")
        assert not dm.owns_row("not a row", "me")


class TestAUserCannotDeleteAnothersEntries:
    def test_another_investigators_entry_is_refused(self, ledger):
        client = ledger([_batch("theirs", collector="someone-else")])

        assert dm.delete_specimen_records(["theirs"]) is None
        assert client.ids() == ["theirs"], "the row must survive"

    def test_a_mixed_selection_deletes_only_your_own(self, ledger):
        client = ledger([
            _batch("mine", collector="me"),
            _batch("theirs", collector="someone-else"),
        ])

        summary = dm.delete_specimen_records(["mine", "theirs"])

        assert summary["deleted"] == 1
        assert client.ids() == ["theirs"]

    def test_the_refusal_is_reported_not_swallowed(self, ledger):
        """A partial delete that reports a clean sweep is the failure this whole module
        exists to refuse. The caller has to be able to say which part was declined."""
        ledger([
            _batch("mine", collector="me"),
            _batch("theirs", collector="someone-else"),
        ])

        summary = dm.delete_specimen_records(["mine", "theirs"])

        assert summary["refused_not_yours"] == ["theirs"]

    def test_nothing_of_yours_selected_deletes_nothing(self, ledger):
        client = ledger([_batch("theirs", collector="someone-else")])

        dm.delete_specimen_records(["theirs"])

        assert client.ids() == ["theirs"]


class TestAnAdminCanDeleteAnyEntry:
    def test_an_admin_deletes_another_investigators_entry(self, ledger):
        client = ledger([_batch("theirs", collector="someone-else")], admin=True)

        summary = dm.delete_specimen_records(["theirs"])

        assert summary["deleted"] == 1
        assert client.ids() == []

    def test_an_admin_refuses_nothing(self, ledger):
        ledger([_batch("theirs", collector="someone-else")], admin=True)

        summary = dm.delete_specimen_records(["theirs"])

        assert summary["refused_not_yours"] == []


class TestCascadeStaysWithinTheOwner:
    def test_deleting_your_batch_takes_your_children(self, ledger):
        """Children inherit the batch's collector_id, so the cascade does not cross an
        ownership line — but the batch is what was authorised, so check it holds."""
        client = ledger([
            _batch("mine", collector="me", vialed={"Anopheles": 2}),
            _child("v1", parent="mine", collector="me"),
            _child("v2", parent="mine", collector="me"),
        ])

        summary = dm.delete_specimen_records(["mine"])

        assert client.ids() == []
        assert summary["cascaded_children"] == 2

    def test_another_investigators_batch_takes_no_children_with_it(self, ledger):
        client = ledger([
            _batch("theirs", collector="someone-else", vialed={"Anopheles": 1}),
            _child("v1", parent="theirs", collector="someone-else"),
        ])

        assert dm.delete_specimen_records(["theirs"]) is None
        assert client.ids() == ["theirs", "v1"], "neither the batch nor its child may go"


class TestBulkDeleteIsAdminOnly:
    def test_a_non_admin_cannot_delete_everything(self, ledger):
        client = ledger([
            _batch("mine", collector="me"),
            _batch("theirs", collector="someone-else"),
        ])

        assert dm.delete_all_specimen_records() is None
        assert client.ids() == ["mine", "theirs"], "not even the caller's own rows go"

    def test_an_admin_can(self, ledger):
        client = ledger([
            _batch("mine", collector="me"),
            _batch("theirs", collector="someone-else"),
        ], admin=True)

        dm.delete_all_specimen_records()

        assert client.ids() == []

    def test_a_non_admin_may_still_clear_their_own(self, ledger):
        """Scoped to yourself is not the admin action — it is the ordinary one."""
        client = ledger([
            _batch("mine", collector="me"),
            _batch("theirs", collector="someone-else"),
        ])

        summary = dm.delete_all_specimen_records(collector_id="me")

        assert summary["deleted"] == 1
        assert client.ids() == ["theirs"]

    def test_a_non_admin_cannot_scope_the_bulk_delete_to_someone_else(self, ledger):
        """Passing another investigator's id must not become a way around the rule: the
        per-row ownership check still runs on everything the scope selected."""
        client = ledger([_batch("theirs", collector="someone-else")])

        assert dm.delete_all_specimen_records(collector_id="someone-else") is None
        assert client.ids() == ["theirs"]


class TestSideTableResetsAreAdminOnly:
    def test_a_non_admin_cannot_clear_bioassay_results(self, monkeypatch):
        client = FakeSupabase({"bioassay_results": [{"id": 1}]})
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm, "is_current_user_admin", lambda: False)

        assert dm.delete_all_bioassay_results() is None
        assert len(client.tables["bioassay_results"]) == 1

    def test_a_non_admin_cannot_clear_clinical_case_data(self, monkeypatch):
        client = FakeSupabase({"clinical_case_data": [{"id": "a"}]})
        monkeypatch.setattr(dm, "get_supabase_client", lambda: client)
        monkeypatch.setattr(dm, "is_current_user_admin", lambda: False)

        assert dm.delete_all_clinical_case_data() is None
        assert len(client.tables["clinical_case_data"]) == 1


class TestTheDeletePasskey:
    """The second gate in front of the admin bulk delete. Not the security boundary — a
    registered admin could delete through the API without ever seeing this prompt — but it
    is what stops an unattended admin session or a misclick emptying the project."""

    def test_the_right_passkey_verifies(self, monkeypatch):
        digest = auth.hash_admin_password("correct horse battery staple", iterations=1)
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH", digest)

        assert auth.verify_admin_passkey("correct horse battery staple")

    def test_a_wrong_passkey_does_not(self, monkeypatch):
        digest = auth.hash_admin_password("correct horse battery staple", iterations=1)
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH", digest)

        assert not auth.verify_admin_passkey("wrong")

    def test_an_unconfigured_passkey_refuses_everything(self, monkeypatch):
        """Fails closed. A project-wide wipe that works before anyone has chosen a passkey
        is the failure mode worth designing against."""
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH", "")

        assert not auth.verify_admin_passkey("anything")
        assert not auth.verify_admin_passkey("")
        assert not auth.admin_passkey_configured()

    def test_an_empty_entry_is_refused_even_when_configured(self, monkeypatch):
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH",
                            auth.hash_admin_password("a passkey", iterations=1))

        assert not auth.verify_admin_passkey("")

    def test_a_malformed_hash_authenticates_nobody(self, monkeypatch):
        """A misconfigured secret must deny, not accidentally admit."""
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH", "not$a$valid$digest")

        assert not auth.verify_admin_passkey("anything")

    def test_it_is_a_separate_credential_from_the_login_password(self, monkeypatch):
        """Sharing one secret between signing in and wiping the project would mean anyone
        who can log in as the admin can also empty it, which is the point of the gate."""
        monkeypatch.setattr(auth, "ADMIN_PASSWORD_HASH",
                            auth.hash_admin_password("login-password", iterations=1))
        monkeypatch.setattr(auth, "ADMIN_DELETE_PASSKEY_HASH",
                            auth.hash_admin_password("delete-passkey", iterations=1))

        assert not auth.verify_admin_passkey("login-password")
        assert auth.verify_admin_passkey("delete-passkey")
