"""A browser reload must not log the user out — but the cookie must never be trusted.

st.session_state does not survive a full page reload, so before this the user was dumped
back at the login screen on every refresh. The cookie holds a Supabase refresh token and
nothing else: restore_session hands it to Supabase, which validates it server-side and
issues a fresh session. A revoked or expired token must get the caller precisely nowhere.

This is the security-critical property. The old `?session=active` URL flag set
authenticated=True with no credential check at all; the cookie must not become a
re-run of that mistake.
"""
import base64
import json
import socket
import time

import streamlit as st

import utils.auth as auth


def _make_jwt(exp_epoch: int) -> str:
    """A minimal unsigned JWT carrying only an `exp` claim — enough for _jwt_exp."""
    def _seg(obj):
        raw = json.dumps(obj).encode()
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    return f"{_seg({'alg': 'none'})}.{_seg({'exp': exp_epoch})}.sig"


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


class TestClientDoesNotRotateTokensBehindOurBack:
    """The shared client must never refresh a session on its own.

    supabase-py defaults to auto_refresh_token=True, which arms a background timer that
    refreshes whatever session the client last saved. Supabase rotates the refresh token
    on every refresh and revokes the old one — including the copy in the user's cookie —
    handing the replacement only to the client's own memory, which nothing reads. About an
    hour after login the cookie's token is silently dead and the next reload dumps the
    field user back at the login screen. Refreshing is restore_session()'s job.
    """

    def test_anon_client_is_built_with_auto_refresh_disabled(self, monkeypatch):
        import utils.config as config

        captured = {}

        def fake_create_client(url, key, options=None):
            captured["options"] = options
            return object()

        monkeypatch.setattr(config, "create_client", fake_create_client)
        monkeypatch.setattr(config, "SUPABASE_ENABLED", True)
        monkeypatch.setattr(config, "SUPABASE_URL", "https://example.supabase.co")
        monkeypatch.setattr(config, "SUPABASE_ANON_KEY", "anon-key")
        monkeypatch.setattr(config, "_supabase_client", None)

        config.get_base_supabase_client()

        assert captured["options"] is not None, "client must be built with explicit options"
        assert captured["options"].auto_refresh_token is False


class TestAccessTokenRefreshBeforeExpiry:
    """A long shift without a reload must not start failing saves on an expired JWT.

    Supabase access tokens live ~1 hour and get_supabase_client() re-applies whatever is
    in session_state on every call. If that token is stale, saves fail. _current_access_token
    renews it from the refresh token before it expires and keeps the reload cookie in step.
    """

    def test_valid_token_is_used_unchanged(self, monkeypatch):
        st.session_state.clear()
        # Expires in an hour — nowhere near the refresh window, so no refresh call is made.
        st.session_state["sb_access_token"] = _make_jwt(int(time.time()) + 3600)
        st.session_state["sb_refresh_token"] = "refresh-1"

        def boom():
            raise AssertionError("must not build a client to refresh a still-valid token")

        monkeypatch.setattr(auth, "get_base_supabase_client", boom)

        assert auth._current_access_token() == st.session_state["sb_access_token"]
        st.session_state.clear()

    def test_expiring_token_is_refreshed_and_persisted(self, monkeypatch):
        st.session_state.clear()
        # Already past expiry: must be renewed before use.
        st.session_state["sb_access_token"] = _make_jwt(int(time.time()) - 10)
        st.session_state["sb_refresh_token"] = "old-refresh"

        fake = FakeAuth(user=_user())
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(fake))
        synced = []
        monkeypatch.setattr(auth, "sync_refresh_cookie", lambda t: synced.append(t))

        token = auth._current_access_token()

        assert fake.refreshed_with == "old-refresh"          # traded the refresh token
        assert token == "new-access"                          # returns the fresh access token
        assert st.session_state["sb_access_token"] == "new-access"
        assert st.session_state["sb_refresh_token"] == "rotated-refresh"
        assert synced == ["rotated-refresh"]                  # cookie kept in step for reloads
        st.session_state.clear()

    def test_failed_refresh_keeps_the_old_token_rather_than_logging_out(self, monkeypatch):
        st.session_state.clear()
        stale = _make_jwt(int(time.time()) - 10)
        st.session_state["sb_access_token"] = stale
        st.session_state["sb_refresh_token"] = "old-refresh"

        fake = FakeAuth(raises=True)  # refresh round-trip fails (e.g. transient network)
        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(fake))

        # Returns the existing token instead of tearing down the session mid-run.
        assert auth._current_access_token() == stale
        assert st.session_state.get("authenticated") is not True  # untouched, not cleared
        st.session_state.clear()


class TestNetworkErrorIsNotAWrongPassword:
    def test_getaddrinfo_failure_is_detected(self):
        wrapped = ConnectionError("connection failed")
        wrapped.__cause__ = socket.gaierror(11001, "getaddrinfo failed")
        assert auth._is_network_error(wrapped) is True

    def test_plain_value_error_is_not_a_network_error(self):
        assert auth._is_network_error(ValueError("Invalid login credentials")) is False

    def test_sign_in_raises_connection_error_on_network_failure(self, monkeypatch):
        st.session_state.clear()

        class Boom:
            def sign_in_with_password(self, _creds):
                raise OSError(11001, "getaddrinfo failed")

        monkeypatch.setattr(auth, "get_base_supabase_client", lambda: FakeClient(Boom()))

        try:
            auth.sign_in_user("a@b.ng", "pw")
        except ConnectionError:
            pass
        else:
            raise AssertionError("network failure must raise ConnectionError, not return None")
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
