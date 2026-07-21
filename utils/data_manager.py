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
    is_network_error,
)
from utils.logging_config import get_logger
from utils.offline_queue import (
    SYNC_OK,
    SYNC_REJECTED,
    SYNC_RETRY,
    drain,
    enqueue_site_log,
)

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
    # A photo needs a live upload; if that fails we still save the record (see the
    # network-error branch below), just without the image, which can be added later.
    photo_url = upload_specimen_photo(photo_file, specimen_id) if photo_file else None

    record = build_site_log_record(
        specimen_id=specimen_id,
        collection_date=collection_date,
        collector_id=collector_id,
        collector_label=get_collector_label() or None,
        breeding_site_type=breeding_site_type,
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        anopheles_count=anopheles_count,
        culex_count=culex_count,
        aedes_count=aedes_count,
        other_genera_count=other_genera_count,
        field_notes=field_notes,
        photo_url=photo_url,
    )

    try:
        row = insert_specimen_record(record, client)
        clear_specimen_records_cache()
        return row
    except Exception as e:
        # A connectivity failure is recoverable: park the entry in the offline queue
        # (it survives a reload) instead of losing what the field worker just typed.
        # Any other failure — a schema/permission problem — would never sync, so it is
        # surfaced honestly rather than queued to fail forever.
        if is_network_error(e):
            if enqueue_site_log(record):
                logger.info("Site-log save offline; queued for sync (%s)", specimen_id)
                return {**record, "_pending_offline": True}
            st.error(
                "You appear to be offline and the pending queue is full. "
                "Reconnect and tap “Sync now” before logging more entries."
            )
            return None
        logger.exception("Could not save site log entry")
        st.error(f"Could not save site log entry: {e}")
        return None


def build_site_log_record(
    *,
    specimen_id: str,
    collection_date: date,
    collector_id: str,
    collector_label: str | None,
    breeding_site_type: str,
    gps_lat: float | None,
    gps_lon: float | None,
    anopheles_count: int = 0,
    culex_count: int = 0,
    aedes_count: int = 0,
    other_genera_count: int = 0,
    field_notes: str = "",
    photo_url: str | None = None,
) -> dict:
    """Build (without persisting) the specimen_records row for a field-count log.

    Pure and JSON-serializable, so the same record can be inserted now or parked in
    the offline queue and inserted later. specimen_id and collector_id are passed in
    (not generated here) so a queued entry keeps the identity — and the QR label —
    it was given at entry time.
    """
    return {
        "specimen_id": specimen_id,
        "collection_date": collection_date.isoformat() if hasattr(collection_date, "isoformat") else collection_date,
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
            "collector_label": collector_label,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        "pcr_status": "not_submitted",
    }


def insert_specimen_record(record: dict, client=None) -> dict | None:
    """Low-level insert of a prebuilt specimen_records row. Raises on failure so the
    caller can distinguish a network drop (queue it) from a hard rejection (surface it);
    does not show UI itself. Used by the online save path and by the offline drain."""
    client = client or get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase is not configured")
    response = client.table("specimen_records").insert(record).execute()
    return first_row(response)


