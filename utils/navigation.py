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
        # Ghost navigation: inactive items are quiet (transparent, muted slate text)
        # so the sidebar reads as one calm list; only the ACTIVE item is emphasized —
        # a teal tint, a teal left-accent bar, and teal label/icon — matching the
        # product's teal brand instead of the old sky-blue that clashed with it.
        # Color is forced on the button AND its inner nodes (label <p> + icon), and
        # -webkit-text-fill-color is set too because it overrides `color` on the
        # rendered glyphs — `color` alone can leave the label its default shade.
        st.markdown(
            """
            <style>
            /* Section eyebrow above the nav list. */
            .vs-nav-eyebrow {
                color: #64748b !important;
                font-size: 0.7rem !important;
                font-weight: 600 !important;
                letter-spacing: 0.09em !important;
                text-transform: uppercase !important;
                margin: 0.35rem 0 0.6rem 0.15rem !important;
            }

            /* Inactive item (secondary button): quiet, transparent, muted text. */
            section[data-testid="stSidebar"] .stButton > button,
            section[data-testid="stSidebar"] .stButton > button * {
                color: #cbd5e1 !important;
                -webkit-text-fill-color: #cbd5e1 !important;
                fill: #cbd5e1 !important;
            }
            section[data-testid="stSidebar"] .stButton > button {
                justify-content: flex-start !important;
                font-weight: 500 !important;
                background-color: transparent !important;
                border: 1px solid transparent !important;
                border-radius: 8px !important;
                box-shadow: none !important;
                transition: background-color 0.15s ease, color 0.15s ease !important;
            }
            /* Streamlit centers the button's inner flex wrapper; left-align it so every
               icon sits in the same gutter and labels start on a shared left edge. */
            section[data-testid="stSidebar"] .stButton > button > div {
                justify-content: flex-start !important;
                width: 100% !important;
            }
            section[data-testid="stSidebar"] .stButton > button:hover,
            section[data-testid="stSidebar"] .stButton > button:hover * {
                color: #f1f5f9 !important;
                -webkit-text-fill-color: #f1f5f9 !important;
                fill: #f1f5f9 !important;
            }
            section[data-testid="stSidebar"] .stButton > button:hover {
                background-color: rgba(148, 163, 184, 0.12) !important;
                border-color: transparent !important;
            }

            /* Active item (primary button): teal tint + left accent bar + teal text. */
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"],
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] * {
                color: #5eead4 !important;
                -webkit-text-fill-color: #5eead4 !important;
                fill: #5eead4 !important;
            }
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"] {
                background-color: rgba(45, 212, 191, 0.14) !important;
                border-color: transparent !important;
                font-weight: 600 !important;
                box-shadow: inset 3px 0 0 0 #2dd4bf !important;
            }
            section[data-testid="stSidebar"] .stButton > button[data-testid="stBaseButton-primary"]:hover {
                background-color: rgba(45, 212, 191, 0.20) !important;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<p class='vs-nav-eyebrow'>Navigation</p>", unsafe_allow_html=True)

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
