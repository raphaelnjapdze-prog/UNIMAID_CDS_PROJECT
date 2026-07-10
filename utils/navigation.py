# =========================================================================
# ENTERPRISE PRODUCT NAVIGATION INTERFACE (utils/navigation.py)
# =========================================================================
import streamlit as st
from utils.theme import COLORS
from utils.icons import icon

def render_sidebar_nav(active: str):
    """Renders a collapsible sidebar navigation with all page links."""
    
    # Format: (Query Parameter ID, Label Text, Lucide Icon Identifier)
    pages = [
        ("dashboard", "Command Center", "dashboard"),
        ("log",       "Site Log Entry", "log"),
        ("ai",        "AI Diagnostics", "diagnostics"),
        ("trends",    "Change Trends", "trends"),
        ("copilot",   "AI Copilot", "copilot"),
        ("forecaster", "Seasonal Forecast", "forecaster"),
        ("risk",      "Risk Engine", "risk"),
        ("correlation", "Correlations", "correlation"),
        ("lab",       "PCR Lab", "lab"),
        ("bioassay",  "Bioassay Entry", "lab"),
        ("case_entry", "Clinical Case Entry", "correlation"),
        ("retraining", "Retraining", "retraining"),
        ("reports",   "Reports", "reports"),
        ("profile",   "Profile", "profile"),
    ]
    
    with st.sidebar:
        st.markdown("""
            <style>
            .sidebar-nav-item { padding: 10px 0px; }
            .sidebar-nav-item a { 
                display: flex;
                align-items: center;
                gap: 10px;
                padding: 10px 12px;
                border-radius: 6px;
                text-decoration: none;
                font-weight: 600;
                font-size: 14px;
                transition: all 0.15s ease;
            }
            .sidebar-nav-item a.active {
                background: """ + COLORS['primary'] + """;
                color: #FFFFFF;
            }
            .sidebar-nav-item a:hover {
                background: """ + COLORS['surface_alt'] + """;
                color: """ + COLORS['primary'] + """;
            }
            .nav-icon { display: flex; align-items: center; }
            </style>
        """, unsafe_allow_html=True)
        
        st.markdown("Navigation")
        st.markdown("---")
        
        for key, label, icon_name in pages:
            is_active = key == active
            active_class = "active" if is_active else ""
            
            icon_color = "#FFFFFF" if is_active else COLORS["text_secondary"]
            svg_icon = icon(icon_name, size=16, color=icon_color)
            
            nav_link = f'<a class="{active_class}" href="/?page={key}" target="_self"><span class="nav-icon">{svg_icon}</span>{label}</a>'
            st.markdown(f'<div class="sidebar-nav-item">{nav_link}</div>', unsafe_allow_html=True)

def render_top_nav(active: str):
    """Renders a persistent, app-like top navigation block driving URL query strings."""
    
    # Format: (Query Parameter ID, Label Text, Lucide Icon Identifier)
    pages = [
        ("dashboard", "Command Center", "dashboard"),
        ("log",       "Site Log Entry", "log"),
        ("ai",        "AI Diagnostics", "diagnostics"),
        ("trends",    "Change Trends", "trends"),
        ("copilot",   "AI Copilot", "copilot"),
        ("forecaster", "Seasonal Forecast", "forecaster"),
        ("risk",      "Risk Engine", "risk"),
        ("correlation", "Correlations", "correlation"),
        ("lab",       "PCR Lab", "lab"),
        ("bioassay",  "Bioassay Entry", "lab"),
        ("case_entry", "Clinical Case Entry", "correlation"),
        ("retraining", "Retraining", "retraining"),
        ("reports",   "Reports", "reports"),
        ("profile",   "Profile", "profile"),
    ]
    
    tabs_html = ""
    for key, label, icon_name in pages:
        is_active = key == active
        active_class = "active" if is_active else ""
        
        icon_color = "#FFFFFF" if is_active else COLORS["text_secondary"]
        svg_icon = icon(icon_name, size=15, color=icon_color)

        tabs_html += f'<a class="nav-tab {active_class}" href="/?page={key}" target="_self"><span class="nav-icon">{svg_icon}</span>{label}</a>'

    st.markdown(f"""
    <style>
    .nav-bar {{ display: flex; align-items: center; flex-wrap: wrap; gap: 6px; padding: 10px 14px; background-color: {COLORS['surface']}; border-bottom: 1px solid {COLORS['border']}; margin-bottom: 20px; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
    .nav-tab {{ display: flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: 6px; font-weight: 600; font-size: 13px; color: {COLORS['text_secondary']}; text-decoration: none; transition: all 0.15s ease; }}
    .nav-tab.active {{ background: {COLORS['primary']}; color: #FFFFFF !important; }}
    .nav-tab:hover:not(.active) {{ background: {COLORS['surface_alt']}; color: {COLORS['primary']}; }}
    .nav-icon {{ display: flex; align-items: center; }}
    </style>
    <div class="nav-bar">{tabs_html}</div>
    """, unsafe_allow_html=True)