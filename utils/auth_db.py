# =========================================================================
# AUTHENTICATION & DATABASE CORE UTILITIES (utils/auth_db.py)
# =========================================================================
import streamlit as st
from datetime import datetime
from utils.config import (
    SUPABASE_CLIENT,
    SUPABASE_ENABLED,
    SUPABASE_SERVICE_CLIENT,
    SUPABASE_TABLE,
    ADMIN_USERNAME,
    ADMIN_EMAIL,
    ADMIN_PASSWORD
)

def get_supabase_client():
    return SUPABASE_CLIENT if SUPABASE_ENABLED else None


def get_supabase_service_client():
    return SUPABASE_SERVICE_CLIENT


def supabase_user():
    client = get_supabase_client()
    if client is None:
        return None
    try:
        user_response = client.auth.get_user()
        return getattr(user_response, "user", None) or user_response
    except Exception:
        return None


def _supabase_table_exists(table_name: str) -> bool:
    client = get_supabase_service_client() or get_supabase_client()
    if client is None:
        return False
    try:
        client.table(table_name).select("*").limit(1).execute()
        return True
    except Exception:
        return False


def _current_supabase_table_status() -> str:
    if not SUPABASE_ENABLED:
        return "Supabase is not configured. Provide SUPABASE_URL and SUPABASE_ANON_KEY using the platform Secrets Management console or local .env for development."
    if _supabase_table_exists(SUPABASE_TABLE):
        return f"Cloud table '{SUPABASE_TABLE}' exists and is ready."
    if get_supabase_service_client() is None:
        return f"Cloud table '{SUPABASE_TABLE}' is missing. Add SUPABASE_SERVICE_ROLE_KEY to allow service-level creation checks."
    return f"Cloud table '{SUPABASE_TABLE}' is missing. Use the admin helper below to create it if your Supabase project supports the SQL RPC helper."


def _attempt_create_supabase_table() -> bool:
    if not SUPABASE_ENABLED or get_supabase_service_client() is None:
        return False
    create_sql = """
        CREATE TABLE IF NOT EXISTS campus_audit_data (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            Survey_Date date NOT NULL,
            Zone_ID text NOT NULL,
            Zone_Name text NOT NULL,
            Latitude double precision,
            Longitude double precision,
            Base_Larval_Count integer,
            Anopheles_Count integer,
            Culex_Count integer,
            Aedes_Count integer,
            Breeding_Sites_Identified integer,
            PyResistance_Detected text,
            OpResistance_Detected text,
            Last_Intervention_Days_Ago integer,
            Temperature_C double precision,
            Humidity_Pct integer,
            Salinity_ppt double precision,
            Water_pH double precision,
            Dissolved_Oxygen_mgL double precision,
            NDVI_Canopy double precision,
            owner_email text,
            owner_id text,
            created_at timestamptz DEFAULT now()
        );
    """
    try:
        get_supabase_service_client().rpc("sql", {"sql": create_sql}).execute()
        return _supabase_table_exists(SUPABASE_TABLE)
    except Exception:
        return False


def set_authenticated(user, provider="supabase"):
    st.session_state["authenticated"] = True
    st.session_state["guest_explorer"] = False
    st.session_state["auth_provider"] = provider
    if isinstance(user, dict):
        st.session_state["auth_user_email"] = user.get("email")
        st.session_state["auth_user_id"] = user.get("id")
        st.session_state["auth_user_name"] = user.get("user_metadata", {}).get("full_name") or user.get("full_name")
    else:
        st.session_state["auth_user_email"] = getattr(user, "email", None)
        st.session_state["auth_user_id"] = getattr(user, "id", None)
        metadata = getattr(user, "user_metadata", None) or {}
        st.session_state["auth_user_name"] = metadata.get("full_name")
    st.session_state["login_time"] = datetime.now()


def sign_in_user(email: str, password: str):
    client = get_supabase_client()
    if client:
        return client.auth.sign_in_with_password({"email": email, "password": password})
    if (email.strip().lower() == ADMIN_USERNAME or email.strip().lower() == ADMIN_EMAIL.lower()) and password == ADMIN_PASSWORD:
        return {"user": {"email": ADMIN_EMAIL, "id": "local-admin", "user_metadata": {"full_name": "Administrator"}}}
    return None


def sign_up_user(email: str, password: str, full_name: str):
    client = get_supabase_client()
    if client:
        return client.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"full_name": full_name}},
        })
    return None


def sign_out_user():
    client = get_supabase_client()
    if client:
        try:
            client.auth.sign_out()
        except Exception:
            pass
    st.session_state["authenticated"] = False
    st.session_state["guest_explorer"] = False
    st.session_state["auth_provider"] = "local"
    st.session_state["auth_user_email"] = None
    st.session_state["auth_user_id"] = None
    st.session_state["auth_user_name"] = None
    st.session_state["current_page"] = "dashboard"