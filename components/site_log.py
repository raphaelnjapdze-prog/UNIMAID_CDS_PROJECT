"""
Single Site Log Entry — replaces CSV upload entirely.

One form, one save button, one photo field, writes straight to
specimen_records via utils.data_manager.submit_site_log_entry(). No
fabricated success states: a save either genuinely succeeds (confirmed by
the returned row) or shows a real error.
"""

from datetime import date

import pandas as pd
import streamlit as st

from utils.data_manager import (
    available_to_vial,
    clear_specimen_records_cache,
    fetch_batch_children,
    load_specimen_records,
    submit_site_log_entry,
    vial_out_specimens,
)
from utils.icons import render_page_header
from utils.pcr_and_accuracy import render_specimen_qr

_SUBSAMPLE_GENERA = ["Anopheles", "Culex", "Aedes"]

_BREEDING_SITE_OPTIONS = [
    "Stagnant pool",
    "Swamp / marsh margin",
    "Rice field / irrigated field",
    "Rain pool (temporary)",
    "Concrete water tank",
    "Plastic container / drum",
    "Tyre / discarded container",
    "Drainage channel / gutter",
    "Rock pool",
    "River margin / backwater",
    "Other (specify in notes)",
]


def _validate(anoph, culex, aedes, other, lat, lon, has_gps) -> str | None:
    """Returns an error message if invalid, else None."""
    if any(v < 0 for v in [anoph, culex, aedes, other]):
        return "Counts cannot be negative."
    if has_gps:
        if lat is None or lon is None:
            return "GPS was enabled but latitude/longitude is missing."
        if not (-90.0 <= lat <= 90.0):
            return "Latitude must be between -90 and 90."
        if not (-180.0 <= lon <= 180.0):
            return "Longitude must be between -180 and 180."
    return None


