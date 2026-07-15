"""
Submits diagnostics results (checklist, AI vision, or trained classifier
output) to the specimen_records table, tagged with which screening method
produced them. This tag is what keeps accuracy tracking honest later —
without it, PCR-confirmation comparisons can't tell a checklist guess
from a trained-model prediction.
"""

from datetime import date, datetime, timezone

import streamlit as st

from utils.auth import get_collector_label, get_supabase_client
from utils.data_manager import (
    IDENTIFICATION_METHODS,
    clear_specimen_records_cache,
    first_row,
    require_current_user_id,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)


def submit_screening_result(
    screening_method: str,      # "manual_checklist" | "ai_vision" | "trained_classifier"
    result: dict,                # whatever that method's function returned
    collector_id: str | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    breeding_site_type: str | None = None,
    photo_urls: list | None = None,
    specimen_id: str | None = None,
) -> dict | None:
    """
    Writes one specimen_records row. Returns the inserted row on success, None on
    failure — every failure path surfaces its own error to the user first, so callers
    must not report a success they didn't get.

    `collector_id` defaults to the signed-in user. It is a parameter only so a caller
    can attribute a record to someone else; leaving it off must never produce an
    unattributed row, which is what it used to do.

    `specimen_id` lets a caller fix the ID up front, which it must do when photos are
    uploaded to storage before the row exists — the images are filed under that ID, so it
    has to be the same one the row ends up with.
    """
    if screening_method not in IDENTIFICATION_METHODS:
        raise ValueError(f"screening_method must be one of {IDENTIFICATION_METHODS}")

    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this identification cannot be saved.")
        return None

    collector_id = collector_id or require_current_user_id()
    if not collector_id:
        return None  # require_current_user_id already told the user why

    field_screening_result = {
        "screening_method": screening_method,
        "result": result,
        "collector_label": get_collector_label() or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    record = {
        "collection_date":        date.today().isoformat(),
        "collector_id":           collector_id,
        "gps_lat":                gps_lat,
        "gps_lon":                gps_lon,
        "breeding_site_type":     breeding_site_type,
        "photo_urls":             photo_urls or [],
        "field_screening_result": field_screening_result,
        "pcr_status":             "not_submitted",
    }
    if specimen_id:
        record["specimen_id"] = specimen_id

    try:
        response = client.table("specimen_records").insert(record).execute()
    except Exception as e:
        logger.exception("Specimen submission failed")
        st.error(f"Could not save identification: {e}")
        return None

    clear_specimen_records_cache()
    saved = first_row(response)
    if saved is None:
        # The insert returned no row (e.g. an RLS policy denied the write). Saying nothing
        # here would let the caller show a bare "check your connection", so be specific.
        logger.warning("Specimen insert for %s returned no row", screening_method)
        st.error(
            "The identification was not saved — the database accepted no new record. "
            "Check your permissions and try again."
        )
        return None
    return saved
