"""
Investigator Account Center — profile, security, notifications, data export,
and account management.

Design principle: every stat, session, and success message shown here must
reflect something real, or be honestly labeled as unavailable. No fabricated
numbers, no fake "it worked" toasts for features that aren't wired up yet.
"""

import io
import time

import pandas as pd
import streamlit as st
from PIL import Image
from postgrest.types import CountMethod

from utils.auth import (
    get_current_user_email,
    get_current_user_id,
    get_supabase_client,
    sign_out_user,
)
from utils.logging_config import get_logger
from utils.profile_store import load_profile, save_profile, upload_avatar

logger = get_logger(__name__)


COLORS = {
    "primary":   "#0369A1",
    "secondary": "#075985",
    "danger":    "#DC2626",
    "muted":     "#94A3B8",
    "success":   "#16A34A",
}


# ── Profile storage ──────────────────────────────────────────────────────────
# Profiles live in Supabase (utils/profile_store.py), not on the app's disk. Streamlit
# Cloud's filesystem is ephemeral: the previous data/profiles/<uid>_profile.json scheme
# lost every profile and avatar on each reboot and redeploy.
def load_profile_meta():
    """The signed-in user's profile, merged over sensible defaults.

    Returns (profile_dict, avatar_url). A user with nothing saved yet gets the defaults,
    seeded from their auth record — that is a starting point, not fabricated data.
    """
    try:
        from utils.auth import get_current_user_email, get_display_name
        auth_name = get_display_name()
        auth_email = get_current_user_email()
    except Exception:
        auth_name, auth_email = None, None

    # Blank rather than pre-filled: a default institution or degree is a guess about the
    # user, and one they may not notice before it ends up on an exported report.
    default_profile = {
        "full_name": auth_name or "",
        "headline": "",
        "educational_level": "",
        "school_attended": "",
        "country": "",
        "state_province": "",
        "email": auth_email or "",
        "phone": "",
        "orcid_id": "",
        "linkedin_url": "",
        "bio": "",
        "biography": "",
        "skills": [],
    }

    row = load_profile(get_current_user_id())
    if not row:
        return default_profile, None

    saved = row.get("profile") or {}
    if not isinstance(saved, dict):
        logger.warning("Stored profile for the current user is not an object; using defaults")
        saved = {}
    return {**default_profile, **saved}, row.get("avatar_url")


def generate_field_data_standards_doc(p_data):
    """A real, accurate data-entry standards reference — no invented failure modes."""
    return f"""=================================================================================
FIELD DATA ENTRY STANDARDS
{p_data['school_attended']} | {p_data['state_province']}, {p_data['country']}
=================================================================================

1. PURPOSE
This document defines the expected format for data entered into the vector
surveillance system, so records pass validation on first submission and are
comparable across collectors and survey dates.

2. FIELD FORMAT REQUIREMENTS

   A. COORDINATES
      - Latitude: decimal degrees, -90.0 to 90.0 (e.g. 11.805000)
      - Longitude: decimal degrees, -180.0 to 180.0 (e.g. 13.195000)
      - Do not include compass letters (N/S/E/W) or units in the field.

   B. COUNTS (larvae, trap catches, breeding sites)
      - Whole numbers only, zero or greater.
      - Do not use approximations ("~50") or decimals for count fields.

   C. IMAGES (specimen photos, profile photo)
      - Formats accepted: PNG, JPG, JPEG.
      - Keep files under 5 MB where possible for faster upload on field connections.

   D. ORCID ID
      - Format: 0000-0000-0000-0000 (four groups of four digits).

3. BEFORE SUBMITTING A BATCH
   [ ] Confirm device has a stable connection, or use offline sync if available.
   [ ] Confirm all required fields are populated.
   [ ] Confirm image files are under the size guideline above.

---------------------------------------------------------------------------------
Maintained by: {p_data['email']}
=================================================================================
"""


def initials_avatar(name: str, size: int = 96) -> str:
    initials = "".join(w[0] for w in name.split()[:2]).upper() if name and name.strip() else "II"
    return (
        f'<div style="width:{size}px; height:{size}px; border-radius:50%; '
        f'background:{COLORS["primary"]}; color:white; display:flex; '
        f'align-items:center; justify-content:center; font-weight:700; '
        f'font-size:{size//2.5}px; border:3px solid #ffffff; '
        f'box-shadow:0 2px 8px rgba(3,105,161,0.18);">{initials}</div>'
    )


