"""A browser reload must not log the user out — but the cookie must never be trusted.

st.session_state does not survive a full page reload, so before this the user was dumped
back at the login screen on every refresh. The cookie holds a Supabase refresh token and
nothing else: restore_session hands it to Supabase, which validates it server-side and
issues a fresh session. A revoked or expired token must get the caller precisely nowhere.

This is the security-critical property. The old `?session=active` URL flag set
authenticated=True with no credential check at all; the cookie must not become a
re-run of that mistake.
"""
import streamlit as st

import utils.auth as auth


class FakeAuth:
    def __init__(self, user=None, raises=False):
        self.user, self.raises = user, raises
        self.refreshed_with = None

    def refresh_session(self, refresh_token=None):
        self.refreshed_with = refresh_token
        if self.raises:
            raise RuntimeError("Invalid refresh token")
        session = type("S", (), {"access_token": "new-access", "refresh_token": "rotated-refresh"})()
        return type("R", (), {"user": self.user, "session": session})()

    def set_session(self, _access, _refresh):
        raise AssertionError("set_session must not be used when session_state is empty")


class FakeClient:
    def __init__(self, auth_impl):
        self.auth = auth_impl


def _user():
    return {"id": "user-uuid-1", "email": "a.musa@unimaid.edu.ng", "user_metadata": {"full_name": "A. Musa"}}


class TestReloadRestoresTheSession:
    def test_cookie_token_is_exchanged_for_a_fresh_session(self, monkeypatch):
        st.session_state.clear()  # exactly what a browser reload leaves behind
        fake = FakeAuth(user=_user())
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(fake))
        monkeypatch.setattr(auth, "read_refresh_token", lambda: "cookie-refresh-token")

        assert auth.restore_session() is True

        # The token was validated by Supabase, not merely believed.
        assert fake.refreshed_with == "cookie-refresh-token"
        assert st.session_state["authenticated"] is True
        assert st.session_state["auth_user_id"] == "user-uuid-1"
        # Rotated tokens are kept, so the next validation uses the current pair.
        assert st.session_state["sb_refresh_token"] == "rotated-refresh"
        st.session_state.clear()

    def test_rejected_cookie_grants_nothing(self, monkeypatch):
        st.session_state.clear()
        fake = FakeAuth(raises=True)  # revoked / expired / forged
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(fake))
        monkeypatch.setattr(auth, "read_refresh_token", lambda: "stolen-or-stale-token")

        assert auth.restore_session() is False
        assert st.session_state["authenticated"] is False
        st.session_state.clear()

    def test_cookie_that_maps_to_no_user_grants_nothing(self, monkeypatch):
        st.session_state.clear()
        fake = FakeAuth(user=None)  # Supabase answered, but with no user
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(fake))
        monkeypatch.setattr(auth, "read_refresh_token", lambda: "token-for-deleted-user")

        assert auth.restore_session() is False
        assert st.session_state["authenticated"] is False
        st.session_state.clear()

    def test_no_cookie_no_session(self, monkeypatch):
        st.session_state.clear()
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(FakeAuth()))
        monkeypatch.setattr(auth, "read_refresh_token", lambda: None)

        # Nothing to validate: it returns early without ever marking anyone authenticated.
        assert auth.restore_session() is False
        assert st.session_state.get("authenticated") is not True
        st.session_state.clear()


class TestCookieTracksTheSession:
    def test_cookie_is_written_once_per_token_not_once_per_rerun(self, monkeypatch):
        import utils.session_cookie as sc

        writes = []
        monkeypatch.setattr(sc, "write_refresh_token", lambda t: writes.append(t))
        monkeypatch.setattr(sc, "clear_refresh_token", lambda: writes.append(None))
        st.session_state.clear()

        sc.sync_refresh_cookie("token-a")
        sc.sync_refresh_cookie("token-a")   # a rerun, same token — must not re-emit
        sc.sync_refresh_cookie("token-b")   # rotated — must be written

        assert writes == ["token-a", "token-b"]
        st.session_state.clear()

    def test_sign_out_clears_the_cookie(self, monkeypatch):
        import utils.session_cookie as sc

        writes = []
        monkeypatch.setattr(sc, "write_refresh_token", lambda t: writes.append(t))
        monkeypatch.setattr(sc, "clear_refresh_token", lambda: writes.append("CLEARED"))
        st.session_state.clear()

        sc.sync_refresh_cookie("token-a")
        sc.sync_refresh_cookie(None)  # signed out: the token is gone from session_state

        # A stale cookie left behind would resurrect the session on the next reload.
        assert writes == ["token-a", "CLEARED"]
        st.session_state.clear()
