# =========================================================================
# STANDARD GLOBAL IMPORTS & CONFIGURATIONS (utils/config.py)
# =========================================================================
import os

import streamlit as st
from dotenv import load_dotenv

# Clean imports from the modern SDK
from supabase import create_client

from utils.logging_config import get_logger

logger = get_logger(__name__)

# 1. Look for and load local hidden .env file
load_dotenv()

def get_secret(key: str, default=None):
    if hasattr(st, "secrets") and st.secrets is not None:
        try:
            secret_value = st.secrets.get(key)
            if secret_value:
                return secret_value
        except Exception:
            logger.debug("st.secrets lookup for %r failed; falling back to env", key, exc_info=True)
    return os.getenv(key, default)

# --- GLOBAL CREDENTIALS & SCM CONSTANTS ---
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
SUPABASE_SERVICE_ENABLED = bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)

# Supabase clients are built lazily on first use rather than at import time, so
# importing this module — and therefore the whole app — never depends on
# credentials being present and stays cheap to import/test. Each client is
# created once and cached.
_supabase_client = None
_supabase_service_client = None


def get_base_supabase_client():
    """Anon Supabase client, created once on first use. None if not configured."""
    global _supabase_client
    if not SUPABASE_ENABLED:
        return None
    if _supabase_client is None:
        _supabase_client = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
    return _supabase_client


def get_service_supabase_client():
    """Service-role Supabase client, created once on first use. None if not configured."""
    global _supabase_service_client
    if not SUPABASE_SERVICE_ENABLED:
        return None
    if _supabase_service_client is None:
        _supabase_service_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    return _supabase_service_client
UPLOAD_DIR = "uploaded_field_sheets"

# --- LOCAL FALLBACK AUTHENTICATION CREDENTIAL SETTINGS ---
# Credentials must be supplied via secrets/env — never hardcoded. If
# ADMIN_PASSWORD is unset, the local-admin fallback login is disabled and
# only Supabase authentication is available.
ADMIN_USERNAME = get_secret("ADMIN_USERNAME", "admin")
ADMIN_EMAIL = get_secret("ADMIN_EMAIL", "admin@localhost")
ADMIN_PASSWORD = get_secret("ADMIN_PASSWORD")

# Ensure upload directory exists right away
if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# --- SYSTEM STATE BOOTSTRAPPING ENGINE ---
def initialize_auth_state():
    defaults = {
        "authenticated": False,
        "auth_provider": "local",
        "auth_user_email": None,
        "auth_user_id": None,
        "auth_user_name": None,
        "remember_me": False,
        "login_time": None,
        "current_page": "dashboard",
        "gemini_chat_history": [],
        "captcha_attempts": 0,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value
