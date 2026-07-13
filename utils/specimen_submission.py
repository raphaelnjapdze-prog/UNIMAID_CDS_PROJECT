"""
Submits diagnostics results (checklist, AI vision, or trained classifier
output) to the specimen_records table, tagged with which screening method
produced them. This tag is what keeps accuracy tracking honest later —
without it, PCR-confirmation comparisons can't tell a checklist guess
from a trained-model prediction.
"""

from datetime import date, datetime, timezone

from utils.auth import get_supabase_client  # adjust import path to match your project
from utils.data_manager import IDENTIFICATION_METHODS, first_row
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
) -> dict | None:
    """
    Writes one specimen_records row. Returns the inserted row on success,
    None on failure (caller should show an error to the user).
    """
    if screening_method not in IDENTIFICATION_METHODS:
        raise ValueError(f"screening_method must be one of {IDENTIFICATION_METHODS}")

    client = get_supabase_client()
    if client is None:
        return None

    field_screening_result = {
        "screening_method": screening_method,
        "result": result,
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

    try:
        response = client.table("specimen_records").insert(record).execute()
        return first_row(response)
    except Exception:
        logger.exception("Specimen submission failed")
        return None