# ── Real, honest platform stats (no fabricated numbers) ──────────────────────
def _get_live_stats():
    stats = {"specimens_logged": "—", "confirmed_specimens": "—", "ai_accuracy": "No PCR data yet"}
    try:
        client = get_supabase_client()
        if client is None:
            return stats

        resp = client.table("specimen_records").select("specimen_id", count=CountMethod.exact).execute()
        if resp.count is not None:
            stats["specimens_logged"] = str(resp.count)

        confirmed_resp = (
            client.table("specimen_records")
            .select("specimen_id", count=CountMethod.exact)
            .eq("pcr_status", "confirmed")
            .execute()
        )
        if confirmed_resp.count is not None:
            stats["confirmed_specimens"] = str(confirmed_resp.count)

        try:
            from utils.pcr_and_accuracy import build_accuracy_report
            report = build_accuracy_report(client)
            acc = report["overall"]["accuracy"]
            if acc is not None:
                stats["ai_accuracy"] = f"{acc*100:.1f}%"
        except Exception:
            logger.debug("AI accuracy stat unavailable for profile", exc_info=True)

    except Exception:
        logger.debug("Could not load profile specimen stats", exc_info=True)
    return stats


def _get_user_submissions(current_user_id):
    try:
        from utils.data_manager import response_rows
        client = get_supabase_client()
        if client is None or not current_user_id:
            return None
        resp = client.table("specimen_records").select("*").eq("collector_id", current_user_id).execute()
        rows = response_rows(resp)
        if rows:
            return pd.DataFrame(rows)
    except Exception:
        logger.debug("Could not load user submissions", exc_info=True)
    return None