def render_site_log_page():
    render_page_header("Site Log Entry", "log")
    st.caption(
        "Log one field observation directly — counts, habitat, GPS, and an "
        "optional photo. Saved immediately to specimen_records; no upload "
        "step, no intermediate file."
    )

    # GPS toggle lives OUTSIDE the form so its conditional fields can
    # actually appear before submission — st.form doesn't rerun on
    # interior widget changes until the submit button is pressed.
    has_gps = st.checkbox("I have GPS coordinates for this site", key="site_log_has_gps")
    gps_lat, gps_lon = None, None
    if has_gps:
        gcol1, gcol2 = st.columns(2)
        with gcol1:
            gps_lat = st.number_input(
                "Latitude", value=11.8000, format="%.6f", min_value=-90.0, max_value=90.0,
                key="site_log_lat",
            )
        with gcol2:
            gps_lon = st.number_input(
                "Longitude", value=13.1500, format="%.6f", min_value=-180.0, max_value=180.0,
                key="site_log_lon",
            )

    with st.form("site_log_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            collection_date = st.date_input("Collection date", value=date.today())
            breeding_site_type = st.selectbox("Breeding site type", _BREEDING_SITE_OPTIONS)

        with col2:
            anopheles_count = st.number_input("Anopheles count", min_value=0, value=0, step=1)
            culex_count = st.number_input("Culex count", min_value=0, value=0, step=1)
            aedes_count = st.number_input("Aedes count", min_value=0, value=0, step=1)
            other_genera_count = st.number_input("Other genera count", min_value=0, value=0, step=1)

        field_notes = st.text_area(
            "Field notes",
            placeholder="Water clarity, vegetation, nearby dwellings, anything relevant...",
        )

        photo_file = st.file_uploader(
            "Field photo (optional)", type=["png", "jpg", "jpeg"],
            help="Uploaded to the specimen-photos storage bucket and linked to this entry.",
        )

        submitted = st.form_submit_button("Save Site Log Entry", type="primary", use_container_width=True)

        if submitted:
            error = _validate(
                anopheles_count, culex_count, aedes_count, other_genera_count,
                gps_lat, gps_lon, has_gps,
            )
            if error:
                st.error(error)
            else:
                with st.spinner("Saving entry..."):
                    saved = submit_site_log_entry(
                        collection_date=collection_date,
                        breeding_site_type=breeding_site_type,
                        gps_lat=gps_lat,
                        gps_lon=gps_lon,
                        anopheles_count=anopheles_count,
                        culex_count=culex_count,
                        aedes_count=aedes_count,
                        other_genera_count=other_genera_count,
                        field_notes=field_notes,
                        photo_file=photo_file,
                    )
                if saved:
                    clear_specimen_records_cache()
                    st.success(f"Saved. Specimen ID: {saved['specimen_id']}")
                    st.caption("Print this QR label and attach it to the physical specimen so the lab can link it to PCR results.")
                    label_col, photo_col = st.columns(2)
                    with label_col:
                        render_specimen_qr(saved["specimen_id"], key="qr_sitelog_save")
                    with photo_col:
                        if saved.get("photo_urls"):
                            st.image(saved["photo_urls"][0], caption="Uploaded photo", width=200)
                else:
                    st.error("Entry was not saved — check the database connection and try again.")

    st.markdown("---")
    _render_subsampling()

    st.markdown("---")
    _render_recent_entries()


def _batch_label(row) -> str:
    """Human-readable label for a batch in the subsampling selector, showing how many
    of each genus remain available to vial out."""
    avail = " ".join(
        f"{g[:2]}:{available_to_vial(row, g)}" for g in _SUBSAMPLE_GENERA
    )
    date_str = str(row.get("collection_date") or "?")
    site = row.get("breeding_site_type") or "site n/a"
    return f"{date_str} · {site} · [{avail}] · {str(row.get('specimen_id'))[:8]}"


def _render_child_labels(children: list, key_prefix: str) -> None:
    """Render a printable QR label per vialed specimen, three across."""
    for start in range(0, len(children), 3):
        cols = st.columns(3)
        for col, child in zip(cols, children[start:start + 3]):
            with col:
                tube = child.get("tube_label")
                caption = f"{tube}" if tube else str(child["specimen_id"])[:8]
                render_specimen_qr(
                    child["specimen_id"],
                    caption=caption,
                    key=f"{key_prefix}_{child['specimen_id']}",
                    width=150,
                )


def _render_subsampling():
    """Vial out individual specimens from a batch field-count log so each can be
    barcoded, identified, and PCR-confirmed on its own — matching a single
    morphological ID to a single molecular result per mosquito."""
    st.subheader("Subsample Specimens for PCR")
    st.caption(
        "A field count logs many mosquitoes as one batch. To confirm species by PCR, "
        "'vial out' individual specimens: each gets its own QR/barcode and can be "
        "identified and PCR-confirmed separately. The batch's original counts are kept "
        "intact — vialed specimens are just tracked individually so totals never double-count."
    )

    df = load_specimen_records()
    if df.empty or "field_screening_result" not in df.columns:
        st.info("No batch field-count logs yet. Save a site log entry above first.")
        return

    def _is_field_log(result):
        return isinstance(result, dict) and result.get("screening_method") == "manual_field_log"

    batches = df[df["field_screening_result"].apply(_is_field_log)].copy()
    if batches.empty:
        st.info("No batch field-count logs yet. Save a site log entry above first.")
        return

    batch_rows = batches.to_dict("records")
    labels = {_batch_label(r): r for r in batch_rows}
    chosen_label = st.selectbox("Batch collection event", list(labels.keys()), key="subsample_batch")
    batch = labels[chosen_label]
    batch_id = batch["specimen_id"]

    available = {g: available_to_vial(batch, g) for g in _SUBSAMPLE_GENERA}
    selectable = [g for g, n in available.items() if n > 0]

    if not selectable:
        st.warning("Every counted specimen in this batch has already been vialed out.")
    else:
        col1, col2, col3 = st.columns([2, 1, 2])
        with col1:
            genus = st.selectbox(
                "Genus to subsample",
                selectable,
                format_func=lambda g: f"{g} ({available[g]} available)",
                key="subsample_genus",
            )
        with col2:
            count = st.number_input(
                "How many", min_value=1, max_value=int(available[genus]), value=1, step=1,
                key="subsample_count",
            )
        with col3:
            tube_prefix = st.text_input(
                "Tube label prefix (optional)", placeholder="e.g. LAB-2026-07",
                key="subsample_prefix",
            )

        if st.button(f"Vial out {int(count)} {genus} specimen(s)", type="primary", key="subsample_go"):
            with st.spinner("Creating individual specimen records…"):
                children = vial_out_specimens(
                    batch_id, genus, int(count), tube_prefix.strip() or None
                )
            if children:
                st.success(
                    f"Vialed out {len(children)} {genus} specimen(s). Print each label and "
                    f"attach it to that specimen's tube — scan it later to record the "
                    f"morphological ID and PCR result for that individual."
                )
                _render_child_labels(children, key_prefix="fresh")

    # Existing individuals already vialed out of this batch (for reprint / PCR tracking).
    existing = fetch_batch_children(batch_id)
    if not existing.empty:
        with st.expander(f"Individuals already vialed from this batch ({len(existing)})"):
            cols = [c for c in ["tube_label", "specimen_id", "pcr_status", "pcr_confirmed_species"] if c in existing.columns]
            st.dataframe(
                existing[cols].rename(columns={
                    "tube_label": "Tube",
                    "specimen_id": "Specimen ID (QR)",
                    "pcr_status": "PCR Status",
                    "pcr_confirmed_species": "PCR Species",
                }),
                use_container_width=True,
                hide_index=True,
            )


def _render_recent_entries():
    st.subheader("Recently Logged Entries")

    df = load_specimen_records()
    if df.empty:
        st.info("No entries logged yet.")
        return

    def _is_field_log(result):
        if isinstance(result, dict):
            return result.get("screening_method") == "manual_field_log"
        return False

    log_df = df[df["field_screening_result"].apply(_is_field_log)].copy()
    if log_df.empty:
        st.info("No site log entries yet — identification-only records exist, but no field counts.")
        return

    log_df["collection_date"] = pd.to_datetime(log_df["collection_date"], errors="coerce")
    log_df = log_df.sort_values("collection_date", ascending=False)

    def _counts(result):
        r = result.get("result", {})
        return f"An:{r.get('anopheles_count',0)} Cx:{r.get('culex_count',0)} Ae:{r.get('aedes_count',0)}"

    log_df["counts"] = log_df["field_screening_result"].apply(_counts)

    display_cols = ["collection_date", "breeding_site_type", "counts", "pcr_status"]
    display_cols = [c for c in display_cols if c in log_df.columns]

    st.dataframe(
        log_df[display_cols].head(10).rename(columns={
            "collection_date": "Date",
            "breeding_site_type": "Site Type",
            "counts": "Counts",
            "pcr_status": "PCR Status",
        }),
        use_container_width=True,
        hide_index=True,
    )