def sync_pending_writes() -> tuple[int, int, int]:
    """Drain the offline queue back to Supabase. Returns (synced, remaining, rejected).

    On a successful drain of anything, the specimen cache is cleared so the newly
    landed rows appear.
    """

    def _sync(kind: str, payload: dict):
        if kind != "site_log":
            # Not transient — nothing will teach this build how to write that kind.
            return SYNC_REJECTED, f"Unknown queued write kind {kind!r}"
        try:
            # An insert that doesn't raise landed, even when it returns no row: under
            # RLS the anon key can be denied SELECT on what it just wrote. Requiring a
            # row back would re-queue a write that succeeded and insert it again on the
            # next drain — double-counting the exact catch this queue exists to protect.
            insert_specimen_record(payload)
            return SYNC_OK, ""
        except Exception as e:
            if is_network_error(e):
                return SYNC_RETRY, str(e)
            # A schema or permission rejection will fail identically on every retry.
            # Entries are only queued after a *network* failure, so the payload was
            # never server-validated — live-schema drift can surface here first.
            logger.exception("Queued site-log entry was rejected by the server")
            return SYNC_REJECTED, str(e)

    synced, remaining, rejected = drain(_sync)
    if synced:
        clear_specimen_records_cache()
    return synced, remaining, rejected


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

    def _rollback_children(reason: str) -> None:
        try:
            child_ids = [c["specimen_id"] for c in inserted]
            client.table("specimen_records").delete().in_("specimen_id", child_ids).execute()
        except Exception:
            logger.error("Rollback of subsampled children failed — manual cleanup needed", exc_info=True)
        st.error(f"Could not update the batch tally, so vialing was rolled back: {reason}")

    try:
        updated_screening = dict(field_screening)
        updated_screening["result"] = _apply_vialed_out(result, genus, count)
        tally_response = (
            client.table("specimen_records")
            .update({"field_screening_result": updated_screening})
            .eq("specimen_id", batch_specimen_id)
            .execute()
        )
    except Exception as e:
        logger.exception("Vial-out batch tally update failed; rolling back children")
        _rollback_children(str(e))
        return None

    # An UPDATE that no RLS policy permits does not raise — it matches zero rows and
    # silently does nothing. Trusting the call to have worked left the batch holding its
    # full raw counts while each child also contributed 1: the same mosquitoes counted
    # twice, reported as a success. Verify the row actually changed, and roll back if not.
    if first_row(tally_response) is None:
        logger.error(
            "Vial-out tally update for batch %s matched no rows; rolling back children",
            batch_specimen_id,
        )
        _rollback_children(
            "the database accepted no change to the batch — check that an UPDATE policy "
            "exists on specimen_records (sql/add_update_policies.sql)"
        )
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


def _as_screening_dict(field_screening_result) -> dict:
    """field_screening_result as a dict, whether it arrived as one or as a JSON string."""
    if isinstance(field_screening_result, str):
        try:
            field_screening_result = json.loads(field_screening_result)
        except Exception:
            logger.debug("Could not JSON-decode field_screening_result", exc_info=True)
            return {}
    return field_screening_result if isinstance(field_screening_result, dict) else {}


def summarise_vialed_child(row: dict) -> dict:
    """One vialed-out individual, described for display under its parent batch."""
    screening = _as_screening_dict(row.get("field_screening_result"))
    method = screening.get("screening_method")

    # The genus is known from the pile it was vialed out of, even before anyone identifies
    # it. On a freshly vialed specimen it sits in the field_subsample result; once
    # identified, attach_identification_to_specimen carries it forward as subsampled_genus.
    if method == "field_subsample":
        known_genus = (screening.get("result") or {}).get("genus")
    else:
        known_genus = screening.get("subsampled_genus")

    # A specimen still tagged field_subsample has been vialed but not identified. Its genus
    # is known from the pile it came from, which is why extract_primary_genus returns one
    # (so it still counts toward that genus in aggregates) — but reporting that as an
    # identification would claim work nobody has done. Only a real identification method
    # counts as identified.
    identified_as = None if method == "field_subsample" else extract_primary_genus(screening)

    return {
        "specimen_id": row.get("specimen_id"),
        "tube_label": row.get("tube_label"),
        "genus": known_genus,
        "identified_as": identified_as,
        "identified_by": screening.get("identified_by_label"),
        "pcr_status": row.get("pcr_status"),
        "pcr_confirmed_species": row.get("pcr_confirmed_species"),
    }


