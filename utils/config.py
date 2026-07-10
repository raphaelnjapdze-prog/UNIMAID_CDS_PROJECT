# =========================================================================
# STANDARD GLOBAL IMPORTS & CONFIGURATIONS (utils/config.py)
# =========================================================================
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
import plotly.express as px
import os
import io
from datetime import datetime, timedelta
from dotenv import load_dotenv
from supabase import create_client
# Clean imports from the modern SDK
from google import genai
from google.genai import types
import requests
import numpy as np
from PIL import Image
from scipy.stats import norm
import plotly.graph_objects as go
import json

# 1. Look for and load local hidden .env file
load_dotenv()

def get_secret(key: str, default=None):
    if hasattr(st, "secrets") and st.secrets is not None:
        try:
            secret_value = st.secrets.get(key)
            if secret_value:
                return secret_value
        except Exception:
            pass
    return os.getenv(key, default)

# --- GLOBAL CREDENTIALS & SCM CONSTANTS ---
GEMINI_API_KEY = get_secret("GEMINI_API_KEY")
SUPABASE_URL = get_secret("SUPABASE_URL")
SUPABASE_ANON_KEY = get_secret("SUPABASE_ANON_KEY")
SUPABASE_SERVICE_ROLE_KEY = get_secret("SUPABASE_SERVICE_ROLE_KEY")

SUPABASE_ENABLED = bool(SUPABASE_URL and SUPABASE_ANON_KEY)
SUPABASE_CLIENT = create_client(SUPABASE_URL, SUPABASE_ANON_KEY) if SUPABASE_ENABLED else None
SUPABASE_SERVICE_CLIENT = (
    create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY
    else None
)
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
        "guest_explorer": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value