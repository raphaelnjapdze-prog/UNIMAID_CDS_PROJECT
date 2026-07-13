# =========================================================================
# LOGIN VIEW & PORTAL MATRIX ENGINE (components/login.py)
# =========================================================================
import os

import streamlit as st

from utils.auth import send_password_reset_email, set_authenticated, sign_in_user, sign_up_user
from utils.config import SUPABASE_ENABLED


def render_login_page():
    """Renders a hardened, visual research portal supporting Login, Registration, and Password Recovery."""

    # Add system title header
    st.markdown("""
        <div style="text-align: center; padding: 20px 0px 10px 0px;">
            <h1 style="color: #0369a1; margin: 0; font-weight: 700;">National Integrated Vector Surveillance System</h1>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
        <style>
        .login-header {
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #0369a1 0%, #075985 100%);
            color: white;
            border-radius: 10px;
            margin-bottom: 30px;
        }
        .img-card {
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
            margin-bottom: 20px;
            border: 1px solid #e2e8f0;
        }
        /* Hidden honeypot layout pattern for invisible bot defense */
        .human-hidden {
            display: none !important;
            position: absolute;
            left: -9999px;
            width: 1px;
            height: 1px;
        }
        /* Style for the professional trust anchor row */
        .trust-footer-row {
            text-align: center;
            font-size: 11px;
            color: #94A3B8;
            margin-top: 20px;
            padding-top: 12px;
            border-top: 1px solid #E2E8F0;
            letter-spacing: 0.3px;
        }
        </style>
    """, unsafe_allow_html=True)

    if "auth_view" not in st.session_state:
        st.session_state["auth_view"] = "login"

    col1, col2, col3 = st.columns([1, 1.2, 1])

    # --- COLUMN 1: RESEARCH IMAGERY & MEDIA (LEFT FLANK) ---
    with col1:
        images_to_load = [
            {"file": "Clinical_malarias.jpg", "caption": "Clinical Malaria Research"},
            {"file": "vector_species.png", "caption": "Vector Species Identification"},
            {"file": "Microscopic_Laval.png", "caption": "Microscopic Larvae Analysis"}
        ]

        for img_item in images_to_load:
            if os.path.exists(img_item["file"]):
                st.image(img_item["file"], caption=img_item["caption"], width="stretch")
            else:
                with st.container(border=True):
                    st.caption(f"🔬 {img_item['caption']} Asset State: Offline")

    # --- COLUMN 2: AUTHENTICATION INTERFACE CONSOLE (CENTER CARD) ---
    with col2:

        # -----------------------------------------------------------------
        # SECTION A: PASSWORD RECOVERY VIEW ROUTE
        # -----------------------------------------------------------------
        if st.session_state["auth_view"] == "forgot_password":
            with st.container(border=True):
                st.subheader("🔑 Password Recovery Node")
                st.caption("Request a secure cryptographic recovery vector link emailed to your account register.")
                st.markdown("<br>", unsafe_allow_html=True)

                with st.form("forgot_password_form", clear_on_submit=False):
                    reset_email = st.text_input("Registered Investigator Email", placeholder="researcher@example.com").strip()
                    submit_reset = st.form_submit_button("Generate Reset Vector Link", type="primary", width="stretch")

                    if submit_reset:
                        if not reset_email:
                            st.error("Recovery halted: Please input a valid registration email link.")
                        else:
                            try:
                                with st.spinner("Processing network token parameters..."):
                                    if SUPABASE_ENABLED:
                                        send_password_reset_email(reset_email)
                                        st.success(f"Recovery token dispatched safely to {reset_email}. Check your mail inbox coordinates.")
                                    else:
                                        st.info(f"Local Demo Mode Active: Simulated recovery configuration sent successfully for {reset_email}.")
                            except Exception as reset_fault:
                                st.error(f"Recovery node exception: {str(reset_fault)}")

                if st.button("⬅ Return to Sign In console", width="stretch"):
                    st.session_state["auth_view"] = "login"
                    st.rerun()

        # -----------------------------------------------------------------
        # SECTION B: MAIN SIGN IN & REGISTER TABS VIEW ROUTE
        # -----------------------------------------------------------------
        else:
            auth_tab = st.tabs(["Sign In", "Register"])

            # -------------------------------------------------------------
            # 🔑 SUB-CONSOLE: INVESTIGATOR SIGN IN
            # -------------------------------------------------------------
            with auth_tab[0]:
                with st.form("signin_form", clear_on_submit=False):
                    st.subheader("Secure Investigator Login")
                    email = st.text_input("Email", placeholder="researcher@example.com").strip()
                    password = st.text_input("Password", type="password")

                    # ─── INVISIBLE BOT DEFENSE HONEYPOT ──────────────────────
                    st.markdown('<div class="human-hidden">', unsafe_allow_html=True)
                    honeypot_value = st.text_input("Confirm Account Verification Field", key="signin_verification_hp")
                    st.markdown('</div>', unsafe_allow_html=True)
                    # ─────────────────────────────────────────────────────────

                    submit = st.form_submit_button("Sign In", width="stretch")

                    if submit:
                        # Validate Honeypot Status
                        if honeypot_value:
                            st.error("Security execution rejected: Automation marker triggered.")
                            st.stop()

                        if not email or not password:
                            st.error("Authentication halted: Mandatory fields missing.")
                        else:
                            try:
                                with st.spinner("Connecting to primary authorization node..."):
                                    auth_response = sign_in_user(email, password)

                                    auth_user = None
                                    if auth_response is not None:
                                        if isinstance(auth_response, dict):
                                            auth_user = auth_response.get("user")
                                        else:
                                            auth_user = getattr(auth_response, "user", None)

                                    if auth_user:
                                        provider_tag = "supabase" if SUPABASE_ENABLED else "local"
                                        set_authenticated(auth_user, provider=provider_tag)
                                        st.success("Access matrix authorized successfully.")
                                        st.rerun()
                                    else:
                                        st.error("Invalid credentials or database synchronization failed.")
                            except Exception as network_error:
                                st.error(f"Operational system fault encountered: {str(network_error)}")

                st.markdown("<br>", unsafe_allow_html=True)
                if st.button(" Forgot credentials? Recover passkey sequence", key="link_forgot_pass", width="stretch"):
                    st.session_state["auth_view"] = "forgot_password"
                    st.rerun()

            # -------------------------------------------------------------
            # SUB-CONSOLE: NEW NODE SIGN UP REGISTRATION
            # -------------------------------------------------------------
            with auth_tab[1]:
                with st.form("register_form", clear_on_submit=False):
                    st.subheader("Register a New Investigator")
                    reg_name = st.text_input("Full Name").strip()
                    reg_email = st.text_input("Email", placeholder="user@example.com").strip()
                    reg_password = st.text_input("Password", type="password")
                    reg_password_confirm = st.text_input("Confirm Password", type="password")

                    # ─── INVISIBLE BOT DEFENSE HONEYPOT ──────────────────────
                    st.markdown('<div class="human-hidden">', unsafe_allow_html=True)
                    reg_honeypot = st.text_input("Confirm Registration Identifier Field", key="register_verification_hp")
                    st.markdown('</div>', unsafe_allow_html=True)
                    # ─────────────────────────────────────────────────────────

                    submit_register = st.form_submit_button("Register", width="stretch")

                    if submit_register:
                        if reg_honeypot:
                            st.error("Security execution rejected: Automation marker triggered.")
                            st.stop()

                        if not reg_name or not reg_email or not reg_password:
                            st.error("Please complete all registration fields.")
                        elif reg_password != reg_password_confirm:
                            st.error("Passwords do not match. Validation check failed.")
                        else:
                            try:
                                with st.spinner("Provisioning credentials across remote cloud tables..."):
                                    response = sign_up_user(reg_email, reg_password, reg_name)

                                    auth_user = None
                                    if response is not None:
                                        if isinstance(response, dict):
                                            auth_user = response.get("user")
                                        else:
                                            auth_user = getattr(response, "user", None)

                                    if auth_user:
                                        provider_tag = "supabase" if SUPABASE_ENABLED else "local"
                                        set_authenticated(auth_user, provider=provider_tag)
                                        st.success("Access matrix authorized successfully.")
                                        st.rerun()
                                    else:
                                        st.error("Invalid credentials or database synchronization failed.")

                            except Exception as registration_fault:
                                st.error(f"Relational registration fault: {str(registration_fault)}")

        # --- SYSTEM METADATA DEPLOYMENT FOOTER CONTROLS ---
        st.markdown("---")
        if SUPABASE_ENABLED:
            st.info("Supabase authentication is enabled. Registered investigators can sign in using email/password.")
        else:
            st.warning(
                "Supabase is not configured. The app will continue in local demo mode. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY using your platform's Secrets Management console for production auth."
            )

            st.markdown(
                "**Local fallback:** sign in with the admin account configured via "
                "`ADMIN_USERNAME` / `ADMIN_PASSWORD` in your environment or Secrets. "
                "If no admin password is set, only Supabase authentication is available."
            )

        # ─── UNIVERSAL TRUST & COMPLIANCE FOOTER ROW ────────────────────────
        st.markdown("""
            <div class="trust-footer-row">
                Data encrypted in transit &bull; Secure Cryptographic Access &bull; WHO IVM Aligned Protocol
            </div>
        """, unsafe_allow_html=True)

    # --- COLUMN 3: FIELD OPERATIONS & ANALYTICS MEDIA (RIGHT FLANK) ---
    with col3:
        right_images = [
            {"file": "field_surveillance.jpg", "caption": "Larval Habitat Mapping"},
            {"file": "field_collection.jpg", "caption": "Field Collection Operations"},
            {"file": "bioassay_testing.jpg", "caption": "Insecticide Bioassay Tracking"}
        ]

        for img_item in right_images:
            if os.path.exists(img_item["file"]):
                st.image(img_item["file"], caption=img_item["caption"], width=250)
            else:
                with st.container(border=True):
                    st.caption(f"📡 {img_item['caption']} Asset State: Offline")
