# =========================================================================
# AUTHENTICATION & DATABASE CORE UTILITIES (utils/auth.py)
# =========================================================================
import streamlit as st
from datetime import datetime
from utils.config import (
    SUPABASE_CLIENT,
    SUPABASE_ENABLED,
    SUPABASE_SERVICE_CLIENT,
    ADMIN_USERNAME,
    ADMIN_EMAIL,
    ADMIN_PASSWORD
)

def get_supabase_client():
    """
    Returns the shared Supabase client, re-attaching the current user's
    authenticated session token on EVERY call. Streamlit reruns can leave
    the shared client in an anon state, so we re-apply the token — which
    lives in st.session_state (persistent across reruns) — each time the
    client is fetched. This is what ensures every DB/storage request
    actually carries the logged-in user's credentials.
    """
    if not SUPABASE_ENABLED:
        return None
    client = SUPABASE_CLIENT
    token = st.session_state.get("sb_access_token")
    if token:
        try:
            client.postgrest.auth(token)
            client.storage._client.headers["Authorization"] = f"Bearer {token}"
        except Exception:
            pass
    return client


def get_supabase_service_client():
    return SUPABASE_SERVICE_CLIENT


def supabase_user():
    client = get_supabase_client()
    if client is None:
        return None
    try:
        user_response = client.auth.get_user()
        return getattr(user_response, "user", None) or user_response
    except Exception:
        return None


def set_authenticated(user, provider="supabase"):
    st.session_state["authenticated"] = True
    st.session_state["guest_explorer"] = False
    st.session_state["auth_provider"] = provider
    if isinstance(user, dict):
        st.session_state["auth_user_email"] = user.get("email")
        st.session_state["auth_user_id"] = user.get("id")
        st.session_state["auth_user_name"] = user.get("user_metadata", {}).get("full_name") or user.get("full_name")
    else:
        st.session_state["auth_user_email"] = getattr(user, "email", None)
        st.session_state["auth_user_id"] = getattr(user, "id", None)
        metadata = getattr(user, "user_metadata", None) or {}
        st.session_state["auth_user_name"] = metadata.get("full_name")
    st.session_state["login_time"] = datetime.now()


def sign_in_user(email: str, password: str):
    """
    Signs in against Supabase and stores the resulting session tokens in
    st.session_state so they survive Streamlit reruns. get_supabase_client()
    re-applies them on every call, keeping all DB/storage requests
    authenticated as this user.
    """
    client = SUPABASE_CLIENT if SUPABASE_ENABLED else None
    if client:
        try:
            auth_response = client.auth.sign_in_with_password({"email": email, "password": password})
        except Exception as e:
            st.error(f"Sign-in failed: {e}")
            return None

        session = getattr(auth_response, "session", None)
        if session:
            try:
                client.auth.set_session(session.access_token, session.refresh_token)
            except Exception:
                pass
            # Persist tokens in session_state so they survive Streamlit reruns
            st.session_state["sb_access_token"] = session.access_token
            st.session_state["sb_refresh_token"] = session.refresh_token

        return auth_response

    # Local fallback login is only available when an admin password has been
    # configured via secrets/env. Without it, there is no offline bypass.
    if (
        ADMIN_PASSWORD
        and password == ADMIN_PASSWORD
        and email.strip().lower() in (ADMIN_USERNAME.lower(), ADMIN_EMAIL.lower())
    ):
        return {"user": {"email": ADMIN_EMAIL, "id": "local-admin", "user_metadata": {"full_name": "Administrator"}}}
    return None


def sign_up_user(email: str, password: str, full_name: str):
    client = SUPABASE_CLIENT if SUPABASE_ENABLED else None
    if client:
        return client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}},
        })
    return None


def _clear_auth_state():
    """Resets all auth-related session_state to a clean logged-out state."""
    st.session_state["authenticated"] = False
    st.session_state["guest_explorer"] = False
    st.session_state["auth_provider"] = "local"
    st.session_state["auth_user_email"] = None
    st.session_state["auth_user_id"] = None
    st.session_state["auth_user_name"] = None
    st.session_state["sb_access_token"] = None
    st.session_state["sb_refresh_token"] = None


def restore_session() -> bool:
    """
    Re-establishes an authenticated session from tokens previously persisted
    in st.session_state — but ONLY after verifying them against Supabase.

    This replaces the old `?session=active` URL flag, which set
    authenticated=True with no credential check at all, letting anyone in by
    editing the address bar. Here, access is granted only if Supabase
    confirms the refresh token still maps to a valid user: an expired access
    token is transparently refreshed, and a revoked/invalid token forces a
    clean logged-out state.

    Note: st.session_state does not survive a full browser reload, so the
    tokens it holds are per-session. This restores auth across Streamlit
    reruns within a session; it does not (by design) grant access from a URL
    alone. Cross-reload persistence would require storing the refresh token
    in a cookie/localStorage, which is a separate, opt-in change.

    Returns True if a valid session was restored.
    """
    if not SUPABASE_ENABLED:
        return False

    access_token = st.session_state.get("sb_access_token")
    refresh_token = st.session_state.get("sb_refresh_token")
    if not access_token or not refresh_token:
        return False

    try:
        auth_response = SUPABASE_CLIENT.auth.set_session(access_token, refresh_token)
    except Exception:
        # Refresh token invalid, expired, or revoked — deny and reset.
        _clear_auth_state()
        return False

    user = getattr(auth_response, "user", None)
    if user is None:
        _clear_auth_state()
        return False

    # Persist any rotated tokens so the next validation uses the latest pair.
    session = getattr(auth_response, "session", None)
    if session is not None:
        st.session_state["sb_access_token"] = getattr(session, "access_token", access_token)
        st.session_state["sb_refresh_token"] = getattr(session, "refresh_token", refresh_token)

    set_authenticated(user, provider="supabase")
    return True


def sign_out_user():
    client = SUPABASE_CLIENT if SUPABASE_ENABLED else None
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    _clear_auth_state()
    st.session_state["current_page"] = "dashboard"

    if "session" in st.query_params:
        del st.query_params["session"]


def send_password_reset_email(email: str):
    """Requests a password reset link from Supabase for the specified email."""
    client = get_supabase_client()
    if client:
        return client.auth.reset_password_for_email(email)
    return None


def get_current_user_email() -> str:
    """Returns the current logged-in user's email address from session state."""
    return st.session_state.get("auth_user_email", "")


def get_current_user_id() -> str:
    """Returns the unique identifier of the logged-in investigator."""
    return st.session_state.get("auth_user_id", "")


def get_display_name() -> str:
    """Returns the active profile name to display in headers and banners."""
    return st.session_state.get("auth_user_name", "")