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
        # Left-align the labels and give every tab a sky-blue fill: inactive tabs
        # get a light sky blue with bold near-black text; the active tab gets a
        # deeper sky blue with white text so it still stands out. Color is forced
        # on the button AND its inner nodes (label <p> + icon), because Streamlit
        # nests the label in a child element that overrides a button-only color.
        st.markdown(
            """
            <style>
            /* Text/icon color — target the button and every descendant.
               -webkit-text-fill-color is set too: it overrides `color` on the
               rendered glyphs, so `color` alone can leave the label its default
               (near-white) shade. */
            section[data-testid="stSidebar"] .stButton > button,
            section[data-testid="stSidebar"] .stButton > button * {
                color: #111827 !important;
                -webkit-text-fill-color: #111827 !important;
                fill: #111827 !important;
            }
            /* Shape + fill on the button element only. */
            section[data-testid="stSidebar"] .stButton > button {
                justify-content: flex-start;
                font-weight: 700;
                background-color: #87ceeb !important;
                border-color: #6cb8dd !important;
            }
            section[data-testid="stSidebar"] .stButton > button:hover {
                background-color: #6cb8dd !important;
                border-color: #4aa3cf !important;
            }
            /* Active tab: deeper blue with white label + icon. */
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] * {
                color: #ffffff !important;
                -webkit-text-fill-color: #ffffff !important;
                fill: #ffffff !important;
            }
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
                background-color: #0ea5e9 !important;
                border-color: #0284c7 !important;
            }
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
                background-color: #0284c7 !important;
                border-color: #0284c7 !important;
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
                width="stretch",
                type="primary" if is_active else "secondary",
            )
            if clicked and not is_active:
                st.query_params["page"] = key
                st.rerun()
