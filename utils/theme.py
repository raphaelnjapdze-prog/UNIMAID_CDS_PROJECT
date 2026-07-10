# =========================================================================
# DESIGN SYSTEM FOUNDATION & STYLING CORE (utils/theme.py)
# =========================================================================
import streamlit as st

# Core palette — refined scientific/health aesthetic
COLORS = {
    "primary":        "#0C4A6E",   # deep ocean blue — authority, trust
    "primary_light":  "#0EA5E9",   # accent actions
    "surface":        "#FFFFFF",
    "surface_alt":    "#F8FAFC",
    "border":         "#E2E8F0",
    "text_primary":   "#0F172A",
    "text_secondary": "#64748B",

    # Risk semantic scale — keep consistent everywhere (map, tables, badges)
    "risk_critical":  "#DC2626",
    "risk_high":      "#EA580C",
    "risk_moderate":  "#D97706",
    "risk_low":       "#16A34A",

    # SDG brand colors (official UN color standards)
    "sdg_health":     "#4C9F38",
    "sdg_water":      "#26BDE2",
    "sdg_cities":     "#DA3A23",
}

# Layout constraints
SPACING = [4, 8, 12, 16, 24, 32, 48, 64]
RADIUS  = {"sm": "6px", "md": "10px", "lg": "16px"}
FONT    = "'Inter', -apple-system, sans-serif"

def inject_global_theme():
    """Injects the unified design token matrix and hides native file routing elements."""
    st.markdown(f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

        html, body, [class*="css"], .stMarkdown, p, div, label {{
            font-family: {FONT} !important;
        }}

        .stApp {{
            background-color: {COLORS['surface_alt']};
            color: {COLORS['text_primary']};
        }}

        /*  CRITICAL: Suppresses the unprofessional native sidebar file browser list */
        [data-testid="stSidebarNav"] {{
            display: none !important;
        }}

        /* Ensure the top header canvas leaves clean padding for our layout custom nav */
        [data-testid="stHeader"] {{
            background-color: rgba(0,0,0,0) !important;
        }}
        </style>
    """, unsafe_allow_html=True)
