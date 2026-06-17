# =========================================================================
# INVESTIGATOR PROFILE & DATABASE TELEMETRY (components/profile.py)
# =========================================================================
import streamlit as st
from utils.auth_db import (
    _current_supabase_table_status,
    _attempt_create_supabase_table,
    sign_out_user
)
from utils.data_manager import (
    _current_user_display_name,
    _current_user_security_notice,
    _get_current_user_email,
    _get_current_user_id
)

def render_profile_page():
    """Renders the investigator profile settings and database infrastructure status."""
    
    st.markdown("## 🛡️ Investigator Profile & Node Configuration")
    st.markdown("---")
    
    # Session Details Section
    st.subheader("Investigator Credentials")
    
    col1, col2 = st.columns(2)
    with col1:
        st.info(f"**Current Identity:**\n{_current_user_display_name()}")
        st.text(f"Authorized Email: {_get_current_user_email() or 'N/A'}")
    with col2:
        st.info(f"**Session Identifier:**\n{_get_current_user_id() or 'guest-session'}")
        if st.session_state.get("login_time"):
            st.text(f"Node Authorization Time: {st.session_state['login_time'].strftime('%Y-%m-%d %H:%M:%S')}")
            
    # Context-aware security status readout
    _current_user_security_notice()
    
    st.markdown("---")
    
    # Infrastructure Database Telemetry Section
    st.subheader("Cloud Infrastructure Sync Telemetry")
    status_message = _current_supabase_table_status()
    
    if "ready" in status_message.lower():
        st.success(status_message)
    elif "missing" in status_message.lower():
        st.error(status_message)
        
        # Admin utility hook if tables need initialization
        if st.session_state.get("auth_user_id") == "local-admin" or _get_current_user_email() == "system@unimaid.edu.ng":
            st.markdown("### 🛠️ Administrative Node Initialization")
            st.write("Construct structural remote storage arrays matching the core relational dataset models.")
            if st.button("Initialize Remote Database Schema"):
                with st.spinner("Provisioning cloud tables..."):
                    if _attempt_create_supabase_table():
                        st.success("Database arrays initialized perfectly. Reloading system matrix.")
                        st.rerun()
                    else:
                        st.error("Failed to construct remote tables. Verify API permissions or execute SQL migration raw.")
    else:
        st.warning(status_message)
        
    st.markdown("---")
    
    # Safe Session Demobilization
    st.subheader("Portal Demobilization")
    st.write("Terminate your current encrypted surveillance session and return to the main security checkpoint gate.")
    
    if st.button("Secure Logout & Terminate Session", type="primary"):
        sign_out_user()
        st.success("Session context cleared safely.")
        st.rerun()