def build_collection_events(df: pd.DataFrame) -> tuple[list[dict], pd.DataFrame]:
    """Reshape the flat ledger into collection events, each with its vialed individuals.

    A batch field log is a collection event: 500 Anopheles caught at one place on one
    night. Vialing an individual out of it creates a child row — which is what keeps the
    counts honest — but a flat ledger then shows that mosquito as an unrelated new ID,
    hiding the relationship it exists to record. This nests each child under the batch it
    came from.

    Per genus it reports three numbers that must always reconcile:
        caught   — the raw field count, never mutated
        vialed   — how many have been vialed out as individuals
        in_batch — caught − vialed, what still sits in the bulk sample

    Returns (events, other_rows). `other_rows` holds rows belonging to no collection
    event — standalone identifications and multi-angle captures — so nothing is silently
    dropped from view.
    """
    if df is None or df.empty:
        return [], pd.DataFrame()

    rows = df.to_dict("records")

    children_by_parent: dict[str, list[dict]] = {}
    for row in rows:
        parent = row.get("parent_specimen_id")
        if parent:
            children_by_parent.setdefault(str(parent), []).append(row)

    events: list[dict] = []
    accounted: set[str] = set()

    for row in rows:
        screening = _as_screening_dict(row.get("field_screening_result"))
        if screening.get("screening_method") != "manual_field_log":
            continue

        specimen_id = str(row.get("specimen_id"))
        accounted.add(specimen_id)
        result = screening.get("result") or {}
        vialed_tally = result.get("vialed_out") or {}

        genus_counts = {}
        for genus, count_key in _FIELD_LOG_GENUS_KEYS.items():
            caught = int(result.get(count_key, 0) or 0)
            vialed = int(vialed_tally.get(genus, 0) or 0)
            if caught or vialed:
                genus_counts[genus] = {
                    "caught": caught,
                    "vialed": vialed,
                    "in_batch": max(0, caught - vialed),
                }

        other_caught = int(result.get("other_genera_count", 0) or 0)
        if other_caught:
            # "Other" cannot be vialed out (only the three tracked genera can), so its
            # whole count always remains in the batch.
            genus_counts["Other"] = {"caught": other_caught, "vialed": 0, "in_batch": other_caught}

        children = children_by_parent.get(specimen_id, [])
        for child in children:
            accounted.add(str(child.get("specimen_id")))

        events.append({
            "specimen_id": specimen_id,
            "collection_date": row.get("collection_date"),
            "breeding_site_type": row.get("breeding_site_type"),
            "collector": extract_collector_display(row),
            "field_notes": (result.get("field_notes") or "").strip(),
            "genus_counts": genus_counts,
            "total_caught": sum(c["caught"] for c in genus_counts.values()),
            "total_vialed": sum(c["vialed"] for c in genus_counts.values()),
            "children": [summarise_vialed_child(c) for c in children],
        })

    events.sort(key=lambda e: str(e["collection_date"] or ""), reverse=True)

    other_rows = df[~df["specimen_id"].astype(str).isin(accounted)] if "specimen_id" in df.columns else pd.DataFrame()
    return events, other_rows


def specimens_ready_for_pcr(df: pd.DataFrame) -> pd.DataFrame:
    """The specimens a PCR confirmation can be attached to: the identified ones.

    A batch field log is not one — it is a bulk count of a night's catch, not an
    individual, and there is no single mosquito for a PCR result to describe. A vialed
    specimen nobody has identified yet is not one either: PCR confirms or overturns an
    identification, so without one there is nothing to confirm.
    """
    if df is None or df.empty or "field_screening_result" not in df.columns:
        return pd.DataFrame()

    identified = df["field_screening_result"].apply(
        lambda fs: _as_screening_dict(fs).get("screening_method") in IDENTIFICATION_METHODS
    )
    out = df[identified].copy()
    if "collection_date" in out.columns:
        out = out.sort_values("collection_date", ascending=False)
    return out


