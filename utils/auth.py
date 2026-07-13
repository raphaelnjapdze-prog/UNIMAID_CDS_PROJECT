# =========================================================================
# AUTHENTICATION & DATABASE CORE UTILITIES (utils/auth.py)
# =========================================================================
from datetime import datetime

import streamlit as st

from utils.config import (
    ADMIN_EMAIL,
    ADMIN_PASSWORD,
    ADMIN_USERNAME,
    get_base_supabase_client,
    get_service_supabase_client,
)
from utils.logging_config import get_logger
from utils.session_cookie import read_refresh_token

logger = get_logger(__name__)

def get_supabase_client():
    """
    Returns the shared Supabase client, re-attaching the current user's
    authenticated session token on EVERY call. Streamlit reruns can leave
    the shared client in an anon state, so we re-apply the token — which
    lives in st.session_state (persistent across reruns) — each time the
    client is fetched. This is what ensures every DB/storage request
    actually carries the logged-in user's credentials.
    """
    client = get_base_supabase_client()
    if client is None:
        return None
    token = st.session_state.get("sb_access_token")
    if token:
        try:
            client.postgrest.auth(token)
            client.storage._client.headers["Authorization"] = f"Bearer {token}"
        except Exception:
            logger.debug("Failed to re-apply auth token to Supabase client", exc_info=True)
    return client


def get_supabase_service_client():
    return get_service_supabase_client()


def supabase_user():
    client = get_supabase_client()
    if client is None:
        return None
    try:
        user_response = client.auth.get_user()
        return getattr(user_response, "user", None) or user_response
    except Exception:
        logger.debug("supabase_user() lookup failed", exc_info=True)
        return None


def set_authenticated(user, provider="supabase"):
    st.session_state["authenticated"] = True
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
    client = get_base_supabase_client()
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
                logger.warning("Could not set Supabase session after sign-in", exc_info=True)
            # Persist tokens in session_state so they survive Streamlit reruns
            st.session_state["sb_access_token"] = session.access_token
            st.session_state["sb_refresh_token"] = session.refresh_token

        return auth_response

    # Local fallback login is only available when an admin password has been
    # configured via secrets/env. Without it, there is no offline bypass.
    #
    # ADMIN_USERNAME/ADMIN_EMAIL come from secrets and may be unset. Calling .lower() on
    # an unset one raised AttributeError mid-login; worse, coercing it to "" would let a
    # submitted empty email match an admin identity that was never configured. Drop the
    # blanks so an unconfigured identity matches nothing at all.
    admin_identities = {
        identity.strip().lower()
        for identity in (ADMIN_USERNAME, ADMIN_EMAIL)
        if identity and identity.strip()
    }
    if (
        ADMIN_PASSWORD
        and password == ADMIN_PASSWORD
        and email.strip().lower() in admin_identities
    ):
        return {"user": {"email": ADMIN_EMAIL, "id": "local-admin", "user_metadata": {"full_name": "Administrator"}}}
    return None


def sign_up_user(email: str, password: str, full_name: str):
    client = get_base_supabase_client()
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
    st.session_state["auth_provider"] = "local"
    st.session_state["auth_user_email"] = None
    st.session_state["auth_user_id"] = None
    st.session_state["auth_user_name"] = None
    st.session_state["sb_access_token"] = None
    st.session_state["sb_refresh_token"] = None


def _adopt_session(auth_response, fallback_access: str = "", fallback_refresh: str = "") -> bool:
    """Take a validated Supabase auth response and mark the user signed in.

    Returns False (and resets to a clean logged-out state) if Supabase did not hand back
    a user — a refresh token that no longer maps to one buys nothing.
    """
    user = getattr(auth_response, "user", None)
    if user is None:
        _clear_auth_state()
        return False

    # Persist any rotated tokens so the next validation uses the latest pair.
    session = getattr(auth_response, "session", None)
    if session is not None:
        st.session_state["sb_access_token"] = getattr(session, "access_token", fallback_access)
        st.session_state["sb_refresh_token"] = getattr(session, "refresh_token", fallback_refresh)

    set_authenticated(user, provider="supabase")
    return True


def restore_session() -> bool:
    """
    Re-establishes an authenticated session — but ONLY after verifying the stored tokens
    against Supabase.

    Two sources, in order:

    1. st.session_state, which survives Streamlit reruns within a page session.
    2. The refresh-token cookie, which survives a full browser reload — session_state does
       not, so without this a refresh dumps the user back to the login screen.

    Neither is trusted on its own. The cookie holds a refresh token and nothing else, and
    it grants no access by itself: it is handed to Supabase, which validates it
    server-side and issues a fresh session. A revoked or expired token gets the caller
    nowhere, and the cookie is dropped. This is emphatically not the old `?session=active`
    URL flag, which set authenticated=True with no credential check at all.

    Returns True if a valid session was restored.
    """
    client = get_base_supabase_client()
    if client is None:
        return False

    access_token = st.session_state.get("sb_access_token")
    refresh_token = st.session_state.get("sb_refresh_token")

    if access_token and refresh_token:
        try:
            auth_response = client.auth.set_session(access_token, refresh_token)
        except Exception:
            # Refresh token invalid, expired, or revoked — deny and reset.
            logger.debug("Stored session tokens rejected by Supabase", exc_info=True)
            _clear_auth_state()
            return False
        return _adopt_session(auth_response, access_token, refresh_token)

    # No tokens in session_state: this is what a browser reload looks like. Fall back to
    # the cookie and let Supabase decide whether it is still good.
    cookie_token = read_refresh_token()
    if not cookie_token:
        return False

    try:
        auth_response = client.auth.refresh_session(cookie_token)
    except Exception:
        logger.debug("Refresh token from cookie rejected by Supabase", exc_info=True)
        _clear_auth_state()  # also drops the cookie, via sync_refresh_cookie next run
        return False

    return _adopt_session(auth_response, "", cookie_token)


def sign_out_user():
    client = get_base_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            logger.debug("Supabase sign_out() call failed; clearing local state anyway", exc_info=True)
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


def get_collector_label() -> str:
    """Human-readable name for whoever is signed in, for stamping onto specimen records.

    collector_id holds the auth UUID, which is what queries join on but is unreadable in
    an exported CSV or a printed report. This is the name that goes beside it. Falls back
    through name -> email -> id, since a Supabase account created without full_name in its
    user_metadata has no display name at all.
    """
    return (
        st.session_state.get("auth_user_name")
        or st.session_state.get("auth_user_email")
        or st.session_state.get("auth_user_id")
        or ""
    )
