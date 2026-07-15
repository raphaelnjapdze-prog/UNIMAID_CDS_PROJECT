# =========================================================================
# APPLICATION ENTRYPOINT ORCHESTRATOR (app.py)
# =========================================================================

import importlib

import streamlit as st

from utils.auth import restore_session
from utils.navigation import render_sidebar_nav
from utils.session_cookie import sync_refresh_cookie
from utils.theme import inject_global_theme

# 1. Page Configuration
st.set_page_config(
    page_title="Vector Sentinel Engine",
    page_icon="🦟",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. Design System Foundation Injection
inject_global_theme()

# 3. UI Sub-Component Layout Imports (Banners, Sidebars, Footers)
from utils.ui_components import (
    inject_global_dashboard_theme as apply_theme,
)
from utils.ui_components import (
    render_institutional_sidebar_header as render_banner,
)
from utils.ui_components import (
    render_system_footer,
)

# Execute additional structural layout themes
apply_theme()

# 4. Page routing — pages are imported ON DEMAND, not up front.
#
# Importing all fifteen at startup dragged in every page's dependencies whether or not
# the user ever opened that page: scikit-learn (1.6s, for the risk engine), google.genai
# (1.0s, for the Copilot), folium, plotly. Cold start was ~9s, paid on every container
# boot — and Streamlit Cloud reboots idle apps, so a field user waited it out.
#
# Each page now imports the first time it is opened and stays in sys.modules afterwards,
# so a revisit costs nothing. Only the login page is imported eagerly: it is what an
# unauthenticated visitor always renders.
from components.login import render_login_page

# page key (URL ?page=) -> "module:render function"
PAGE_MODULES = {
    "dashboard":   "components.dashboard:render_dashboard_page",
    "log":         "components.site_log:render_site_log_page",
    "ai":          "components.diagnostics:render_diagnostics_page",
    "trends":      "components.environmental_trends:render_environmental_trends_page",
    "copilot":     "components.copilot:render_copilot_page",
    "forecaster":  "components.forecasting:render_forecasting_page",
    "risk":        "components.predictions:render_predictions_page",
    "correlation": "components.correlation:render_correlation_page",
    "lab":         "components.lab_pcr:render_lab_pcr_page",
    "bioassay":    "components.bioassay_entry:render_bioassay_entry_page",
    "case_entry":  "components.clinical_case_entry:render_clinical_case_entry_page",
    "retraining":  "components.retraining:render_retraining_page",
    "reports":     "components.reports:render_reports_page",
    "profile":     "components.profile:render_profile_page",
}


def _render_page(page_key: str) -> None:
    """Import the page's module on first use and render it."""
    module_path, function_name = PAGE_MODULES[page_key].split(":")
    module = importlib.import_module(module_path)
    getattr(module, function_name)()

# 5. Session State Initialization & Verified Session Restore
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

# Restore a prior session ONLY by re-validating the stored Supabase tokens
# against the auth server — never by trusting a URL flag. See
# utils.auth.restore_session for the security rationale.
if not st.session_state["authenticated"]:
    restore_session()

# Keep the refresh-token cookie in step with the session: written on login (so a browser
# reload can restore the session instead of dumping the user at the login screen) and
# cleared on sign-out. Runs before the auth gate below, so the sign-out case — which
# returns early — still clears the cookie.
sync_refresh_cookie(st.session_state.get("sb_refresh_token"))

def main():
    # Enforce strict authentication gate security boundary. A real Supabase login (or a
    # revalidated restore_session) is the only way past this — the old Guest Explorer flag
    # let an unauthenticated visitor through, which on a public Streamlit Cloud URL meant
    # anyone with the link was inside the app.
    if not st.session_state["authenticated"]:
        render_login_page()
        return

    # One product, one name. This header read "National Integrated Vector Surveillance
    # System" — a claim to be a national system that nothing supports, and a third name
    # for the app after the login page's and the sidebar's.
    st.markdown("""
        <div style="text-align: center; padding: 10px 0px 5px 0px;">
            <h2 style="color: #0369a1; margin: 0; font-weight: 700;">Vector Sentinel Engine</h2>
        </div>
    """, unsafe_allow_html=True)

    # Read active query parameter state directly from browser canvas location
    url_params = st.query_params
    query_page = url_params.get("page", "dashboard")

    if query_page not in PAGE_MODULES:
        query_page = "dashboard"

    # Brand header first so it sits at the TOP of the sidebar, above the nav.
    render_banner()

    # Render sidebar navigation
    render_sidebar_nav(query_page)

    _render_page(query_page)

    render_system_footer()

if __name__ == "__main__":
    main()
