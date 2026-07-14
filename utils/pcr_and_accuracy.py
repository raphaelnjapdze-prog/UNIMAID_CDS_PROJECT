"""Utilities for specimen QR codes, PCR confirmation, and accuracy reporting.

This module is designed for a Python/Streamlit app backed by Supabase/Postgres.
It provides:
1. QR code generation for specimen IDs
2. A Streamlit lab form for PCR confirmation entry
3. Accuracy reporting comparing field AI outputs to PCR-confirmed species —
   split by screening_method (manual_checklist / ai_vision / trained_classifier)
   so different tools are never blended into one misleading number.
"""

from __future__ import annotations

import io
from datetime import date, datetime
from typing import Any, Dict, Optional

import pandas as pd
import qrcode
import streamlit as st
from qrcode.constants import ERROR_CORRECT_M
from supabase import Client

from utils.auth import get_supabase_client
from utils.data_manager import (
    clear_specimen_records_cache,
    first_row,
    load_specimen_records,
    pcr_specimen_label,
    response_rows,
    specimens_ready_for_pcr,
)
from utils.logging_config import get_logger
from utils.morphology_keys import complex_membership_by_trigger

logger = get_logger(__name__)


def _as_date(value: Any) -> Optional[date]:
    """Coerce a stored pcr_confirmed_date into the `date` st.date_input expects.

    Postgres `date` columns come back over PostgREST as ISO strings, but a caller may
    also hand us a real date/datetime. Anything unparseable yields None (an empty field)
    rather than crashing the lab form — and says so in the log instead of silently.
    """
    if not value:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        logger.warning("Unparseable pcr_confirmed_date %r; leaving the field blank", value)
        return None


