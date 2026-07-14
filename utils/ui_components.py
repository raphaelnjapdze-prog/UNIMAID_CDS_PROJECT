# =========================================================================
# SYSTEM UI STYLING & BRANDING ENGINE (utils/ui_components.py)
# =========================================================================
import streamlit as st


def inject_global_dashboard_theme():
    """
    Injects custom CSS to override standard Streamlit element layouts,
    providing high-contrast metric borders, styled forms, and crisp dividers.
    """
    custom_css = """
    <style>
        /* Optimize block layout padding */
        .main .block-container {
            padding-top: 1.8rem;
            padding-bottom: 3rem;
            max-width: 1200px;
        }

        /* Modernized Sidebar Aesthetics */
        [data-testid="stSidebar"] {
            background-color: #0f172a !important; /* Deep Navy Slate */
        }
        [data-testid="stSidebar"] * {
            color: #e2e8f0 !important;
        }
        [data-testid="stSidebar"] hr {
            border-color: #334155 !important;
        }

        /* Custom Section Underlines for H2 elements */
        h2 {
            color: #0d9488 !important; /* Medical Teal Accent */
            font-weight: 700 !important;
            border-bottom: 2px solid #e2e8f0;
            padding-bottom: 0.4rem;
            margin-top: 1.2rem;
            margin-bottom: 1rem;
        }

        /* High-Contrast Analytical Metric Cards */
        [data-testid="stMetricBlock"] {
            background-color: #ffffff !important;
            border: 1px solid #e2e8f0 !important;
            border-left: 6px solid #0d9488 !important; /* Structural Teal Spine */
            border-radius: 8px !important;
            padding: 1rem 1.2rem !important;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05) !important;
            transition: transform 0.15s ease, box-shadow 0.15s ease !important;
        }
        [data-testid="stMetricBlock"]:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.08) !important;
        }

        /* Styled Input Forms */
        [data-testid="stForm"] {
            border: 1px solid #e2e8f0 !important;
            background-color: #f8fafc !important; /* Off-white surface background */
            border-radius: 8px !important;
            padding: 1.5rem !important;
            box-shadow: inset 0 1px 2px rgba(0,0,0,0.02) !important;
        }

        /* Polished UI Buttons */
        .stButton > button {
            border-radius: 6px !important;
            font-weight: 500 !important;
            transition: all 0.2s ease;
        }

        /* Custom Status Callout Padding */
        .stAlert {
            border-radius: 6px !important;
            border: none !important;
            border-left: 4px solid rgba(0,0,0,0.2) !important;
        }
    </style>
    """
    st.markdown(custom_css, unsafe_allow_html=True)

def render_institutional_sidebar_header():
    """Product identity at the top of the navigation pane.

    Says the same thing as the login page. It previously read "VECTRA EDGE" — a product
    name that appears nowhere else — over "UNIMAID Research Node Node-01", so the sidebar
    and the login screen named two different systems.
    """
    with st.sidebar:
        st.markdown(
            "<div style='margin-top: -1.5rem; padding-bottom: 0.5rem;'>"
            "<h2 style='color: #2dd4bf !important; margin: 0; font-size: 1.3rem; "
            "border-bottom: none !important;'>Vector Sentinel Engine</h2>"
            "<p style='font-size: 0.78rem; color: #94a3b8 !important; margin: 3px 0 0 0; "
            "line-height: 1.35;'>Malaria vector surveillance</p></div>",
            unsafe_allow_html=True
        )
        st.markdown("---")

def render_system_footer():
    """Appends a clear, secure computational footer statement at the base of the page layout."""
    st.markdown("---")
    st.markdown(
        "<div style='text-align: center; font-size: 0.75rem; color: #94a3b8; padding: 1rem 0;'>"
        "Authorized Personnel Only • Dynamic Data Sync: Active • Compliance: WHO Ethical AI Guidelines Implemented"
        "</div>",
        unsafe_allow_html=True
    )
