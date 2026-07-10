"""
Data Management & Persistence Layer (utils/data_manager.py)

Scope, deliberately narrow:
  1. User identity passthrough (delegates to utils.auth — no duplicate logic)
  2. Specimen photo upload to Supabase Storage
  3. Site log entry persistence — the single-entry-with-photo form writes here
  4. Loading specimen_records for pages that need the full ledger
  5. Supabase schema/table status helpers (used by the Profile page)

Everything that used to fabricate species identifications, satellite data,
or AI briefings has been removed from this file. Real versions of those
concerns live in utils/morphology_keys.py, utils/vision_inference.py, and
utils/ai_advisory.py — this file does not duplicate them.

specimen_records is the single table backing this entire app: diagnostics
saves, PCR confirmation, accuracy reporting, the dashboard, and site log
entries all read/write the same table. There is no separate local-CSV or
campus_audit_data fallback path — if Supabase isn't configured, functions
here return None/empty and the caller must show an honest "not connected"
state rather than silently substituting fake data.
"""

import json
import uuid
from datetime import datetime, date, timezone

import pandas as pd
import streamlit as st

from utils.auth import (
    get_supabase_client,
    get_supabase_service_client,
    get_current_user_email,
    get_current_user_id,
)

# =============================================================================
# COMPATIBILITY SHIMS — several pages still call these old names.
# These redirect to the real, current implementation rather than the deleted
# fabricated versions. IMPORTANT: this only fixes the ImportError. Pages
# built against the old schema (Base_Larval_Count, Temperature_C,
# Satellite_LST, etc.) will still get a DataFrame with none of those
# columns — they need individual review, not just this shim.
# =============================================================================
def _load_master_df():
    return load_specimen_records()


def _current_user_display_name() -> str:
    from utils.auth import get_display_name
    return get_display_name()


def _current_user_security_notice():
    from utils.auth import get_supabase_client
    if get_supabase_client() is not None:
        st.success("Connected to Supabase — row-level security active for your account.")
    else:
        st.warning("Running without a Supabase connection. Data is not being persisted centrally.")
# =============================================================================
# 1. IDENTITY — thin passthrough, no duplicate logic
# =============================================================================
# utils.auth is the single source of truth for identity. Re-exported here
# only so existing call sites that import from utils.data_manager don't
# break; new code should import directly from utils.auth.
def get_current_user_email_():
    return get_current_user_email()


def get_current_user_id_():
    return get_current_user_id()


# =============================================================================
# 2. SPECIMEN PHOTO UPLOAD
# =============================================================================
def upload_specimen_photo(uploaded_file, specimen_id: str) -> str | None:
    """
    Uploads a field photo to the specimen-photos Supabase Storage bucket and
    returns its public URL. Returns None on failure — caller must warn the
    user, not silently drop the photo.
    """
    client = get_supabase_client()
    if client is None or uploaded_file is None:
        return None
    try:
        file_bytes = uploaded_file.getvalue()
        ext = uploaded_file.name.split(".")[-1] if "." in uploaded_file.name else "jpg"
        path = f"{specimen_id}/{uuid.uuid4()}.{ext}"
        client.storage.from_("specimen-photos").upload(
            path, file_bytes, {"content-type": uploaded_file.type or "image/jpeg"}
        )
        return client.storage.from_("specimen-photos").get_public_url(path)
    except Exception as e:
        st.warning(f"Photo upload failed, entry will be saved without it: {e}")
        return None


