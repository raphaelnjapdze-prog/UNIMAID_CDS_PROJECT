# =========================================================================
# INSTITUTIONAL VECTOR ICON REGISTRY (utils/icons.py)
# =========================================================================
import streamlit as st

from utils.theme import COLORS


def icon(name: str, size: int = 20, color: str = None) -> str:
    """
    Generates an inline SVG vector icon using crisp, production-grade Lucide blueprints.
    Guarantees cross-platform layout rendering uniformity across all server states.
    """
    # Fallback to design system primary color if not explicitly defined
    if color is None:
        color = COLORS.get("primary", "#0C4A6E")

    # Validated, pure geometric stroke paths extracted from lucide.dev
    icons = {
        "dashboard": '<rect width="7" height="9" x="3" y="3" rx="1"/><rect width="7" height="5" x="14" y="3" rx="1"/><rect width="7" height="9" x="14" y="12" rx="1"/><rect width="7" height="5" x="3" y="16" rx="1"/>',
        "diagnostics": '<path d="M6 18h8"/><path d="M3 22h18"/><path d="M14 22a7 7 0 1 0-14 0"/><path d="M14 14h2"/><path d="M12 11h4"/><path d="M14 12V6a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v6a1 1 0 0 1-1 1h-4a1 1 0 0 1-1-1z"/><path d="M12 2v2"/>',
        "trends": '<path d="M22 12h-4l-3 9L9 3l-3 9H2"/>',
        "copilot": '<path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/>',
        "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" x2="12" y1="3" y2="15"/>',
        "reports": '<path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"/><path d="M14 2v4a2 2 0 0 0 2 2h4"/><path d="M10 9H8"/><path d="M16 13H8"/><path d="M16 17H8"/>',
        "forecaster": '<path d="M8 2v4"/><path d="M16 2v4"/><rect width="18" height="18" x="3" y="4" rx="2"/><path d="M3 10h18"/>',
        "risk": '<path d="M20 13c0 5-3.5 7.5-7.66 9.7a1 1 0 0 1-.68 0C7.5 20.5 4 18 4 13V6a1 1 0 0 1 .76-.97l8-2a1 1 0 0 1 .48 0l8 2A1 1 0 0 1 20 6v7z"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>',
        "correlation": '<path d="M18 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3ZM6 3a3 3 0 0 0-3 3v12a3 3 0 0 0 3 3 3 3 0 0 0 3-3V6a3 3 0 0 0-3-3Z"/><path d="M12 6v12"/>',
        "profile": '<path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/>',
        "lab": '<path d="M14 2v6"/><path d="M10 8h8"/><path d="M14 8v12"/><path d="M6 20h16"/><path d="M10 14h8"/>',
        "retraining": '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.26L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.26L3 16"/><path d="M3 21v-5h5"/>',
        "alert": '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" x2="12" y1="9" y2="13"/><line x1="12" x2="12.01" y1="17" y2="17"/>',
        "info": '<circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/>'
    }

    inner_path = icons.get(name, icons["info"])
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'stroke="{color}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
        f'style="display: inline-block; vertical-align: middle; line-height: 1;">'
        f'{inner_path}</svg>'
    )

def render_page_header(title: str, icon_name: str, caption: str = None):
    """Renders a standardized institutional header block containing a crisp vector icon layout."""
    icon_html = icon(icon_name, size=28, color=COLORS["primary"])
    st.markdown(
        f"""
        <div style="display: flex; align-items: center; gap: 12px; margin-top: 10px; margin-bottom: 4px;">
            <div style="display: flex; align-items: center;">{icon_html}</div>
            <h1 style="margin: 0; font-size: 2.0rem; color: {COLORS['primary']}; font-weight: 700; line-height: 1.2;">
                {title}
            </h1>
        </div>
        """,
        unsafe_allow_html=True
    )
    if caption:
        st.markdown(
            f'<p style="color: {COLORS["text_secondary"]}; font-size: 0.95rem; margin-top: 2px; margin-bottom: 24px;">'
            f'{caption}'
            f'</p>',
            unsafe_allow_html=True
        )
