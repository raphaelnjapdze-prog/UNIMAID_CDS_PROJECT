# =========================================================================
# APPLICATION ENTRYPOINT ORCHESTRATOR (app.py)
# =========================================================================

import streamlit as st

from utils.auth import restore_session
from utils.navigation import render_sidebar_nav
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

# 3. Dynamic UI Sub-Component Layout Imports (Banners, Sidebars, Footers)
try:
    from utils.ui_components import inject_global_dashboard_theme as apply_theme
except ImportError:
    try:
        from utils.ui_components import apply_custom_dashboard_theme as apply_theme
    except ImportError:
        def apply_theme(): pass

try:
    from utils.ui_components import render_institutional_sidebar_header as render_banner
except ImportError:
    try:
        from utils.ui_components import render_dashboard_banner as render_banner
    except ImportError:
        def render_banner(): pass

try:
    from utils.ui_components import render_system_footer
except ImportError:
    def render_system_footer(): pass

# Execute additional structural layout themes
apply_theme()

# 4. Core Page Component Imports
from components.bioassay_entry import render_bioassay_entry_page
from components.clinical_case_entry import render_clinical_case_entry_page
from components.copilot import render_copilot_page
from components.correlation import render_correlation_page
from components.dashboard import render_dashboard_page
from components.diagnostics import render_diagnostics_page
from components.environmental_trends import render_environmental_trends_page
from components.forecasting import render_forecasting_page
from components.lab_pcr import render_lab_pcr_page
from components.login import render_login_page
from components.multi_angle_capture import render_multi_angle_capture_page
from components.predictions import render_predictions_page
from components.profile import render_profile_page
from components.reports import render_reports_page
from components.retraining import render_retraining_page
from components.site_log import render_site_log_page

# ... (Keep your existing page configs and component imports completely identical)

# 5. Session State Initialization & Verified Session Restore
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "guest_explorer" not in st.session_state:
    st.session_state["guest_explorer"] = False

# Restore a prior session ONLY by re-validating the stored Supabase tokens
# against the auth server — never by trusting a URL flag. See
# utils.auth.restore_session for the security rationale.
if not st.session_state["authenticated"] and not st.session_state["guest_explorer"]:
    restore_session()

# Reverse mapping configuration linking URL keys directly to functional names
NAV_MAP = {
    "dashboard": "Surveillance Dashboard",
    "log":       "Site Log Entry",
    "ai":        "Advanced AI Diagnostics",
    "capture":   "Multi-Angle Capture",
    "trends":    "Global Change Trends",
    "copilot":   "WHO Entomology AI Copilot",
    "forecaster": "Historical Trends",
    "risk": "Resistance Status Prediction",
    "correlation": "Clinical Case Correlation",
    "lab":       "PCR Lab Confirmation",
    "bioassay":  "Bioassay Result Entry",
    "case_entry": "Clinical Case Data Entry",
    "retraining": "Local Retraining",
    "reports":   "Automated Reports",
    "profile":   "Investigator Profile",
}
def main():
    # Enforce strict authentication gate security boundary
    if not st.session_state["authenticated"] and not st.session_state["guest_explorer"]:
        render_login_page()
        return

    # Add system title header
    st.markdown("""
        <div style="text-align: center; padding: 10px 0px 5px 0px;">
            <h2 style="color: #0369a1; margin: 0; font-weight: 700;">National Integrated Vector Surveillance System</h2>
        </div>
    """, unsafe_allow_html=True)

    # Read active query parameter state directly from browser canvas location
    url_params = st.query_params
    query_page = url_params.get("page", "dashboard")

    if query_page not in NAV_MAP:
        query_page = "dashboard"

    current_active_page = NAV_MAP[query_page]

    # Render sidebar navigation
    render_sidebar_nav(query_page)

    # Render layout brand graphics and menus smoothly
    render_banner()

    # 6. Core Architectural Layout Routing Switches (SPA Architecture Engine)
    if current_active_page == "Surveillance Dashboard":
        render_dashboard_page()
    elif current_active_page == "Site Log Entry":
        render_site_log_page()
    elif current_active_page == "Advanced AI Diagnostics":
        render_diagnostics_page()
    elif current_active_page == "Multi-Angle Capture":
        render_multi_angle_capture_page()
    elif current_active_page == "Global Change Trends":
        render_environmental_trends_page()
    elif current_active_page == "WHO Entomology AI Copilot":
        render_copilot_page()
    elif current_active_page == "Historical Trends":
        render_forecasting_page()
    elif current_active_page == "Resistance Status Prediction":
        render_predictions_page()
    elif current_active_page == "Clinical Case Correlation":
        render_correlation_page()
    elif current_active_page == "PCR Lab Confirmation":
        render_lab_pcr_page()
    elif current_active_page == "Bioassay Result Entry":
        render_bioassay_entry_page()
    elif current_active_page == "Clinical Case Data Entry":
        render_clinical_case_entry_page()
    elif current_active_page == "Local Retraining":
        render_retraining_page()
    elif current_active_page == "Automated Reports":
        render_reports_page()
    elif current_active_page == "Investigator Profile":
        render_profile_page()

    render_system_footer()

if __name__ == "__main__":
    main()
