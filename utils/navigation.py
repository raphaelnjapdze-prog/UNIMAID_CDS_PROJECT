# =========================================================================
# PRODUCT NAVIGATION INTERFACE (utils/navigation.py)
# =========================================================================
import streamlit as st

# Page registry: (query-param id, label, Material Symbols icon).
# Material icons are crisp vector glyphs (same line-art spirit as the original
# Lucide SVGs); Streamlit renders them on native buttons via the :material/...:
# syntax. Custom SVG can't go on a native button, so this is the closest look
# that keeps the in-session (no page reload) navigation.
_PAGES = [
    ("dashboard", "Command Center", ":material/dashboard:"),
    ("log", "Site Log Entry", ":material/edit_note:"),
    ("ai", "AI Diagnostics", ":material/biotech:"),
    ("capture", "Multi-Angle Capture", ":material/photo_camera:"),
    ("trends", "Change Trends", ":material/trending_up:"),
    ("copilot", "AI Copilot", ":material/smart_toy:"),
    ("forecaster", "Seasonal Forecast", ":material/calendar_month:"),
    ("risk", "Risk Engine", ":material/warning:"),
    ("correlation", "Correlations", ":material/hub:"),
    ("lab", "PCR Lab", ":material/science:"),
    ("bioassay", "Bioassay Entry", ":material/vaccines:"),
    ("case_entry", "Clinical Case Entry", ":material/clinical_notes:"),
    ("retraining", "Retraining", ":material/model_training:"),
    ("reports", "Reports", ":material/description:"),
    ("profile", "Profile", ":material/account_circle:"),
]


def render_sidebar_nav(active: str):
    """
    Sidebar navigation.

    Tabs navigate IN-SESSION by setting st.query_params (this updates the URL
    and reruns without a full page reload), so the authenticated session_state
    survives a click. Plain HTML <a href> links — the previous approach —
    trigger a browser navigation that spins up a fresh Streamlit session with
    empty state, which logged the user out on every tab click.
    """
    with st.sidebar:
        # Left-align the labels, and force readable label colors. The default
        # secondary-button text rendered near-white on the light sidebar and was
        # invisible until hover; pin inactive tabs to dark slate (teal on hover)
        # while keeping the active teal-filled tab's label white.
        st.markdown(
            """
            <style>
            section[data-testid="stSidebar"] .stButton > button {
                justify-content: flex-start;
                font-weight: 600;
                color: #1e293b !important;
            }
            section[data-testid="stSidebar"] .stButton > button:hover {
                color: #0d9488 !important;
                border-color: #0d9488 !important;
            }
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
                color: #ffffff !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("Navigation")
        st.markdown("---")

        for key, label, icon_name in _PAGES:
            is_active = key == active
            clicked = st.button(
                label,
                key=f"nav_{key}",
                icon=icon_name,
                use_container_width=True,
                type="primary" if is_active else "secondary",
            )
            if clicked and not is_active:
                st.query_params["page"] = key
                st.rerun()