# =============================================================================
# 3. SITE LOG ENTRY — replaces the old CSV upload path entirely
# =============================================================================
def submit_site_log_entry(
    collection_date: date,
    breeding_site_type: str,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    anopheles_count: int = 0,
    culex_count: int = 0,
    aedes_count: int = 0,
    other_genera_count: int = 0,
    field_notes: str = "",
    photo_file=None,
) -> dict | None:
    """
    Saves one field survey observation directly to specimen_records. This is
    a raw count log, not a species identification claim — it's tagged
    screening_method="manual_field_log" so it correctly stays out of the
    genus/accuracy reporting built for actual identification results.

    Returns the inserted row on success, or None if Supabase isn't
    configured or the insert failed. Caller must show an honest error,
    never a fake success message.
    """
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this entry cannot be saved.")
        return None

    specimen_id = str(uuid.uuid4())
    photo_url = upload_specimen_photo(photo_file, specimen_id) if photo_file else None

    record = {
        "specimen_id": specimen_id,
        "collection_date": collection_date.isoformat(),
        "collector_id": get_current_user_id(),
        "gps_lat": gps_lat,
        "gps_lon": gps_lon,
        "breeding_site_type": breeding_site_type,
        "photo_urls": [photo_url] if photo_url else [],
        "field_screening_result": {
            "screening_method": "manual_field_log",
            "result": {
                "anopheles_count": int(anopheles_count),
                "culex_count": int(culex_count),
                "aedes_count": int(aedes_count),
                "other_genera_count": int(other_genera_count),
                "field_notes": field_notes,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "pcr_status": "not_submitted",
    }

    try:
        response = client.table("specimen_records").insert(record).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Could not save site log entry: {e}")
        return None


# =============================================================================
# 4. LOADING — single source of truth for reading the ledger
# =============================================================================
@st.cache_data(ttl=60, show_spinner=False)
def load_specimen_records() -> pd.DataFrame:
    """
    Loads all specimen_records from Supabase. Returns an empty DataFrame —
    never fabricated rows — if Supabase isn't configured or the table has
    no data yet.
    """
    client = get_supabase_client()
    if client is None:
        return pd.DataFrame()
    try:
        response = client.table("specimen_records").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Could not load specimen records: {e}")
    return pd.DataFrame()


def clear_specimen_records_cache():
    """Call after any write, so the next load_specimen_records() reflects it."""
    load_specimen_records.clear()


# =============================================================================
# 5. SCHEMA / TABLE STATUS — used by the Profile page's Security tab
# =============================================================================
SPECIMEN_TABLE = "specimen_records"


def supabase_table_exists() -> bool:
    client = get_supabase_service_client() or get_supabase_client()
    if client is None:
        return False
    try:
        client.table(SPECIMEN_TABLE).select("specimen_id").limit(1).execute()
        return True
    except Exception:
        return False


def current_supabase_table_status() -> str:
    if get_supabase_client() is None:
        return "Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY in Secrets."
    if supabase_table_exists():
        return f"Table '{SPECIMEN_TABLE}' exists and is reachable."
    if get_supabase_service_client() is None:
        return f"Table '{SPECIMEN_TABLE}' is missing. Add SUPABASE_SERVICE_ROLE_KEY to enable auto-creation."
    return f"Table '{SPECIMEN_TABLE}' is missing. Use the migration below to create it."


def attempt_create_supabase_table() -> bool:
    """
    Creates specimen_records if it doesn't exist yet. Matches the schema
    used throughout the app (diagnostics saves, PCR confirmation, accuracy
    reporting, dashboard, site log entries).
    """
    service = get_supabase_service_client()
    if service is None:
        return False

    create_sql = f"""
        CREATE TABLE IF NOT EXISTS {SPECIMEN_TABLE} (
            specimen_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            collection_date date NOT NULL DEFAULT CURRENT_DATE,
            collector_id text,
            gps_lat double precision,
            gps_lon double precision,
            breeding_site_type text,
            photo_urls text[],
            field_screening_result jsonb,
            pcr_status text NOT NULL DEFAULT 'not_submitted',
            pcr_confirmed_species text,
            pcr_lab_reference text,
            pcr_confirmed_date date,
            created_at timestamptz DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_specimen_pcr_status ON {SPECIMEN_TABLE} (pcr_status);
    """
    try:
        service.rpc("sql", {"sql": create_sql}).execute()
        return supabase_table_exists()
    except Exception:
        return False
# =============================================================================
# SHARED GENUS EXTRACTION — single source of truth for turning a stored
# field_screening_result into genus counts, regardless of which screening
# method produced it. Used by dashboard.py and environmental_trends.py so
# genus-counting logic doesn't drift between pages.
# =============================================================================
def _genus_from_label(label: str | None) -> str | None:
    if not label:
        return None
    label_lower = label.lower()
    for genus in ["anopheles", "culex", "aedes"]:
        if genus in label_lower:
            return genus.capitalize()
    return None


def extract_genus_counts_from_screening(field_screening_result: dict) -> dict:
    """
    Returns {genus: count} contributed by one specimen_records row.
    manual_field_log entries contribute their raw counts; single-specimen
    identification methods (checklist/vision/classifier) contribute 1 to
    whichever genus was resolved, or nothing if undetermined.
    """
    if not field_screening_result or not isinstance(field_screening_result, dict):
        return {}

    method = field_screening_result.get("screening_method")
    result = field_screening_result.get("result") or {}

    if method == "manual_field_log":
        counts = {
            "Anopheles": int(result.get("anopheles_count", 0) or 0),
            "Culex": int(result.get("culex_count", 0) or 0),
            "Aedes": int(result.get("aedes_count", 0) or 0),
        }
        other = int(result.get("other_genera_count", 0) or 0)
        if other:
            counts["Other"] = other
        return {k: v for k, v in counts.items() if v > 0}

    genus = None
    if method == "ai_vision":
        genus = result.get("genus") or _genus_from_label(result.get("best_match"))
    elif method == "manual_checklist":
        genus_triage = result.get("genus_triage")
        genus = genus_triage.get("genus") if genus_triage else (result.get("genus") or result.get("resolved_genus"))
        if not genus:
            candidates = result.get("species_candidates")
            if candidates:
                genus = _genus_from_label(candidates[0].get("species_name"))
    elif method == "trained_classifier":
        genus = result.get("genus") or _genus_from_label(result.get("predicted_species"))

    if genus in ("Anopheles", "Culex", "Aedes"):
        return {genus: 1}
    return {}


def extract_primary_genus(field_screening_result) -> str | None:
    """
    Single resolved genus for one specimen from an identification screening
    result, or None when undetermined or not applicable. manual_field_log
    entries hold raw multi-genus counts, not a single identification, so they
    return None here and are aggregated via extract_genus_counts_from_screening
    instead.

    This is the single source of truth for genus-from-result used by the
    dashboard map summaries and DHIS2 aggregation; components must call it
    rather than re-parsing field_screening_result themselves.
    """
    if not field_screening_result:
        return None
    if isinstance(field_screening_result, str):
        try:
            field_screening_result = json.loads(field_screening_result)
        except Exception:
            return None
    if not isinstance(field_screening_result, dict):
        return None

    method = field_screening_result.get("screening_method")
    result = field_screening_result.get("result") or {}

    if method == "ai_vision":
        return result.get("genus")
    if method == "manual_checklist":
        genus_triage = result.get("genus_triage")
        if genus_triage:
            return genus_triage.get("genus")
        return result.get("genus") or result.get("resolved_genus")
    if method == "trained_classifier":
        return result.get("genus")
    return None
# =============================================================================
# BIOASSAY RESULTS — WHO tube bioassay mortality/knockdown submission
# =============================================================================
def submit_bioassay_result(
    assay_date: date,
    treatment_name: str,
    concentration_pct: float,
    replicate_number: int,
    is_control: bool,
    mosquitoes_exposed: int,
    mortality_24hr: int,
    exposure_time_minutes: float = 60.0,
    knockdown_60min: int | None = None,
    species_tested: str = "",
    batch_reference: str = "",
    notes: str = "",
) -> dict | None:
    """
    Saves one bioassay replicate result. Returns the inserted row on
    success, or None on failure — caller must show a real error, not a
    fake success message.
    """
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this result cannot be saved.")
        return None

    if mortality_24hr > mosquitoes_exposed:
        st.error("Mortality count cannot exceed the number of mosquitoes exposed.")
        return None
    if knockdown_60min is not None and knockdown_60min > mosquitoes_exposed:
        st.error("Knockdown count cannot exceed the number of mosquitoes exposed.")
        return None

    record = {
        "assay_date": assay_date.isoformat(),
        "treatment_name": treatment_name,
        "concentration_pct": float(concentration_pct),
        "replicate_number": int(replicate_number),
        "is_control": bool(is_control),
        "mosquitoes_exposed": int(mosquitoes_exposed),
        "exposure_time_minutes": float(exposure_time_minutes),
        "knockdown_60min": int(knockdown_60min) if knockdown_60min is not None else None,
        "mortality_24hr": int(mortality_24hr),
        "species_tested": species_tested or None,
        "batch_reference": batch_reference or None,
        "submitted_by": get_current_user_id(),
        "notes": notes or None,
    }

    try:
        response = client.table("bioassay_results").insert(record).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Could not save bioassay result: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def load_bioassay_results() -> pd.DataFrame:
    """Loads all bioassay_results from Supabase. Empty DataFrame if unavailable."""
    client = get_supabase_client()
    if client is None:
        return pd.DataFrame()
    try:
        response = client.table("bioassay_results").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Could not load bioassay results: {e}")
    return pd.DataFrame()


def clear_bioassay_results_cache():
    load_bioassay_results.clear()


def compute_mortality_percentage(mortality_24hr: int, mosquitoes_exposed: int) -> float | None:
    """WHO-standard corrected mortality is not applied here — this is raw
    percentage mortality. Abbott's correction should be applied at analysis
    time once control mortality data for the same batch is available."""
    if mosquitoes_exposed == 0:
        return None
    return round((mortality_24hr / mosquitoes_exposed) * 100, 1)


def classify_resistance_status(mortality_pct: float | None) -> str:
    """WHO (2016) susceptibility test interpretation thresholds."""
    if mortality_pct is None:
        return "Unknown"
    if mortality_pct >= 98:
        return "Susceptible"
    if mortality_pct >= 90:
        return "Possible resistance (confirm with additional testing)"
    return "Resistant"
# =============================================================================
# CLINICAL CASE DATA — manually logged confirmed malaria case counts, used
# for real (not fabricated) larval density vs. case count correlation.
# =============================================================================
def submit_clinical_case_record(
    report_date: date,
    facility_name: str,
    confirmed_cases: int,
    lga_district: str = "",
    suspected_cases: int | None = None,
    diagnostic_method: str = "",
    patient_age_group: str = "",
    notes: str = "",
) -> dict | None:
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this record cannot be saved.")
        return None

    if confirmed_cases < 0:
        st.error("Confirmed cases cannot be negative.")
        return None
    if suspected_cases is not None and suspected_cases < confirmed_cases:
        st.error("Suspected cases cannot be lower than confirmed cases.")
        return None

    record = {
        "report_date": report_date.isoformat(),
        "facility_name": facility_name,
        "lga_district": lga_district or None,
        "confirmed_cases": int(confirmed_cases),
        "suspected_cases": int(suspected_cases) if suspected_cases is not None else None,
        "diagnostic_method": diagnostic_method or None,
        "patient_age_group": patient_age_group or None,
        "submitted_by": get_current_user_id(),
        "notes": notes or None,
    }

    try:
        response = client.table("clinical_case_data").insert(record).execute()
        return response.data[0] if response.data else None
    except Exception as e:
        st.error(f"Could not save clinical case record: {e}")
        return None


@st.cache_data(ttl=60, show_spinner=False)
def load_clinical_case_data() -> pd.DataFrame:
    client = get_supabase_client()
    if client is None:
        return pd.DataFrame()
    try:
        response = client.table("clinical_case_data").select("*").execute()
        if response.data:
            return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"Could not load clinical case data: {e}")
    return pd.DataFrame()


def clear_clinical_case_data_cache():
    load_clinical_case_data.clear()