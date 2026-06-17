# =========================================================================
# LOGIN VIEW & PORTAL MATRIX ENGINE (components/login.py)
# =========================================================================
import streamlit as st
import random
from utils.config import SUPABASE_ENABLED, ADMIN_USERNAME, ADMIN_PASSWORD
from utils.auth_db import sign_in_user, sign_up_user, set_authenticated

def render_login_page():
    """Renders a beautified, visual research portal for authentication."""

    st.markdown("""
        <style>
        .login-header {
            text-align: center;
            padding: 30px;
            background: linear-gradient(135deg, #0369a1 0%, #075985 10%);
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
        .img-caption {
            font-size: 12px;
            text-align: center;
            padding: 8px;
            background: #f8fafc;
            color: #475569;
            font-weight: 600;
        }
        </style>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div class="login-header">
            <h1 style="margin:0; font-size: 32px;">UNIMAID Vector Sentinel</h1>
            <p style="margin:0; opacity: 10;">Integrated Vector Management & Epidemiological Surveillance Node</p>
        </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1.2, 1])

    with col1:
        st.image("Clinical_malarias.jpg", caption="Clinical Malaria Research")
        st.image("vector_species.png", caption="Vector Species Identification")
        st.image("Microscopic_Laval.png", caption="Microscopic Larvae Analysis")

    with col2:
        if "captcha_challenge" not in st.session_state:
            st.session_state.captcha_challenge = {"num1": random.randint(5, 20), "num2": random.randint(1, 10)}

        auth_tab = st.tabs(["Sign In", "Register"])

        with auth_tab[0]:
            with st.form("signin_form"):
                st.subheader("Secure Investigator Login")
                email = st.text_input("Email", placeholder="researcher@unimaid.edu.ng")
                password = st.text_input("Password", type="password")
                captcha_answer = st.text_input(
                    "Anti-bot verification: What is "
                    f"{st.session_state.captcha_challenge['num1']} + {st.session_state.captcha_challenge['num2']}?",
                    key="signin_captcha",
                )
                submit = st.form_submit_button("Sign In")

                if submit:
                    try:
                        required_captcha = st.session_state.captcha_challenge["num1"] + st.session_state.captcha_challenge["num2"]
                        if int(captcha_answer or -1) != required_captcha:
                            st.error("CAPTCHA verification failed.")
                        else:
                            auth_response = sign_in_user(email, password)
                            auth_user = None
                            if auth_response is not None:
                                auth_user = auth_response.get("user") if isinstance(auth_response, dict) else getattr(auth_response, "user", None)
                            if auth_user:
                                set_authenticated(auth_user, provider="supabase" if SUPABASE_ENABLED else "local")
                                st.success("Login successful.")
                                st.rerun()
                            else:
                                st.error("Invalid credentials or Supabase authentication failed.")
                    except ValueError:
                        st.error("Please provide a numeric answer for verification.")

        with auth_tab[1]:
            with st.form("register_form"):
                st.subheader("Register a New Investigator")
                reg_name = st.text_input("Full Name")
                reg_email = st.text_input("Email")
                reg_password = st.text_input("Password", type="password")
                reg_password_confirm = st.text_input("Confirm Password", type="password")
                submit_register = st.form_submit_button("Register")

                if submit_register:
                    if not reg_name or not reg_email or not reg_password:
                        st.error("Please complete all registration fields.")
                    elif reg_password != reg_password_confirm:
                        st.error("Passwords do not match.")
                    else:
                        response = sign_up_user(reg_email, reg_password, reg_name)
                        auth_user = None
                        if response is not None:
                            auth_user = getattr(response, "user", None) if not isinstance(response, dict) else response.get("user")
                        if auth_user:
                            set_authenticated(auth_user, provider="supabase")
                            st.success("Registration complete. You are now logged in.")
                            st.rerun()
                        else:
                            st.error("Registration failed. Check your Supabase credentials and configuration.")

        st.markdown("---")
        if SUPABASE_ENABLED:
            st.info("Supabase authentication is enabled. Registered investigators can sign in using email/password.")
        else:
            st.warning(
                "Supabase is not configured. The app will continue in local demo mode. "
                "Set SUPABASE_URL and SUPABASE_ANON_KEY using your platform's Secrets Management console for production auth."
            )
        if not SUPABASE_ENABLED:
            st.markdown("**Local fallback:** use the sample admin account to access the dashboard.")
            st.text(f"Username: {ADMIN_USERNAME}")
            st.text(f"Password: {ADMIN_PASSWORD}")

        st.markdown("**Guest Explorer Mode:**")
        st.info(
            "Start a secure guest exploration session with simulated operational data. "
            "This mode is ideal for demonstrations, stakeholder walkthroughs, and pilot previews."
        )
        if st.button("Continue as Guest Explorer", key="guest_explorer_button"):
            st.session_state["guest_explorer"] = True
            st.session_state["authenticated"] = False
            st.session_state["auth_provider"] = "guest"
            st.session_state["auth_user_email"] = "guest@explorer.local"
            st.session_state["auth_user_id"] = "guest-explorer"
            st.session_state["auth_user_name"] = "Guest Explorer"
            st.session_state["current_page"] = "dashboard"
            st.rerun()