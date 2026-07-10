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
from typing import Any, Dict, Optional

import pandas as pd
import qrcode
import streamlit as st
from supabase import Client

try:
    from utils.config import get_base_supabase_client
except Exception:  # pragma: no cover - fallback for local use
    def get_base_supabase_client():
        return None


def generate_qr_code_image(specimen_id: str, box_size: int = 10, border: int = 4) -> bytes:
    """Generate a QR code PNG for a specimen_id and return raw image bytes."""
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=box_size, border=border)
    qr.add_data(str(specimen_id))
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def get_supabase_client() -> Optional[Client]:
    """Return the active Supabase client when configured."""
    return get_base_supabase_client()


def upsert_specimen_record(client: Client, record: Dict[str, Any]) -> Dict[str, Any]:
    """Insert or update a specimen record in Supabase."""
    if client is None:
        raise RuntimeError("Supabase client is not available")
    response = client.table("specimen_records").upsert(record, on_conflict="specimen_id").execute()
    if getattr(response, "data", None):
        return response.data[0]
    raise RuntimeError("Failed to upsert specimen record")


def fetch_specimen_by_id(client: Client, specimen_id: str) -> Optional[Dict[str, Any]]:
    """Fetch a specimen record by specimen_id."""
    if client is None:
        raise RuntimeError("Supabase client is not available")
    response = client.table("specimen_records").select("*").eq("specimen_id", specimen_id).execute()
    if getattr(response, "data", None):
        return response.data[0] if response.data else None
    return None


def render_pcr_confirmation_form() -> None:
    """Render a Streamlit form for lab staff to look up and update a specimen record."""
    st.subheader("PCR Confirmation Entry")
    st.caption("Scan or enter the specimen QR ID to link the physical specimen to its database record.")

    client = get_supabase_client()
    if client is None:
        st.warning("Supabase is not configured. Set SUPABASE_URL and SUPABASE_ANON_KEY to enable database updates.")
        return

    specimen_id_input = st.text_input("Specimen ID (QR value)", placeholder="UUID or specimen ID")

    if st.button("Look up specimen") and specimen_id_input:
        record = fetch_specimen_by_id(client, specimen_id_input)
        if record is None:
            st.error("No specimen record found. Confirm the QR code value or create the record first.")
            return

        st.success(f"Loaded specimen {record['specimen_id']}")
        st.json(record)

        with st.form("pcr_confirmation_form"):
            st.write("### PCR confirmation details")
            pcr_status = st.selectbox(
                "PCR status",
                options=["not_submitted", "pending", "confirmed"],
                index=["not_submitted", "pending", "confirmed"].index(record.get("pcr_status") or "not_submitted"),
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
                value=pd.to_datetime(record.get("pcr_confirmed_date")) if record.get("pcr_confirmed_date") else None,
            )

            submitted = st.form_submit_button("Submit PCR result")
            if submitted:
                payload = {
                    "specimen_id": record["specimen_id"],
                    "pcr_status": pcr_status,
                    "pcr_confirmed_species": pcr_confirmed_species or None,
                    "pcr_lab_reference": pcr_lab_reference or None,
                    "pcr_confirmed_date": pcr_confirmed_date.isoformat() if pcr_confirmed_date else None,
                }
                updated = upsert_specimen_record(client, payload)
                st.success(f"PCR result saved for specimen {updated['specimen_id']}")
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


def _is_correct_match(predicted_label: str, confirmed_species: str) -> bool:
    """
    Transparent, simple string/complex matching between a predicted label
    and the PCR-confirmed species. Extend the complex membership lists here
    if new complexes are added to the taxonomy.
    """
    predicted_lower = str(predicted_label).strip().lower()
    species_lower = str(confirmed_species).strip().lower()

    if "gambiae" in predicted_lower and any(
        s in species_lower for s in
        ["gambiae", "coluzzii", "arabiensis", "merus", "melas", "quadriannulatus"]
    ):
        return True
    if "funestus" in predicted_lower and any(
        s in species_lower for s in
        ["funestus", "rivulorum", "parensis", "leesoni", "vaneedeni"]
    ):
        return True
    if "culex" in predicted_lower and "culex" in species_lower:
        return True
    if "aedes" in predicted_lower and "aedes" in species_lower:
        return True
    if (
        "anopheles" in predicted_lower and "anopheles" in species_lower
        and "gambiae" not in predicted_lower and "funestus" not in predicted_lower
    ):
        # Pure genus-level Anopheles call (e.g. from larval screening) counts
        # as correct if the confirmed species is any Anopheles.
        return True

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
    rows = response.data or []

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
                st.dataframe(pd.DataFrame(data["by_complex"]), use_container_width=True, hide_index=True)