def _clean_label_part(value) -> str:
    """Coerce a DataFrame-record value into a clean label string.

    DataFrame.to_dict("records") renders a missing cell as float NaN (dates as
    NaT), both truthy — so callers can't just test `if value`. Returns "" for
    missing/NaN, else the stripped string form. Never raises: label building must
    not take a page down.
    """
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def pcr_specimen_label(row: dict) -> str:
    """Human-readable option label for the PCR specimen picker.

    A bare UUID tells lab staff nothing about which tube is in their hand, so lead with
    the tube label and the identification.
    """
    screening = _as_screening_dict(row.get("field_screening_result"))
    genus = extract_primary_genus(screening) or "undetermined"
    # A row from DataFrame.to_dict("records") carries a missing tube_label / date as a
    # float NaN, which is truthy — so `[tube] if tube else []` kept the NaN and
    # " · ".join() then blew up ("expected str instance, float found"). An identified
    # specimen that was never vialed out has no tube_label at all, so this is the
    # common case, not an edge one. Coerce every part to a clean string.
    tube = _clean_label_part(row.get("tube_label"))
    date = _clean_label_part(row.get("collection_date")) or "undated"
    short_id = str(row.get("specimen_id") or "")[:8]

    parts = [tube] if tube else []
    parts += [str(genus), date, f"{short_id}…"]
    prefix = "✔ " if (row.get("pcr_status") == "confirmed") else ""
    return prefix + " · ".join(parts)


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
    specimen_id: str, screening_method: str, result: dict, photo_urls: list | None = None
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
            .select("field_screening_result, photo_urls")
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

    update_payload: dict = {"field_screening_result": field_screening_result}

    # Append the images the identification was made from, rather than replacing whatever
    # the specimen already had — a field photo taken at collection and a lab photo taken
    # at identification are both evidence, and neither should evict the other.
    if photo_urls:
        prior_photos = existing_row.get("photo_urls") or []
        if not isinstance(prior_photos, list):
            prior_photos = []
        update_payload["photo_urls"] = [*prior_photos, *photo_urls]

    try:
        response = (
            client.table("specimen_records")
            .update(update_payload)
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


def extract_genus_counts_from_screening(field_screening_result: dict | None) -> dict:
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


# The sentinel sql/enforce_collector_id.sql backfills onto rows written before identity
# was enforced. Their author was never recorded anywhere and cannot be recovered, so they
# are labelled as what they are rather than attributed to a guess.
UNATTRIBUTED_LEGACY = "unattributed-legacy"


def extract_collector_display(row) -> str:
    """The collector to show for one specimen_records row, for tables and exports.

    Prefers the human-readable collector_label stamped into field_screening_result at
    write time; a bare collector_id is a UUID, which tells a reader nothing. Falls back to
    a truncated id for rows written before the label existed, so the cell is never blank —
    an empty Collector column is exactly the ambiguity this whole change set removed.
    """
    if not isinstance(row, dict):
        return "Unknown"

    collector_id = str(row.get("collector_id") or "").strip()
    if collector_id == UNATTRIBUTED_LEGACY:
        return "Unattributed (pre-identity record)"

    screening = row.get("field_screening_result") or {}
    if isinstance(screening, str):
        try:
            screening = json.loads(screening)
        except Exception:
            logger.debug("Could not JSON-decode field_screening_result for collector display", exc_info=True)
            screening = {}
    label = (screening.get("collector_label") or "").strip() if isinstance(screening, dict) else ""

    if label:
        return label
    if collector_id:
        # Pre-label row: show enough of the id to tell two collectors apart, no more.
        return f"ID {collector_id[:8]}…"
    return "Unknown"


def add_collector_column(df: pd.DataFrame, column: str = "Collector") -> pd.DataFrame:
    """Return a copy of a specimen_records DataFrame with a human-readable collector column."""
    if df is None or df.empty:
        return df
    out = df.copy()
    out[column] = [extract_collector_display(row) for row in out.to_dict("records")]
    return out


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
        # genus_triage is written as {"genus": ...}. It is JSONB, though, so a row shaped
        # differently must not take the whole dashboard down with an AttributeError.
        if isinstance(genus_triage, dict):
            return genus_triage.get("genus")
        if isinstance(genus_triage, str) and genus_triage:
            return genus_triage
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
    except Exception as e:
        logger.exception("Could not save bioassay result")
        st.error(f"Could not save bioassay result: {e}")
        return None

    # load_bioassay_results is cached for 60s: without this the user saves a replicate and
    # the table below the form keeps showing the set without it, as if the save was lost.
    clear_bioassay_results_cache()
    return first_row(response)


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
    except Exception as e:
        logger.exception("Could not save clinical case record")
        st.error(f"Could not save clinical case record: {e}")
        return None

    clear_clinical_case_data_cache()
    return first_row(response)


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
