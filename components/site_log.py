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
    clear_specimen_records_cache,
    load_specimen_records,
    submit_site_log_entry,
)
from utils.icons import render_page_header

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
                    if saved.get("photo_urls"):
                        st.image(saved["photo_urls"][0], caption="Uploaded photo", width=200)
                else:
                    st.error("Entry was not saved — check the database connection and try again.")

    st.markdown("---")
    _render_recent_entries()


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
