# =========================================================================
# LOGIN VIEW (components/login.py)
#
# Deliberately restrained: this page is the first thing a ministry officer,
# funder, or field entomologist sees, so it states plainly what the system is
# and what it does not claim. No stock photography, no sci-fi copy, and no
# capability the app does not actually have.
# =========================================================================
import streamlit as st

from utils.auth import send_password_reset_email, set_authenticated, sign_in_user, sign_up_user
from utils.config import SUPABASE_ENABLED

# Matches utils/theme.py — deep ocean blue for authority, sky for accents.
_INK = "#0C4A6E"
_ACCENT = "#0EA5E9"


def _inject_styles():
    st.markdown(
        f"""
        <style>
        .login-brand {{
            background: linear-gradient(160deg, {_INK} 0%, #082F49 100%);
            border-radius: 10px;
            padding: 38px 34px;
            color: #E2F2FB;
            height: 100%;
        }}
        .login-brand h1 {{
            font-size: 30px;
            line-height: 1.2;
            font-weight: 800;
            color: #FFFFFF;
            margin: 0 0 6px 0;
            letter-spacing: -0.01em;
        }}
        .login-brand .eyebrow {{
            font-size: 11px;
            font-weight: 600;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: {_ACCENT};
            margin-bottom: 18px;
        }}
        .login-brand .lede {{
            font-size: 15px;
            line-height: 1.6;
            color: #BAE0F5;
            margin: 0 0 26px 0;
        }}
        .login-brand .cap {{
            display: flex;
            gap: 12px;
            align-items: flex-start;
            padding: 11px 0;
            border-top: 1px solid rgba(255,255,255,0.10);
        }}
        .login-brand .cap-title {{
            font-size: 13.5px;
            font-weight: 600;
            color: #FFFFFF;
            margin: 0;
        }}
        .login-brand .cap-sub {{
            font-size: 12.5px;
            color: #93C5E8;
            margin: 2px 0 0 0;
            line-height: 1.45;
        }}
        .login-brand .dot {{
            width: 7px; height: 7px;
            border-radius: 50%;
            background: {_ACCENT};
            margin-top: 7px;
            flex-shrink: 0;
        }}
        .login-brand .disclaimer {{
            margin-top: 26px;
            padding: 12px 14px;
            border-left: 2px solid {_ACCENT};
            background: rgba(255,255,255,0.04);
            font-size: 12px;
            line-height: 1.5;
            color: #BAE0F5;
        }}
        .login-foot {{
            text-align: center;
            font-size: 11.5px;
            color: #64748B;
            margin-top: 22px;
            padding-top: 14px;
            border-top: 1px solid #E2E8F0;
        }}
        /* Honeypot: present in the DOM for bots, never shown to a person.
           Targeted by Streamlit's st-key-<key> class on the element container. Wrapping
           the widget in a styled <div> via st.markdown does NOT work — Streamlit renders
           each element in its own container and closes the stray div, so the field stayed
           visible and a real user who typed in it was rejected as a bot. */
        .st-key-signin_verification_hp,
        .st-key-register_verification_hp {{
            display: none !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_brand_panel():
    """The system, stated plainly. Every claim here is one the app can back up."""
    st.markdown(
        """
        <div class="login-brand">
          <div class="eyebrow">Vector Surveillance Platform</div>
          <h1>Vector Sentinel Engine</h1>
          <p class="lede">
            Malaria vector surveillance for endemic regions — field collection,
            specimen identification, insecticide-resistance bioassays, and
            clinical-case correlation, held in one auditable record.
          </p>

          <div class="cap">
            <div class="dot"></div>
            <div>
              <p class="cap-title">Specimen-level ledger</p>
              <p class="cap-sub">Every mosquito traceable from the trap to its PCR result, by barcode.</p>
            </div>
          </div>
          <div class="cap">
            <div class="dot"></div>
            <div>
              <p class="cap-title">Resistance monitoring</p>
              <p class="cap-sub">Bioassay mortality scored against WHO susceptibility thresholds.</p>
            </div>
          </div>
          <div class="cap">
            <div class="dot"></div>
            <div>
              <p class="cap-title">Taxonomic honesty</p>
              <p class="cap-sub">Cryptic species complexes are never resolved beyond what the evidence supports.</p>
            </div>
          </div>

          <div class="disclaimer">
            A screening aid for trained personnel — not a validated diagnostic device.
            Species within a complex can only be separated by PCR.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_password_reset():
    st.subheader("Reset your password")
    st.caption("We'll email you a link to set a new password.")

    with st.form("forgot_password_form", clear_on_submit=False):
        reset_email = st.text_input("Email", placeholder="you@institution.edu.ng").strip()
        submit_reset = st.form_submit_button("Send reset link", type="primary", width="stretch")

        if submit_reset:
            if not reset_email:
                st.error("Enter the email address registered to your account.")
            elif not SUPABASE_ENABLED:
                st.warning("Supabase is not configured, so no reset email can be sent.")
            else:
                try:
                    with st.spinner("Sending…"):
                        send_password_reset_email(reset_email)
                    st.success(f"If an account exists for {reset_email}, a reset link is on its way.")
                except Exception as e:
                    st.error(f"Could not send the reset email: {e}")

    if st.button("Back to sign in", key="link_back_to_signin", width="stretch"):
        st.session_state["auth_view"] = "login"
        st.rerun()


def _user_from_response(response):
    """sign_in_user returns a Supabase AuthResponse online and a plain dict on the
    local-admin fallback. Accept both rather than assuming one."""
    if response is None:
        return None
    if isinstance(response, dict):
        return response.get("user")
    return getattr(response, "user", None)


def _render_sign_in():
    with st.form("signin_form", clear_on_submit=False):
        st.subheader("Sign in")
        email = st.text_input("Email", placeholder="you@institution.edu.ng").strip()
        password = st.text_input("Password", type="password")

        # Invisible to a person, filled in by a bot: hidden by the .st-key-* CSS above, so
        # it stays in the DOM where an automated form-filler will find it.
        honeypot_value = st.text_input(
            "Confirm Account Verification Field", key="signin_verification_hp"
        )

        submit = st.form_submit_button("Sign in", type="primary", width="stretch")

        if submit:
            if honeypot_value:
                st.error("This request looks automated and was not processed.")
                st.stop()

            if not email or not password:
                st.error("Enter both your email and password.")
            else:
                try:
                    with st.spinner("Signing you in…"):
                        auth_user = _user_from_response(sign_in_user(email, password))

                    if auth_user:
                        set_authenticated(auth_user, provider="supabase" if SUPABASE_ENABLED else "local")
                        st.rerun()
                    else:
                        st.error("Incorrect email or password.")
                except Exception as e:
                    st.error(f"Could not sign you in: {e}")

    if st.button("Forgot your password?", key="link_forgot_pass", width="stretch"):
        st.session_state["auth_view"] = "forgot_password"
        st.rerun()


def _render_register():
    with st.form("register_form", clear_on_submit=False):
        st.subheader("Register")
        st.caption("For investigators and field staff authorised to record surveillance data.")
        reg_name = st.text_input("Full name").strip()
        reg_email = st.text_input("Email", placeholder="you@institution.edu.ng").strip()
        reg_password = st.text_input("Password", type="password")
        reg_password_confirm = st.text_input("Confirm password", type="password")

        reg_honeypot = st.text_input(
            "Confirm Registration Identifier Field", key="register_verification_hp"
        )

        submit_register = st.form_submit_button("Create account", type="primary", width="stretch")

        if submit_register:
            if reg_honeypot:
                st.error("This request looks automated and was not processed.")
                st.stop()

            if not reg_name or not reg_email or not reg_password:
                st.error("Complete every field to register.")
            elif reg_password != reg_password_confirm:
                st.error("The two passwords do not match.")
            else:
                try:
                    with st.spinner("Creating your account…"):
                        auth_user = _user_from_response(sign_up_user(reg_email, reg_password, reg_name))

                    if auth_user:
                        set_authenticated(auth_user, provider="supabase" if SUPABASE_ENABLED else "local")
                        st.rerun()
                    else:
                        # Supabase commonly returns no user here because the address needs
                        # confirming first — say so rather than implying the details were wrong.
                        st.info(
                            "Check your inbox to confirm your email address, then sign in. "
                            "If you already have an account, sign in instead."
                        )
                except Exception as e:
                    st.error(f"Could not create your account: {e}")


def render_login_page():
    """Sign in, register, or request a password reset."""
    _inject_styles()

    if "auth_view" not in st.session_state:
        st.session_state["auth_view"] = "login"

    left, right = st.columns([1.15, 1], gap="large")

    with left:
        _render_brand_panel()

    with right:
        if st.session_state["auth_view"] == "forgot_password":
            _render_password_reset()
        else:
            sign_in_tab, register_tab = st.tabs(["Sign in", "Register"])
            with sign_in_tab:
                _render_sign_in()
            with register_tab:
                _render_register()

        if not SUPABASE_ENABLED:
            st.warning(
                "Supabase is not configured, so accounts and data are unavailable. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY in your secrets to enable sign-in."
            )

        st.markdown(
            '<div class="login-foot">'
            'Encrypted in transit · Row-level security on every record · '
            'Screening aid, not a diagnostic device'
            '</div>',
            unsafe_allow_html=True,
        )