def generate_qr_code_image(specimen_id: str, box_size: int = 10, border: int = 4) -> bytes:
    """Generate a QR code PNG for a specimen_id and return raw image bytes."""
    qr = qrcode.QRCode(version=1, error_correction=ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(str(specimen_id))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    # get_image() unwraps qrcode's PilImage to the underlying PIL Image, whose save()
    # actually declares `format`. Byte-for-byte identical output.
    img.get_image().save(buf, format="PNG")
    return buf.getvalue()


def render_specimen_qr(
    specimen_id: Any,
    *,
    caption: Optional[str] = None,
    key: Optional[str] = None,
    width: int = 180,
) -> None:
    """Render a specimen's QR label in Streamlit: the QR image plus a PNG
    download button so the label can be printed and stuck on the physical tube.

    This is the single UI entry point for specimen QR codes — used at capture
    time (site log / diagnostics saves), on lab lookup, and for reprinting from
    the specimen list. All of them link the physical specimen back to this exact
    database row, which is what makes PCR confirmation possible.
    """
    if not specimen_id:
        st.caption("No specimen ID available for a QR label.")
        return
    try:
        png = generate_qr_code_image(str(specimen_id))
    except Exception:
        logger.warning("QR generation failed for specimen %s", specimen_id, exc_info=True)
        st.caption("Could not generate a QR code for this specimen.")
        return

    st.image(png, caption=caption or f"Specimen {specimen_id}", width=width)
    st.download_button(
        "⬇ Download QR label (PNG)",
        data=png,
        file_name=f"specimen_{specimen_id}.png",
        mime="image/png",
        key=key or f"qr_dl_{specimen_id}",
        width="stretch",
    )


def upsert_specimen_record(client: Client, record: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a specimen record in Supabase."""
    if client is None:
        raise RuntimeError("Supabase client is not available")
    response = client.table("specimen_records").upsert(record, on_conflict="specimen_id").execute()
    row = first_row(response)
    if row is None:
        raise RuntimeError("Failed to upsert specimen record")
    # The ledger this row belongs to is cached for 60s. Without this, a lab confirms a
    # species and the dashboard, accuracy report and specimen tables keep showing the
    # unconfirmed row back to them — looking like the confirmation was lost.
    clear_specimen_records_cache()
    return row


def fetch_specimen_by_id(client: Client, specimen_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a specimen record by specimen_id."""
    if client is None:
        raise RuntimeError("Supabase client is not available")
    response = client.table("specimen_records").select("*").eq("specimen_id", specimen_id).execute()
    return first_row(response)


_MANUAL_ENTRY = "Enter an ID manually / scan a QR…"
_NOTHING_SELECTED = "— Select a specimen —"


def _pcr_target_specimen_id() -> str:
    """Which specimen the lab is confirming: picked from the list, or typed/scanned.

    Lab staff hold a tube, not a UUID, so the list leads with the tube label and the
    identification. Manual entry stays, for a QR scanned straight into the box.
    """
    candidates = specimens_ready_for_pcr(load_specimen_records())

    if candidates.empty:
        st.info(
            "No identified specimens yet. PCR confirms or overturns an identification, so "
            "identify a specimen on the Diagnostics page first — then it appears here."
        )
        return st.text_input(
            "Specimen ID (QR value)", key="pcr_manual_id", placeholder="UUID or specimen ID"
        ).strip()

    labels = {pcr_specimen_label(row): row["specimen_id"] for row in candidates.to_dict("records")}

    choice = st.selectbox(
        "Identified specimen",
        options=[_NOTHING_SELECTED, *labels.keys(), _MANUAL_ENTRY],
        key="pcr_specimen_choice",
        help="Vialed specimens that have been identified. ✔ marks one already PCR-confirmed.",
    )

    if choice == _MANUAL_ENTRY:
        return st.text_input(
            "Specimen ID (QR value)", key="pcr_manual_id", placeholder="UUID or specimen ID"
        ).strip()
    if choice == _NOTHING_SELECTED:
        return ""
    return str(labels[choice])


def render_pcr_confirmation_form() -> None:
    """Render a Streamlit form for lab staff to look up and update a specimen record."""
    st.subheader("PCR Confirmation Entry")
    st.caption("Pick the identified specimen, or scan its QR value, then record the PCR result.")

    client = get_supabase_client()
    if client is None:
        st.warning("Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY to enable database updates.")
        return

    specimen_id = _pcr_target_specimen_id()
    if not specimen_id:
        return

    record = fetch_specimen_by_id(client, specimen_id)
    if record is None:
        st.error("No specimen record found. Confirm the QR code value or create the record first.")
        return

    # NOTE: everything below is rendered unconditionally, NOT inside `if st.button(...)`.
    # It used to be: the form was only instantiated on the run where "Look up specimen" was
    # clicked, so the rerun that a Submit click triggers re-evaluated that button as False,
    # the form was never created, and the PCR result was silently discarded — the same bug
    # that was fixed on the Diagnostics page.
    detail_col, qr_col = st.columns([3, 1])
    with detail_col:
        with st.expander("Specimen record"):
            st.json(record)
    with qr_col:
        st.markdown("**Specimen label**")
        render_specimen_qr(record["specimen_id"], key="qr_pcr_lookup")

    statuses = ["not_submitted", "pending", "confirmed"]
    with st.form("pcr_confirmation_form"):
        st.write("### PCR confirmation details")
        pcr_status = st.selectbox(
            "PCR status",
            options=statuses,
            index=statuses.index(record.get("pcr_status") or "not_submitted"),
        )
        pcr_confirmed_species = st.text_input(
            "PCR-confirmed species",
            value=record.get("pcr_confirmed_species") or "",
            placeholder="e.g. Anopheles coluzzii",
        )
        pcr_lab_reference = st.text_input(
            "Lab reference / batch ID",
            value=record.get("pcr_lab_reference") or "",
            placeholder="e.g. LAB-2026-001",
        )
        pcr_confirmed_date = st.date_input(
            "PCR confirmed date",
            value=_as_date(record.get("pcr_confirmed_date")),
        )

        submitted = st.form_submit_button("Submit PCR result", type="primary")

    if submitted:
        payload = {
            "specimen_id": record["specimen_id"],
            "pcr_status": pcr_status,
            "pcr_confirmed_species": pcr_confirmed_species or None,
            "pcr_lab_reference": pcr_lab_reference or None,
            "pcr_confirmed_date": pcr_confirmed_date.isoformat() if pcr_confirmed_date else None,
        }
        try:
            updated = upsert_specimen_record(client, payload)
        except Exception as e:
            logger.exception("PCR upsert failed for %s", record["specimen_id"])
            st.error(f"The PCR result was not saved: {e}")
            return

        st.success(f"PCR result saved for specimen {updated['specimen_id']}")
        with st.expander("Updated record"):
            st.json(updated)


def _extract_predicted_label(field_screening_result: Dict[str, Any]) -> Optional[str]:
    """
    Pull the best available predicted species/complex/genus label out of a
    stored field_screening_result, regardless of which screening_method
    produced it. Each method stores its raw output in a different shape
    under "result" — this is the single place that knows how to read all
    of them, so accuracy reporting doesn't silently break when a method's
    result shape differs from the others.
    """
    if not field_screening_result:
        return None

    method = field_screening_result.get("screening_method")
    result = field_screening_result.get("result") or {}

    if method == "ai_vision":
        # Adult vision results carry "best_match" (species/complex/group).
        # Larval vision results only ever resolve to genus level.
        return result.get("best_match") or result.get("genus")

    if method == "manual_checklist":
        # Anopheles deep-key engine (character scoring or couplet key) resolves a
        # rich taxon — "An. gambiae complex", "Anopheles pharoensis", etc. Prefer
        # that over the bare genus so accuracy credits complex/species precision
        # rather than scoring every deep-key call as genus-level "Anopheles".
        deep = result.get("anopheles_deep_key") or result.get("anopheles_couplet_key")
        if deep and deep.get("taxon"):
            return deep["taxon"]

        # Adult checklist: prefer the top species/complex candidate if the
        # user ticked enough markers to narrow past genus; fall back to
        # genus_triage if no candidates matched.
        candidates = result.get("species_candidates")
        if candidates:
            top = candidates[0]
            group = top.get("group_complex")
            return group if group not in (None, "None") else top.get("species_name")
        genus_triage = result.get("genus_triage")
        if genus_triage:
            return genus_triage.get("genus")
        # Larval checklist result is flatter — genus/resolved_genus at top level
        return result.get("genus") or result.get("resolved_genus")

    if method == "trained_classifier":
        # Convention for when the trained classifier is wired in: it should
        # store {"predicted_species": "...", "confidence": ...} in "result".
        return result.get("predicted_species") or result.get("genus")

    # Unknown/legacy method — fall back to the original loose keys, in case
    # of hand-inserted or older records.
    return result.get("predicted_complex") or result.get("complex") or result.get("group")


# Cryptic-complex / species-group membership, keyed by the trigger word that
# appears in a complex/group prediction label (e.g. "An. gambiae complex" ->
# "gambiae"). A prediction naming one of these complexes/groups is scored
# correct against ANY member, because morphology (and the deep key) genuinely
# cannot split the complex to species — only PCR can.
#
# The membership data itself is owned by utils.morphology_keys.SPECIES_COMPLEXES
# (the single source of truth, also used by the deep-key engine). We derive the
# trigger->members map from there so PCR scoring and the identification engine
# can never drift out of sync.
COMPLEX_MEMBERSHIP = complex_membership_by_trigger()

_GENERA = {"anopheles", "culex", "aedes"}


def _norm(label: Any) -> str:
    return str(label or "").strip().lower()


def _pure_genus(label_lower: str) -> Optional[str]:
    """Return the genus if `label_lower` is a genus-only call (e.g. "anopheles",
    "anopheles spp."), else None. A genus-only prediction is honestly correct
    against any confirmed species of that genus, but a species/complex label is
    NOT genus-only and must be matched more strictly."""
    tokens = [t for t in label_lower.replace(".", " ").split() if t not in ("sp", "spp")]
    if len(tokens) == 1 and tokens[0] in _GENERA:
        return tokens[0]
    return None


def _complex_members_for(label_lower: str) -> Optional[list[str]]:
    """If the prediction names a known cryptic complex/group, return its member
    epithets; else None. Detected by the presence of the complex trigger word
    together with a 'complex'/'group' marker, or a bare complex trigger word."""
    for trigger, members in COMPLEX_MEMBERSHIP.items():
        if trigger in label_lower:
            return members
    return None


def _is_correct_match(predicted_label: str, confirmed_species: str) -> bool:
    """
    Rank-aware match between a predicted label and the PCR-confirmed species.

    The scoring respects what each prediction could legitimately resolve:
      • Complex/group prediction  -> correct if confirmed is ANY member
        (morphology can't split the complex; only PCR can).
      • Genus-only prediction     -> correct if confirmed shares that genus.
      • Species-level prediction  -> correct only if the confirmed species
        actually matches (no free genus-level credit).

    Extend COMPLEX_MEMBERSHIP above when new complexes enter the taxonomy.
    """
    predicted_lower = _norm(predicted_label)
    species_lower = _norm(confirmed_species)
    if not predicted_lower or not species_lower:
        return False

    # 1. Complex/group prediction — credited against any member.
    members = _complex_members_for(predicted_lower)
    if members is not None:
        return any(m in species_lower for m in members)

    # 2. Genus-only prediction — credited against any species of that genus.
    genus = _pure_genus(predicted_lower)
    if genus is not None:
        return genus in species_lower

    # 3. Species-level (or other specific) prediction — require an actual
    #    species match, so a distinct species is never credited against a
    #    different one of the same genus.
    return predicted_lower in species_lower or species_lower in predicted_lower


def build_accuracy_report(
    client: Optional[Client] = None,
    screening_method: Optional[str] = None,
) -> Dict[str, Any]:
    """Compare AI/checklist field-screening results to PCR-confirmed species.

    Pass screening_method to restrict the report to one tool
    (e.g. "ai_vision") — this is what keeps checklist, vision, and trained-
    classifier accuracy from being blended into one misleading number.
    """
    if client is None:
        client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client is not available")

    response = client.table("specimen_records").select("*").eq("pcr_status", "confirmed").execute()
    rows = response_rows(response)

    if screening_method:
        rows = [
            r for r in rows
            if (r.get("field_screening_result") or {}).get("screening_method") == screening_method
        ]

    if not rows:
        return {"overall": {"total_confirmed": 0, "correct": 0, "accuracy": None}, "by_complex": []}

    records = []
    for row in rows:
        screening = row.get("field_screening_result") or {}
        predicted_label = _extract_predicted_label(screening)
        confirmed_species = row.get("pcr_confirmed_species")
        if not predicted_label or not confirmed_species:
            continue
        records.append({
            "predicted_complex": predicted_label,
            "confirmed_species": confirmed_species,
            "correct": _is_correct_match(predicted_label, confirmed_species),
        })

    if not records:
        return {"overall": {"total_confirmed": len(rows), "correct": 0, "accuracy": None}, "by_complex": []}

    overall_correct = sum(1 for r in records if r["correct"])
    overall_accuracy = overall_correct / len(records)

    by_complex = []
    grouped = pd.DataFrame(records).groupby("predicted_complex")
    for complex_name, frame in grouped:
        correct = int(frame["correct"].sum())
        total = int(len(frame))
        by_complex.append({
            "complex_group": complex_name,
            "total_confirmed": total,
            "correct": correct,
            "accuracy": round(correct / total, 3) if total else None,
        })

    return {
        "overall": {
            "total_confirmed": len(records),
            "correct": overall_correct,
            "accuracy": round(overall_accuracy, 3),
        },
        "by_complex": sorted(by_complex, key=lambda x: x["complex_group"]),
    }


KNOWN_SCREENING_METHODS = ["manual_checklist", "ai_vision", "trained_classifier"]


def build_accuracy_report_by_method(client: Optional[Client] = None) -> Dict[str, Any]:
    """
    Builds one accuracy report PER screening method, so a checklist
    heuristic, an AI vision guess, and a trained classifier never get
    blended into one misleading number. Also includes a combined/blended
    report, clearly labeled as such, for reference only.
    """
    if client is None:
        client = get_supabase_client()
    if client is None:
        raise RuntimeError("Supabase client is not available")

    by_method = {
        method: build_accuracy_report(client, screening_method=method)
        for method in KNOWN_SCREENING_METHODS
    }
    by_method["_blended_all_methods"] = build_accuracy_report(client, screening_method=None)
    return by_method


def render_accuracy_dashboard() -> None:
    """Streamlit view of accuracy split by screening method."""
    st.subheader("Screening Accuracy vs. PCR Ground Truth")
    st.caption(
        "Each screening method is reported separately so a checklist heuristic, "
        "an AI vision guess, and a trained classifier are never averaged into "
        "one misleading accuracy number."
    )

    client = get_supabase_client()
    if client is None:
        st.warning("Supabase is not configured.")
        return

    if st.button("Refresh accuracy report"):
        st.session_state["_accuracy_report_cache"] = build_accuracy_report_by_method(client)

    report = st.session_state.get("_accuracy_report_cache")
    if not report:
        st.info("Click 'Refresh accuracy report' to compute the latest numbers.")
        return

    method_labels = {
        "manual_checklist":     "Manual Checklist",
        "ai_vision":            "AI Vision Screening",
        "trained_classifier":   "Trained Classifier",
        "_blended_all_methods": "Blended (all methods — reference only)",
    }

    for method_key, label in method_labels.items():
        data = report.get(method_key)
        if not data:
            continue
        overall = data["overall"]
        with st.expander(f"{label} — {overall['total_confirmed']} PCR-confirmed comparisons"):
            if overall["accuracy"] is None:
                st.info("No comparable confirmed records yet for this method.")
                continue
            st.metric(
                "Accuracy",
                f"{overall['accuracy']*100:.1f}%",
                f"{overall['correct']}/{overall['total_confirmed']} correct",
            )
            if data["by_complex"]:
                st.dataframe(pd.DataFrame(data["by_complex"]), width="stretch", hide_index=True)
