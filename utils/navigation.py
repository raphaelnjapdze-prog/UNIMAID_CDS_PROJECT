# =========================================================================
# PRODUCT NAVIGATION INTERFACE (utils/navigation.py)
# =========================================================================
import streamlit as st

# Page registry: (query-param id, label, icon emoji)
_PAGES = [
    ("dashboard", "Command Center", "🧭"),
    ("log", "Site Log Entry", "📝"),
    ("ai", "AI Diagnostics", "🔬"),
    ("capture", "Multi-Angle Capture", "📸"),
    ("trends", "Change Trends", "📈"),
    ("copilot", "AI Copilot", "🤖"),
    ("forecaster", "Seasonal Forecast", "📅"),
    ("risk", "Risk Engine", "🚨"),
    ("correlation", "Correlations", "🔗"),
    ("lab", "PCR Lab", "🧪"),
    ("bioassay", "Bioassay Entry", "🧫"),
    ("case_entry", "Clinical Case Entry", "📋"),
    ("retraining", "Retraining", "🔁"),
    ("reports", "Reports", "📄"),
    ("profile", "Profile", "👤"),
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
        # Left-align button labels so they read as nav items, not centered CTAs.
        st.markdown(
            "<style>section[data-testid='stSidebar'] .stButton button "
            "{ justify-content: flex-start; font-weight: 600; }</style>",
            unsafe_allow_html=True,
        )
        st.markdown("Navigation")
        st.markdown("---")

        for key, label, emoji in _PAGES:
            is_active = key == active
            clicked = st.button(
                label,
                key=f"nav_{key}",
                icon=emoji,
                use_container_width=True,
                type="primary" if is_active else "secondary",
            )
            if clicked and not is_active:
                st.query_params["page"] = key
                st.rerun()
