# =========================================================================
# APPLICATION ENTRYPOINT ORCHESTRATOR (main.py - Full Deployment)
# =========================================================================
import streamlit as st

# Initialize essential state management keys prior to page draws
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "guest_explorer" not in st.session_state:
    st.session_state["guest_explorer"] = False
if "current_page" not in st.session_state:
    st.session_state["current_page"] = "dashboard"

# Import component rendering wrappers safely
from components.login import render_login_page
from components.dashboard import render_dashboard_page
from components.diagnostics import render_diagnostics_page
from components.environmental_trends import render_environmental_trends_page
from components.copilot import render_copilot_page            # Integrated Import
from components.upload import render_upload_page
from components.profile import render_profile_page

st.set_page_config(
    page_title="UNIMAID Vector Sentinel Engine",
    page_icon="🦟",
    layout="wide",
    initial_sidebar_state="expanded"
)

def main():
    # Enforce authentication gate boundary
    if not st.session_state["authenticated"] and not st.session_state["guest_explorer"]:
        render_login_page()
        return

    st.sidebar.title("Navigation Hub")
    
    # Render unified interactive navigation deck
    page_selection = st.sidebar.radio(
        "Navigate Workspace",
        [
            "Surveillance Dashboard", 
            "Advanced AI Diagnostics", 
            "Global Change Trends",
            "WHO Entomology AI Copilot",   # Added navigation node option
            "Ingest Field Logs", 
            "Investigator Profile"
        ],
        index=(
            0 if st.session_state["current_page"] == "dashboard" 
            else 1 if st.session_state["current_page"] == "diagnostics"
            else 2 if st.session_state["current_page"] == "environmental"
            else 3 if st.session_state["current_page"] == "copilot"
            else 4 if st.session_state["current_page"] == "upload"
            else 5
        )
    )

    # Orchestrate active workspace layout switches
    if page_selection == "Surveillance Dashboard":
        st.session_state["current_page"] = "dashboard"
        render_dashboard_page()
    elif page_selection == "Advanced AI Diagnostics":
        st.session_state["current_page"] = "diagnostics"
        render_diagnostics_page()
    elif page_selection == "Global Change Trends":
        st.session_state["current_page"] = "environmental"
        render_environmental_trends_page()
    elif page_selection == "WHO Entomology AI Copilot":  # Routing bridge logic
        st.session_state["current_page"] = "copilot"
        render_copilot_page()
    elif page_selection == "Ingest Field Logs":
        st.session_state["current_page"] = "upload"
        render_upload_page()
    elif page_selection == "Investigator Profile":
        st.session_state["current_page"] = "profile"
        render_profile_page()

if __name__ == "__main__":
    main()