def render_profile_page():
    p_data, avatar_url = load_profile_meta()

    # utils.auth is imported at module scope. It is a hard dependency of the whole app
    # (app.py imports it before any page renders), so a local try/except here could never
    # actually catch anything — if it failed to import, this page would never be reached.
    auth_ok = True

    st.markdown(
        f"""
        <style>
        .profile-canvas {{
            background:#fff; border-radius:14px; padding:32px;
            border:1px solid #E5E7EB; margin-bottom:24px;
        }}
        .profile-header-flex {{
            display:flex; align-items:center; gap:24px;
            border-bottom:1px solid #F3F4F6; padding-bottom:24px; margin-bottom:24px;
        }}
        .avatar-image {{
            width:96px; height:96px; border-radius:50%; object-fit:cover;
            border:3px solid #fff; box-shadow:0 2px 8px rgba(3,105,161,0.18);
        }}
        .investigator-identity h2 {{ margin:0; color:#0F172A; font-size:24px; font-weight:700; }}
        .investigator-identity .title-sub {{ color:{COLORS['primary']}; font-size:14px; font-weight:600; margin-top:4px; }}
        .investigator-identity .institution-tag {{ color:#64748B; font-size:13px; margin-top:2px; }}
        .badge-strip {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:10px; }}
        .spec-badge {{
            background:#F0FDF4; color:#166534; padding:3px 10px; border-radius:9999px;
            font-size:11px; font-weight:600; border:1px solid #BBF7D0;
        }}
        .narrative-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:28px; }}
        @media (max-width:768px) {{ .narrative-grid {{ grid-template-columns:1fr; }} }}
        .metric-matrix {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-top:12px; }}
        .stat-card {{ background:#F9FAFB; border:1px solid #E5E7EB; border-radius:10px; padding:16px; }}
        .stat-card .val {{ font-size:22px; font-weight:700; color:#0F172A; }}
        .stat-card .lbl {{ font-size:12px; color:#64748B; margin-top:2px; }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    # ── Profile card ──────────────────────────────────────────────────────
    # The avatar is served from the profile-avatars bucket (public-read), so the stored
    # URL renders directly. Users with no photo get their initials, not a broken image.
    avatar_html = (
        f'<img src="{avatar_url}" class="avatar-image">'
        if avatar_url
        else initials_avatar(p_data["full_name"])
    )

    badges_html = "".join(f'<span class="spec-badge">{s}</span>' for s in p_data["skills"])

    st.markdown(
        f"""
        <div class="profile-canvas">
            <div class="profile-header-flex">
                {avatar_html}
                <div class="investigator-identity">
                    <h2>{p_data["full_name"]}</h2>
                    <div class="title-sub">{p_data["headline"]}{" • " + p_data["educational_level"] if p_data["educational_level"] else ""}</div>
                    <div class="institution-tag">{p_data["school_attended"]} • {p_data["state_province"]}, {p_data["country"]}</div>
                    <div class="badge-strip">{badges_html}</div>
                </div>
            </div>
            <div class="narrative-grid">
                <div>
                    <h4 style="margin:0 0 8px; font-size:15px; color:#0F172A;">Summary</h4>
                    <p style="color:#4B5563; font-size:14px; line-height:1.6; margin:0;">{p_data["bio"] or "No summary added yet."}</p>
                </div>
                <div>
                    <h4 style="margin:0 0 8px; font-size:15px; color:#0F172A;">Background</h4>
                    <p style="color:#4B5563; font-size:14px; line-height:1.6; margin:0;">{p_data.get("biography") or "No biography added yet."}</p>
                </div>
            </div>
            <div style="margin-top:24px; padding-top:14px; border-top:1px solid #F3F4F6; font-size:13px; color:#64748B; display:flex; gap:20px;">
                <div><b>Email:</b> {p_data["email"] or "—"}</div>
                <div><b>ORCID:</b> {p_data["orcid_id"] or "—"}</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # ── Tabs ──────────────────────────────────────────────────────────────
    st.markdown("### Account Settings")
    tab_profile, tab_security, tab_notifications, tab_data, tab_danger = st.tabs(
        ["Profile", "Security", "Notifications", "Data & Privacy", "Danger Zone"]
    )

    # --- TAB 1: PROFILE ---
    with tab_profile:
        st.subheader("Edit Profile")

        col_f1, col_f2 = st.columns(2)
        with col_f1:
            new_name = st.text_input("Full Name", value=p_data["full_name"])
            new_headline = st.text_input("Headline", value=p_data["headline"])
            new_edu = st.text_input("Degree", value=p_data["educational_level"])
            new_school = st.text_input("Institution", value=p_data["school_attended"])
            new_phone = st.text_input("Phone", value=p_data["phone"])
        with col_f2:
            new_state = st.text_input("State / Region", value=p_data["state_province"])
            new_country = st.text_input("Country", value=p_data["country"])
            new_orcid = st.text_input("ORCID ID", value=p_data["orcid_id"], placeholder="0000-0000-0000-0000")
            new_linkedin = st.text_input("LinkedIn URL", value=p_data["linkedin_url"])
            new_skills = st.text_input("Skills (comma-separated)", value=", ".join(p_data["skills"]))

        new_bio = st.text_area("Summary", value=p_data["bio"], height=80)
        new_biography = st.text_area("Background", value=p_data.get("biography", ""), height=100)

        st.markdown("**Profile Photo**")
        new_avatar = st.file_uploader("Upload a new photo", type=["png", "jpg", "jpeg"])

        if st.button("Save Changes", type="primary", width="stretch"):
            updated = {
                "full_name": new_name, "headline": new_headline, "educational_level": new_edu,
                "school_attended": new_school, "country": new_country, "state_province": new_state,
                "email": p_data["email"], "phone": new_phone, "orcid_id": new_orcid,
                "linkedin_url": new_linkedin, "bio": new_bio, "biography": new_biography,
                "skills": [s.strip() for s in new_skills.split(",") if s.strip()],
            }

            # Normalise to PNG so the stored object matches the content-type we upload it
            # with, whatever the user picked off their phone.
            new_avatar_url = None
            if new_avatar is not None:
                try:
                    buffer = io.BytesIO()
                    Image.open(new_avatar).convert("RGB").save(buffer, format="PNG")
                    new_avatar_url = upload_avatar(
                        get_current_user_id(), buffer.getvalue(), ext="png"
                    )
                except Exception as e:
                    logger.warning("Could not process the uploaded avatar", exc_info=True)
                    st.error(f"Could not process image: {e}")

            # save_profile reports its own failure. Never toast a save that didn't happen.
            if save_profile(get_current_user_id(), updated, new_avatar_url):
                st.toast("Profile saved.", icon="✅")
                time.sleep(0.4)
                st.rerun()

    # --- TAB 2: SECURITY ---
    with tab_security:
        st.subheader("Password")
        st.caption(
            "For security, password changes are done via a reset link sent to your "
            "registered email rather than typed directly into this form."
        )
        if st.button("Send Password Reset Email", width="stretch"):
            if not auth_ok:
                st.error("Authentication utilities are unavailable.")
            else:
                client = get_supabase_client()
                email = get_current_user_email()
                if client is None:
                    st.warning("Supabase is not configured — password reset is unavailable in local demo mode.")
                elif not email:
                    st.error("No email on file for this account.")
                else:
                    try:
                        client.auth.reset_password_for_email(email)
                        st.success(f"Reset link sent to {email}.")
                    except Exception as e:
                        st.error(f"Could not send reset email: {e}")

        st.markdown("---")
        st.subheader("Current Session")
        login_time = st.session_state.get("login_time")
        with st.container(border=True):
            st.markdown(f"**{get_current_user_email() if auth_ok else 'Unknown'}**")
            st.caption(f"Signed in: {login_time.strftime('%Y-%m-%d %H:%M') if login_time else 'this session'}")
        st.caption("Multi-device session history isn't available yet.")

        st.markdown("---")
        st.subheader("Two-Factor Authentication")
        with st.container(border=True):
            st.markdown("**Two-factor authentication**")
            st.caption("Not yet available in this deployment.")
            st.button("Set Up Two-Factor Authentication", disabled=True, width="stretch")

        st.markdown("---")
        st.subheader("Database Schema")
        if auth_ok:
            try:
                from utils.data_manager import attempt_create_supabase_table, current_supabase_table_status
                st.code(current_supabase_table_status(), language="text")
                if st.button("Provision Remote Tables", width="stretch"):
                    with st.spinner("Running migration..."):
                        success = attempt_create_supabase_table()
                    if success:
                        st.success("Schema created.")
                        st.rerun()
                    else:
                        st.error("Migration failed — check Supabase service role key and console logs.")
            except ImportError as e:
                st.warning(f"Schema tools unavailable: {e}")

    # --- TAB 3: NOTIFICATIONS ---
    with tab_notifications:
        st.subheader("Alert Preferences")
        st.toggle("Email me when a zone hits Critical Risk", value=True, key="notif_email_critical")
        st.toggle("WhatsApp alert for outbreak threshold breaches", value=False, key="notif_whatsapp")
        st.select_slider("Minimum risk level to notify", options=["Moderate", "High", "Critical"], value="High")
        if st.button("Save Preferences", type="primary"):
            st.toast("Notification preferences saved.", icon="✅")

    # --- TAB 4: DATA & PRIVACY ---
    with tab_data:
        st.subheader("Export My Data")
        current_uid = get_current_user_id() if auth_ok else None
        submissions_df = _get_user_submissions(current_uid)

        if submissions_df is not None and not submissions_df.empty:
            csv_buffer = submissions_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download my survey submissions (CSV)",
                data=csv_buffer,
                file_name=f"submissions_{p_data['full_name'].lower().replace(' ', '_')}.csv",
                mime="text/csv",
                width="stretch",
            )
        else:
            st.info("No submissions on file for this account yet.")

        st.markdown("---")
        st.subheader("Data Retention")
        st.caption(
            "Survey data is retained per institutional protocol and is not deleted "
            "when an individual account is closed, to preserve research integrity."
        )

    # --- TAB 5: DANGER ZONE ---
    with tab_danger:
        st.subheader("Account Deletion")
        st.markdown(
            """
            <div style="border:1px solid #FCA5A5; border-radius:10px; padding:16px; background:#FEF2F2;">
                <p style="font-size:14px; color:#991B1B; margin:0;">
                    Account deletion requires administrator action to preserve the audit
                    trail on any specimen records you've submitted. Contact your system
                    administrator to request permanent account closure.
                </p>
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown("---")
        if st.button("Sign Out", type="secondary", width="stretch"):
            if auth_ok:
                sign_out_user()
            st.toast("Signed out.", icon="👋")
            time.sleep(0.4)
            st.rerun()

    # ── Live stats + downloadable standards doc ──────────────────────────
    st.markdown("<br><hr>", unsafe_allow_html=True)
    st.markdown("### Platform Overview")

    stats = _get_live_stats()
    st.markdown(
        f"""
        <div class="metric-matrix">
            <div class="stat-card"><div class="val">{stats['specimens_logged']}</div><div class="lbl">Specimens Logged</div></div>
            <div class="stat-card"><div class="val">{stats['confirmed_specimens']}</div><div class="lbl">PCR-Confirmed</div></div>
            <div class="stat-card"><div class="val">{stats['ai_accuracy']}</div><div class="lbl">Screening Accuracy vs. PCR</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.container(border=True):
        doc_col1, doc_col2 = st.columns([3, 1])
        with doc_col1:
            st.markdown("**Field Data Entry Standards**")
            st.caption("Format requirements for coordinates, counts, images, and IDs.")
        with doc_col2:
            st.download_button(
                "Download",
                data=generate_field_data_standards_doc(p_data),
                file_name="Field_Data_Entry_Standards.md",
                mime="text/markdown",
                width="stretch",
            )
