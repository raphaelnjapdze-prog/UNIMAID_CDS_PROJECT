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
from datetime import date, datetime, timezone

import pandas as pd
import streamlit as st

from utils.auth import (
    get_collector_label,
    get_current_user_id,
    get_supabase_client,
    get_supabase_service_client,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

# The screening methods that represent a single-specimen identification. Both write
# paths validate against this: submit_screening_result (insert) and
# attach_identification_to_specimen (update onto an existing vialed-out specimen).
# A method outside this set produces a row no genus aggregator can interpret.
IDENTIFICATION_METHODS = frozenset({"manual_checklist", "ai_vision", "trained_classifier"})


def response_rows(response) -> list[dict]:
    """Narrow a Supabase response's `.data` to the list of row dicts it actually is.

    supabase-py types `.data` as a loose JSON union (it could in principle be a float, a
    string, a bool…), so indexing or calling .get() on it directly is unsound — every
    such use is a type error, and a malformed response would blow up at runtime with an
    obscure AttributeError instead of being handled. Funnel every read through here: a
    non-list payload, or entries that aren't objects, yield no rows rather than a crash.
    """
    data = getattr(response, "data", None)
    if not isinstance(data, list):
        return []
    return [row for row in data if isinstance(row, dict)]


def first_row(response) -> dict | None:
    """The single row a Supabase insert/update returns, or None when it affected none."""
    rows = response_rows(response)
    return rows[0] if rows else None

# =============================================================================
# SPECIMEN PHOTO UPLOAD
# =============================================================================
def _upload_photo_bytes(
    file_bytes: bytes, specimen_id: str, ext: str = "jpg", content_type: str = "image/jpeg"
) -> str | None:
    """
    Uploads raw image bytes to the specimen-photos Supabase Storage bucket and
    returns its public URL, or None on failure. Shared by the file-upload and
    multi-angle (in-memory bytes) capture paths so both hit the same bucket.
    """
    client = get_supabase_client()
    if client is None or not file_bytes:
        return None
    try:
        path = f"{specimen_id}/{uuid.uuid4()}.{ext}"
        client.storage.from_("specimen-photos").upload(
            path, file_bytes, {"content-type": content_type or "image/jpeg"}
        )
        return client.storage.from_("specimen-photos").get_public_url(path)
    except Exception as e:
        logger.warning("Photo upload to specimen-photos failed", exc_info=True)
        st.warning(f"Photo upload failed, entry will be saved without it: {e}")
        return None


def upload_specimen_photo(uploaded_file, specimen_id: str) -> str | None:
    """
    Uploads a field photo to the specimen-photos Supabase Storage bucket and
    returns its public URL. Returns None on failure — caller must warn the
    user, not silently drop the photo.
    """
    if uploaded_file is None:
        return None
    ext = uploaded_file.name.split(".")[-1] if "." in uploaded_file.name else "jpg"
    return _upload_photo_bytes(
        uploaded_file.getvalue(), specimen_id, ext, uploaded_file.type or "image/jpeg"
    )


def require_current_user_id() -> str | None:
    """The signed-in user's id, or None (with an error shown) if there isn't one.

    Every write that records who made it goes through this. get_current_user_id() returns
    "" for a session with no user, and an empty string satisfies a NOT NULL constraint
    just fine — which is how blank-collector rows got into specimen_records in the first
    place, despite the column being declared NOT NULL. A row nobody is accountable for
    never comes back from that user's own "Export my data" (which filters on collector_id)
    and leaves no trace of who recorded it, so refuse the write rather than store it
    anonymously.
    """
    user_id = (get_current_user_id() or "").strip()
    if not user_id:
        st.error("You must be signed in to save — no user on record for this entry.")
        return None
    return user_id


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

    collector_id = require_current_user_id()
    if collector_id is None:
        return None

    specimen_id = str(uuid.uuid4())
    photo_url = upload_specimen_photo(photo_file, specimen_id) if photo_file else None

    record = {
        "specimen_id": specimen_id,
        "collection_date": collection_date.isoformat(),
        "collector_id": collector_id,
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
            "collector_label": get_collector_label() or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "pcr_status": "not_submitted",
    }

    try:
        response = client.table("specimen_records").insert(record).execute()
        clear_specimen_records_cache()
        return first_row(response)
    except Exception as e:
        logger.exception("Could not save site log entry")
        st.error(f"Could not save site log entry: {e}")
        return None


def submit_multi_angle_capture_entry(
    angle_images: dict,
    statuses: dict | None = None,
    gps_lat: float | None = None,
    gps_lon: float | None = None,
    field_collector_label: str = "",
    collection_date: date | None = None,
) -> dict | None:
    """
    Persists a multi-angle specimen capture to specimen_records: uploads each
    captured angle image to the specimen-photos bucket and inserts one row
    tagged screening_method="multi_angle_capture".

    This is a raw image capture, not a species identification — like
    manual_field_log it deliberately carries no genus claim, so it stays out of
    genus/accuracy reporting (extract_primary_genus / extract_genus_counts do
    not match this method).

    `angle_images` maps angle_key -> {"bytes", "filename", "mime_type",
    "captured_at"}; `statuses` maps angle_key -> "captured"/"not_captured"/
    "pending". Returns the inserted row on success, or None if Supabase isn't
    configured or the insert failed — the caller must show an honest error.
    """
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this capture cannot be saved.")
        return None

    collector_id = require_current_user_id()
    if collector_id is None:
        return None

    statuses = statuses or {}
    specimen_id = str(uuid.uuid4())
    photo_urls: list[str] = []
    angle_records: dict[str, dict] = {}

    # Record every angle's status; upload images only for captured ones.
    angle_keys = list(statuses.keys()) or list((angle_images or {}).keys())
    for angle_key in angle_keys:
        payload = (angle_images or {}).get(angle_key) or {}
        image_bytes = payload.get("bytes")
        photo_url = None
        if image_bytes:
            filename = payload.get("filename") or f"{angle_key}.jpg"
            ext = filename.split(".")[-1] if "." in filename else "jpg"
            photo_url = _upload_photo_bytes(
                image_bytes, specimen_id, ext, payload.get("mime_type") or "image/jpeg"
            )
            if photo_url:
                photo_urls.append(photo_url)
        angle_records[angle_key] = {
            "status": statuses.get(angle_key, "captured" if image_bytes else "pending"),
            "filename": payload.get("filename"),
            "captured_at": payload.get("captured_at"),
            "photo_url": photo_url,
        }

    record = {
        "specimen_id": specimen_id,
        "collection_date": (collection_date or date.today()).isoformat(),
        "collector_id": collector_id,
        "gps_lat": gps_lat,
        "gps_lon": gps_lon,
        "breeding_site_type": None,
        "photo_urls": photo_urls,
        "field_screening_result": {
            "screening_method": "multi_angle_capture",
            "result": {
                "angles": angle_records,
                "angles_captured": [k for k, r in angle_records.items() if r["photo_url"]],
                # Who physically collected it — may be a field assistant, so it is a free
                # label and NOT the account identity stamped alongside it.
                "field_collector_label": field_collector_label or None,
            },
            "collector_label": get_collector_label() or None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "pcr_status": "not_submitted",
    }

    try:
        response = client.table("specimen_records").insert(record).execute()
        clear_specimen_records_cache()
        return first_row(response)
    except Exception as e:
        logger.exception("Could not save multi-angle capture")
        st.error(f"Could not save specimen capture: {e}")
        return None


# =============================================================================
# 3b. SUBSAMPLING — "vial out" individual specimens from a batch field-count log
# =============================================================================
# A manual_field_log row is a batch collection event holding raw genus counts
# (e.g. 500 Anopheles). To PCR-confirm individuals, we subsample: each vialed
# specimen becomes its own specimen_records row (its specimen_id IS its QR/barcode),
# linked back to the batch via parent_specimen_id, and independently identifiable
# and PCR-confirmable. The batch's raw counts are preserved untouched; a "vialed_out"
# tally records how many of each genus have been individualized, so effective genus
# totals (raw − vialed_out, plus one per child) never double-count. These pure
# helpers hold the count math and row shaping so they can be unit-tested without a DB.

# Genus display name -> the manual_field_log count key it is stored under.
_FIELD_LOG_GENUS_KEYS = {
    "Anopheles": "anopheles_count",
    "Culex": "culex_count",
    "Aedes": "aedes_count",
}


def _available_to_vial(field_log_result: dict, genus: str) -> int:
    """How many specimens of `genus` in a manual_field_log batch remain available
    to vial out: the raw field count minus those already vialed out. Floors at 0;
    returns 0 for genera the field log doesn't track (only Anopheles/Culex/Aedes)."""
    key = _FIELD_LOG_GENUS_KEYS.get(genus)
    if key is None:
        return 0
    result = field_log_result or {}
    raw = int(result.get(key, 0) or 0)
    already = int((result.get("vialed_out") or {}).get(genus, 0) or 0)
    return max(0, raw - already)


def available_to_vial(batch_record: dict, genus: str) -> int:
    """Public accessor: how many specimens of `genus` remain available to vial out of
    a batch specimen_records row. Returns 0 if the row isn't a field-count log. Wraps
    the tested `_available_to_vial` count math so UI code doesn't re-derive it."""
    field_screening = (batch_record or {}).get("field_screening_result") or {}
    if field_screening.get("screening_method") != "manual_field_log":
        return 0
    return _available_to_vial(field_screening.get("result") or {}, genus)


def _apply_vialed_out(field_log_result: dict, genus: str, count: int) -> dict:
    """Return a copy of a manual_field_log result with `count` more specimens of
    `genus` recorded under 'vialed_out'. The raw counts are preserved unchanged, so
    the original catch total is never lost and vialing stays reversible."""
    updated = dict(field_log_result or {})
    vialed = dict(updated.get("vialed_out") or {})
    vialed[genus] = int(vialed.get(genus, 0) or 0) + int(count)
    updated["vialed_out"] = vialed
    return updated


def _build_subsample_children(
    batch_row: dict, genus: str, count: int, tube_prefix: str | None, now_iso: str
) -> list[dict]:
    """Build (but do not persist) the child specimen_records rows for a vial-out.
    Pure and side-effect free — the caller performs the DB insert and parent update.
    Each child inherits the batch's collection metadata, carries a known-genus
    'field_subsample' screening result (pending species identification), and gets a
    fresh specimen_id that doubles as its QR/barcode."""
    children: list[dict] = []
    for i in range(count):
        specimen_id = str(uuid.uuid4())
        children.append({
            "specimen_id": specimen_id,
            "parent_specimen_id": batch_row.get("specimen_id"),
            "specimen_role": "individual",
            "collection_date": batch_row.get("collection_date"),
            "collector_id": batch_row.get("collector_id"),
            "gps_lat": batch_row.get("gps_lat"),
            "gps_lon": batch_row.get("gps_lon"),
            "breeding_site_type": batch_row.get("breeding_site_type"),
            "photo_urls": [],
            "tube_label": f"{tube_prefix}-{i + 1:03d}" if tube_prefix else None,
            "field_screening_result": {
                "screening_method": "field_subsample",
                "result": {
                    "genus": genus,
                    "resolution_level": "genus",
                    "pending_identification": True,
                },
                "timestamp": now_iso,
            },
            "pcr_status": "not_submitted",
        })
    return children


def vial_out_specimens(
    batch_specimen_id: str, genus: str, count: int, tube_prefix: str | None = None
) -> list[dict] | None:
    """Subsample `count` individual specimens of `genus` out of a batch field-count
    log, creating one barcoded specimen_records row per individual (linked to the
    batch via parent_specimen_id) so each can be identified and PCR-confirmed on its
    own. The batch's raw counts are preserved; a 'vialed_out' tally is updated so
    genus totals never double-count.

    Returns the list of created child rows (each carries a specimen_id for QR
    printing), or None if Supabase isn't configured, the batch is invalid, or fewer
    than `count` specimens of `genus` remain available. Never fabricates success:
    callers must surface an honest error on None.
    """
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — specimens cannot be vialed out.")
        return None

    if count < 1:
        st.error("Number to vial out must be at least 1.")
        return None

    genus = (genus or "").strip().capitalize()
    if genus not in _FIELD_LOG_GENUS_KEYS:
        st.error(f"Subsampling is only supported for {', '.join(_FIELD_LOG_GENUS_KEYS)}.")
        return None

    try:
        response = (
            client.table("specimen_records").select("*").eq("specimen_id", batch_specimen_id).execute()
        )
    except Exception as e:
        logger.exception("Could not load batch record for vialing")
        st.error(f"Could not load the batch record: {e}")
        return None

    batch = first_row(response)
    if batch is None:
        st.error("Batch record not found.")
        return None

    field_screening = batch.get("field_screening_result") or {}
    if field_screening.get("screening_method") != "manual_field_log":
        st.error("Specimens can only be vialed out of a field-count log entry.")
        return None
    result = field_screening.get("result") or {}

    available = _available_to_vial(result, genus)
    if count > available:
        st.error(f"Only {available} {genus} remain available to vial out of this batch.")
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    children = _build_subsample_children(batch, genus, count, tube_prefix, now_iso)

    # Insert the individuals first, then update the batch tally. If the tally update
    # fails we roll the children back, so the batch's vialed_out count and the actual
    # child rows can never disagree (which would corrupt genus totals).
    try:
        insert_response = client.table("specimen_records").insert(children).execute()
    except Exception as e:
        logger.exception("Could not create subsampled specimens")
        st.error(f"Could not vial out specimens: {e}")
        return None

    inserted = response_rows(insert_response) or children
    try:
        updated_screening = dict(field_screening)
        updated_screening["result"] = _apply_vialed_out(result, genus, count)
        (
            client.table("specimen_records")
            .update({"field_screening_result": updated_screening})
            .eq("specimen_id", batch_specimen_id)
            .execute()
        )
    except Exception as e:
        logger.exception("Vial-out batch tally update failed; rolling back children")
        try:
            child_ids = [c["specimen_id"] for c in inserted]
            client.table("specimen_records").delete().in_("specimen_id", child_ids).execute()
        except Exception:
            logger.error("Rollback of subsampled children failed — manual cleanup needed", exc_info=True)
        st.error(f"Could not update the batch tally, so vialing was rolled back: {e}")
        return None

    clear_specimen_records_cache()
    return inserted


def fetch_batch_children(batch_specimen_id: str) -> pd.DataFrame:
    """Return all individual specimens vialed out of a batch, as a DataFrame
    (empty — never fabricated — if none exist or Supabase is unavailable)."""
    client = get_supabase_client()
    if client is None:
        return pd.DataFrame()
    try:
        response = (
            client.table("specimen_records").select("*").eq("parent_specimen_id", batch_specimen_id).execute()
        )
        return pd.DataFrame(response_rows(response))
    except Exception:
        logger.warning("Could not fetch subsampled children for batch %s", batch_specimen_id, exc_info=True)
        return pd.DataFrame()


def is_pending_identification(record) -> bool:
    """True if a row is a vialed-out individual still awaiting its identification —
    i.e. a subsample whose genus is known from the pile it came from but which has
    not yet been morphologically or AI-identified. These are the specimens a user
    scans a tube for on the Diagnostics page."""
    field_screening = (record or {}).get("field_screening_result") or {}
    if field_screening.get("screening_method") != "field_subsample":
        return False
    return bool((field_screening.get("result") or {}).get("pending_identification"))


def specimens_pending_identification(df: pd.DataFrame) -> pd.DataFrame:
    """Filter a loaded specimen_records frame down to the vialed-out individuals still
    awaiting identification. Pure — takes the frame from the cached
    load_specimen_records() rather than issuing its own query."""
    if df is None or df.empty or "field_screening_result" not in df.columns:
        return pd.DataFrame()
    # Test the one column that decides this, rather than materializing a dict of every
    # column (photos, PCR fields, …) for every row in the ledger on each page render.
    mask = df["field_screening_result"].apply(
        lambda fsr: is_pending_identification({"field_screening_result": fsr})
    )
    return df[mask].copy()


def attach_identification_to_specimen(
    specimen_id: str, screening_method: str, result: dict
) -> dict | None:
    """Attach a morphological/AI identification to an EXISTING specimen row (e.g. a
    vialed-out individual whose barcode was scanned), replacing its
    field_screening_result. Use this instead of submit_screening_result when the
    specimen record already exists. Returns the updated row, or None on failure —
    the caller must show an honest error, never a fake success."""
    client = get_supabase_client()
    if client is None:
        st.error("Supabase is not configured — this identification cannot be saved.")
        return None

    # Same allowlist submit_screening_result enforces on the insert path. An unrecognised
    # method would write a row that neither extract_genus_counts_from_screening nor
    # extract_primary_genus can read — the specimen would persist but be invisible to
    # every aggregate that reads the ledger.
    if screening_method not in IDENTIFICATION_METHODS:
        raise ValueError(f"screening_method must be one of {IDENTIFICATION_METHODS}")

    # Refuse to overwrite a batch field-count log. Its field_screening_result holds the
    # raw genus counts and the vialed_out tally; replacing that with a single-specimen
    # identification would silently destroy the catch totals for the whole collection
    # event. Individuals must be vialed out of the batch first (see vial_out_specimens).
    try:
        existing = (
            client.table("specimen_records")
            .select("field_screening_result")
            .eq("specimen_id", specimen_id)
            .execute()
        )
    except Exception as e:
        logger.exception("Could not load specimen %s before attaching identification", specimen_id)
        st.error(f"Could not load that specimen: {e}")
        return None

    existing_row = first_row(existing)
    if existing_row is None:
        st.error("No specimen found with that ID — check the QR value.")
        return None

    prior = existing_row.get("field_screening_result") or {}
    if prior.get("screening_method") == "manual_field_log":
        st.error(
            "That ID is a batch field-count log, not an individual specimen. Vial out a "
            "specimen from the batch first, then identify that individual."
        )
        return None

    # Carry the subsampled genus forward. The batch this specimen came from has already
    # been decremented by one for it, so if the incoming identification resolves to no
    # genus (undetermined triage, vision returning none), the specimen would contribute
    # nothing and a real, caught mosquito would vanish from the totals. The genus is known
    # from the pile it was vialed out of; keep it as the floor that aggregation falls back
    # to. Re-identifying an already-identified child preserves it via the second branch.
    subsampled_genus = None
    if prior.get("screening_method") == "field_subsample":
        subsampled_genus = (prior.get("result") or {}).get("genus")
    elif prior.get("subsampled_genus"):
        subsampled_genus = prior["subsampled_genus"]

    # Who identified this specimen, which is not necessarily who collected it: the row's
    # collector_id belongs to whoever logged the batch it was vialed out of, and that
    # column stays theirs. Overwriting it would rewrite the collection event's history.
    field_screening_result = {
        "screening_method": screening_method,
        "result": result,
        "identified_by_id": get_current_user_id() or None,
        "identified_by_label": get_collector_label() or None,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if subsampled_genus:
        field_screening_result["subsampled_genus"] = subsampled_genus

    try:
        response = (
            client.table("specimen_records")
            .update({"field_screening_result": field_screening_result})
            .eq("specimen_id", specimen_id)
            .execute()
        )
    except Exception as e:
        logger.exception("Could not attach identification to specimen %s", specimen_id)
        st.error(f"Could not save identification: {e}")
        return None

    clear_specimen_records_cache()
    updated = first_row(response)
    if updated is None:
        # The update matched no rows (e.g. an RLS policy denied the write). Returning a
        # bare None here would let the caller show nothing at all, so say so out loud.
        logger.warning("Identification update for %s matched no rows", specimen_id)
        st.error(
            "The identification was not saved — the database accepted no change to that "
            "specimen. Check your permissions and try again."
        )
        return None
    return updated


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
        rows = response_rows(response)
        if rows:
            return pd.DataFrame(rows)
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
        logger.debug("specimen_records existence probe failed", exc_info=True)
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
            parent_specimen_id uuid REFERENCES {SPECIMEN_TABLE} (specimen_id) ON DELETE SET NULL,
            tube_label text,
            specimen_role text NOT NULL DEFAULT 'primary',
            created_at timestamptz DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_specimen_pcr_status ON {SPECIMEN_TABLE} (pcr_status);
        CREATE INDEX IF NOT EXISTS idx_specimen_parent ON {SPECIMEN_TABLE} (parent_specimen_id);
    """
    try:
        service.rpc("sql", {"sql": create_sql}).execute()
        return supabase_table_exists()
    except Exception:
        logger.warning("Failed to create %s table via service RPC", SPECIMEN_TABLE, exc_info=True)
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
        # Subtract any specimens vialed out of this batch: each is now tracked as its
        # own child row contributing 1, so counting them here too would double-count.
        # Raw counts are preserved on the row; we only net out vialed_out for totals.
        vialed = result.get("vialed_out") or {}
        counts = {
            "Anopheles": int(result.get("anopheles_count", 0) or 0) - int(vialed.get("Anopheles", 0) or 0),
            "Culex": int(result.get("culex_count", 0) or 0) - int(vialed.get("Culex", 0) or 0),
            "Aedes": int(result.get("aedes_count", 0) or 0) - int(vialed.get("Aedes", 0) or 0),
        }
        other = int(result.get("other_genera_count", 0) or 0)
        if other:
            counts["Other"] = other
        return {k: v for k, v in counts.items() if v > 0}

    genus = None
    if method == "field_subsample":
        # An individual vialed out of a batch: genus is known (subsampled from a
        # genus-specific pile), species identification may still be pending.
        genus = result.get("genus")
    elif method == "ai_vision":
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

    if genus not in ("Anopheles", "Culex", "Aedes"):
        # A specimen vialed out of a batch whose identification came back undetermined.
        # Its parent batch was already decremented by one for it, so dropping it here
        # would delete a real, caught mosquito from the totals. Fall back to the genus of
        # the pile it was subsampled from — which is known regardless of what the
        # identification could or couldn't resolve. See attach_identification_to_specimen.
        genus = field_screening_result.get("subsampled_genus")

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
            logger.debug("Could not JSON-decode field_screening_result for genus extraction", exc_info=True)
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
    if method == "field_subsample":
        # Genus is known from which pile the individual was subsampled, even before
        # species-level morphology/PCR — so it counts at genus level for aggregation.
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

    submitted_by = require_current_user_id()
    if submitted_by is None:
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
        "submitted_by": submitted_by,
        "notes": notes or None,
    }

    try:
        response = client.table("bioassay_results").insert(record).execute()
        return first_row(response)
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
        rows = response_rows(response)
        if rows:
            return pd.DataFrame(rows)
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

    submitted_by = require_current_user_id()
    if submitted_by is None:
        return None

    record = {
        "report_date": report_date.isoformat(),
        "facility_name": facility_name,
        "lga_district": lga_district or None,
        "confirmed_cases": int(confirmed_cases),
        "suspected_cases": int(suspected_cases) if suspected_cases is not None else None,
        "diagnostic_method": diagnostic_method or None,
        "patient_age_group": patient_age_group or None,
        "submitted_by": submitted_by,
        "notes": notes or None,
    }

    try:
        response = client.table("clinical_case_data").insert(record).execute()
        return first_row(response)
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
        rows = response_rows(response)
        if rows:
            return pd.DataFrame(rows)
    except Exception as e:
        st.error(f"Could not load clinical case data: {e}")
    return pd.DataFrame()


def clear_clinical_case_data_cache():
    load_clinical_case_data.clear()
