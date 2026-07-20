"""Browser-cookie persistence for the Supabase refresh token.

st.session_state does not survive a full browser reload, so without this a refresh drops
the user back to the login screen — punishing on a phone in the field, where the browser
backgrounds and reloads constantly.

What is stored is ONLY the refresh token, and it buys no access on its own: restore_session
hands it to Supabase, which validates it server-side and issues a fresh session. A revoked
or expired token gets the user nothing. This is deliberately not the old `?session=active`
URL flag, which granted access with no credential check at all.

The cookie is readable by JavaScript (Streamlit cannot set an httpOnly cookie from the
server), which is the same posture supabase-js takes by default. It is written with
SameSite=Lax, and with Secure whenever the page is served over https.

Reading uses st.context.cookies, which sees the cookies the browser sent with the request.
Writing goes through a tiny script in a srcdoc iframe (st.iframe): srcdoc iframes inherit
the parent's origin, so a document.cookie write there lands on the app's own domain.
"""

import streamlit as st

from utils.logging_config import get_logger

logger = get_logger(__name__)

COOKIE_NAME = "vs_refresh_token"

# Mirrors utils/offline_queue's pending field-writes so they survive a full reload /
# idle-reboot, the same way the refresh token does. Holds no credential — just
# queued form payloads the user already entered — so it needs no server validation.
PENDING_QUEUE_COOKIE = "vs_pending_queue"

# A week: long enough that a field worker isn't retyping a password every day, short enough
# that a stolen cookie stops working reasonably soon. Supabase rotates the token on every
# refresh, so an active user's cookie is replaced well before this expires.
MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def read_refresh_token() -> str | None:
    """The refresh token the browser sent with this request, if any."""
    try:
        cookies = st.context.cookies or {}
    except Exception:
        logger.debug("st.context.cookies unavailable", exc_info=True)
        return None
    token = cookies.get(COOKIE_NAME)
    return token or None


def _emit_cookie_script(value: str, max_age: int, name: str = COOKIE_NAME) -> None:
    # json.dumps-style quoting is not enough here: the value is a JWT (dot-separated
    # base64url), so it carries no quotes or semicolons, but escape defensively anyway.
    safe = value.replace("\\", "\\\\").replace('"', '\\"')
    st.iframe(
        f"""
        <script>
          (function () {{
            // This script runs inside a srcdoc iframe, whose own location.protocol is
            // "about:" — never the page's scheme. Checking it here therefore never
            // matched 'https:', so Secure was silently left off on every deployment.
            // Read the host page's scheme instead; the iframe sandbox grants
            // allow-same-origin, so the parent is reachable.
            var proto = '';
            try {{ proto = window.parent.location.protocol; }} catch (e) {{ proto = ''; }}
            var secure = proto === 'https:' ? '; Secure' : '';
            document.cookie = "{name}=" + "{safe}"
              + "; Path=/; Max-Age={max_age}; SameSite=Lax" + secure;
          }})();
        </script>
        """,
        # The iframe only runs a script and shows nothing, but st.iframe rejects height=0
        # (unlike the old components.html) — 1px is the smallest it allows and is invisible.
        height=1,
    )


def write_refresh_token(token: str) -> None:
    """Persist the refresh token so the next page load can restore the session."""
    if not token:
        return
    _emit_cookie_script(token, MAX_AGE_SECONDS)


def clear_refresh_token() -> None:
    """Drop the cookie — called on sign-out and whenever a token is rejected."""
    _emit_cookie_script("", 0)


def sync_refresh_cookie(token: str | None) -> None:
    """Make the cookie match the session's current refresh token.

    Called once per run. Only emits the script when the value actually changed, so a
    Streamlit rerun doesn't inject a fresh iframe on every interaction — and so a
    sign-out (token gone) clears the cookie rather than leaving a stale one behind.
    """
    last_written = st.session_state.get("_refresh_cookie_written")
    if token:
        if token != last_written:
            write_refresh_token(token)
            st.session_state["_refresh_cookie_written"] = token
    elif last_written:
        clear_refresh_token()
        st.session_state["_refresh_cookie_written"] = None


# --- Offline pending-queue cookie (mirrors utils/offline_queue) --------------
def read_pending_queue() -> str | None:
    """The encoded pending-write queue the browser sent with this request, if any."""
    try:
        cookies = st.context.cookies or {}
    except Exception:
        logger.debug("st.context.cookies unavailable for pending queue", exc_info=True)
        return None
    return cookies.get(PENDING_QUEUE_COOKIE) or None


def write_pending_queue(value: str) -> None:
    """Persist (or clear, when value is empty) the encoded pending-write queue.

    Only emits the cookie script when the value actually changed, so a rerun that
    didn't touch the queue doesn't inject a fresh iframe every interaction.
    """
    last = st.session_state.get("_pending_queue_written")
    if value == last:
        return
    _emit_cookie_script(value, MAX_AGE_SECONDS if value else 0, name=PENDING_QUEUE_COOKIE)
    st.session_state["_pending_queue_written"] = value
