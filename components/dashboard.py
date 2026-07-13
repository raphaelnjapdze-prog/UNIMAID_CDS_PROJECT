# =========================================================================
# ENTOMOLOGICAL ANALYTICS & HOTSPOT VISUALIZATION (components/dashboard.py)
#
# Reads exclusively from specimen_records — the real table backing PCR
# confirmation and accuracy reporting. No fabricated data, no fake success
# messages: every number shown here is either real or honestly labeled
# as unavailable.
# =========================================================================
import csv
import json
import os
from datetime import datetime

import folium
import pandas as pd
import streamlit as st
from streamlit_folium import st_folium

from utils.auth import get_supabase_client
from utils.data_manager import (
    add_collector_column,
    extract_primary_genus,
    load_specimen_records,
)
from utils.icons import render_page_header
from utils.logging_config import get_logger

logger = get_logger(__name__)


# ── Real data loading ─────────────────────────────────────────────────────
def _load_specimen_records() -> pd.DataFrame:
    """Loads specimen_records via the canonical cached loader in data_manager."""
    return load_specimen_records()


def _extract_genus(field_screening_result) -> str | None:
    """Genus for dashboard aggregation — delegates to the canonical extractor."""
    return extract_primary_genus(field_screening_result)


def _extract_screening_summary(field_screening_result) -> str:
    """Short human-readable summary for map popups — honest, not padded."""
    if not field_screening_result:
        return "No screening result recorded."
    if isinstance(field_screening_result, str):
        try:
            field_screening_result = json.loads(field_screening_result)
        except Exception:
            return "Screening result could not be parsed."

    method = field_screening_result.get("screening_method", "unknown method")
    genus = _extract_genus(field_screening_result) or "Undetermined"
    method_label = {
        "manual_checklist": "Checklist",
        "ai_vision": "AI vision screening",
        "trained_classifier": "Trained classifier",
    }.get(method, method)
    return f"{genus} ({method_label})"


def _build_dhis2_payload(df: pd.DataFrame) -> str:
    """
    Aggregates real specimen counts by collection date and breeding site
    type into a WHO-style DHIS2 DataValueSet. Org unit codes are derived
    from breeding_site_type as a placeholder grouping key — an admin
    should map these to real DHIS2 facility/org unit codes before this
    is used for an actual submission.
    """
    if df.empty:
        return json.dumps({"dataValues": []}, indent=2)

    working = df.copy()
    working["genus"] = working["field_screening_result"].apply(_extract_genus)
    working = working.dropna(subset=["genus"])

    data_values = []
    if not working.empty:
        grouped = working.groupby(["collection_date", "breeding_site_type", "genus"]).size()
        for (date, site, genus), count in grouped.items():
            period = pd.to_datetime(date).strftime("%Y%m%d") if pd.notna(date) else datetime.now().strftime("%Y%m%d")
            org_unit = f"SITE_{str(site or 'UNSPECIFIED').upper().replace(' ', '_')}"
            element_map = {"Anopheles": "ZVD_LDI_001", "Culex": "ZVD_LDI_002", "Aedes": "ZVD_LDI_003"}
            data_values.append({
                "dataElement": element_map.get(genus, "ZVD_LDI_999"),
                "period": period,
                "orgUnit": org_unit,
                "value": str(int(count)),
            })

    return json.dumps({"dataValues": data_values}, indent=2)


def _save_subscriber(email: str) -> bool:
    """
    Actually persists a subscriber, rather than just showing a success
    toast. Writes to Supabase if configured, otherwise falls back to a
    local CSV — matching the pattern already used elsewhere in this app.
    Returns True only if the write genuinely succeeded.
    """
    client = get_supabase_client()
    if client is not None:
        try:
            client.table("subscribers").insert({
                "email": email,
                "subscribed_at": datetime.now().isoformat(),
            }).execute()
            return True
        except Exception:
            logger.warning("Subscriber insert to Supabase failed; falling back to local CSV", exc_info=True)

    try:
        subs_file = "data/subscribers.csv"
        os.makedirs("data", exist_ok=True)
        header_needed = not os.path.exists(subs_file)
        with open(subs_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            if header_needed:
                writer.writerow(["Email", "Subscribed_At"])
            writer.writerow([_csv_safe(email), datetime.now().isoformat()])
        return True
    except Exception:
        logger.exception("Failed to persist subscriber to local CSV fallback")
        return False


def _csv_safe(value: str) -> str:
    """
    Neutralize spreadsheet formula injection. A value starting with =, +, -, @
    (or a control char) is treated as a formula when the CSV is opened in
    Excel/Sheets; prefixing an apostrophe forces it to be read as text. Quoting
    of delimiters/quotes is handled separately by csv.writer.
    """
    text = str(value)
    if text[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + text
    return text


def render_dashboard_page():
    """Renders the primary surveillance dashboard, sourced entirely from real specimen_records data."""

    hdr_title, hdr_actions = st.columns([4, 1])

    with hdr_title:
        render_page_header(
            title="Surveillance Dashboard",
            icon_name="dashboard",
            caption="Live specimen collection, screening, and confirmation status across monitored sites.",
        )

    df = _load_specimen_records()

    with hdr_actions:
        st.markdown("<div style='margin-top: 22px;'></div>", unsafe_allow_html=True)
        with st.popover("⋮ More Actions", use_container_width=True):
            st.markdown("**Data Export**")
            st.caption(
                "Org unit codes below are derived from breeding_site_type as a "
                "placeholder — map these to real DHIS2 facility codes before use."
            )
            st.markdown("---")
            if st.button("Generate DHIS2 Payload", type="primary", use_container_width=True):
                payload = _build_dhis2_payload(df)
                st.code(payload, language="json")
                st.download_button(
                    "Download payload JSON", data=payload,
                    file_name=f"dhis2_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json", use_container_width=True,
                )
            st.markdown("---")
            if not df.empty:
                st.download_button(
                    "Download raw specimen records (CSV)",
                    data=df.to_csv(index=False),
                    file_name=f"specimen_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv", use_container_width=True,
                )

    st.markdown("---")

    if df.empty:
        st.info(
            "No specimen records found yet. Records appear here once field "
            "screenings are saved from the Diagnostics page, or Supabase isn't "
            "configured — check your connection settings if you expected data."
        )
        return

    # ── Real KPI row ──────────────────────────────────────────────────────
    df["genus"] = df["field_screening_result"].apply(_extract_genus)
    total_specimens = len(df)
    confirmed_count = int((df["pcr_status"] == "confirmed").sum())

    accuracy_display = "No PCR data yet"
    try:
        from utils.pcr_and_accuracy import build_accuracy_report
        client = get_supabase_client()
        if client is not None:
            report = build_accuracy_report(client)
            acc = report["overall"]["accuracy"]
            if acc is not None:
                accuracy_display = f"{acc*100:.1f}% ({report['overall']['correct']}/{report['overall']['total_confirmed']})"
    except Exception:
        logger.debug("Accuracy summary unavailable for dashboard header", exc_info=True)

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Total Specimens Logged", f"{total_specimens:,}")
    kpi2.metric("PCR-Confirmed", f"{confirmed_count:,}")
    kpi3.metric("Screening Accuracy vs. PCR", accuracy_display)
    kpi4.metric(
        "Genus Coverage",
        f"{df['genus'].notna().sum():,} / {total_specimens:,}",
        help="Specimens with a resolvable genus from their screening result.",
    )

    st.markdown("---")

    # ── Map ───────────────────────────────────────────────────────────────
    st.subheader("Geospatial Collection Map")
    st.write("Real collection sites from specimen_records. Click a marker for screening details and photos.")

    map_data = df.dropna(subset=["gps_lat", "gps_lon"]).copy()
    if not map_data.empty:
        map_data["gps_lat"] = pd.to_numeric(map_data["gps_lat"], errors="coerce")
        map_data["gps_lon"] = pd.to_numeric(map_data["gps_lon"], errors="coerce")
        map_data = map_data.dropna(subset=["gps_lat", "gps_lon"])

        center_lat = map_data["gps_lat"].mean()
        center_lon = map_data["gps_lon"].mean()
        m = folium.Map(location=[center_lat, center_lon], zoom_start=12, tiles="OpenStreetMap")

        for _, row in map_data.iterrows():
            summary = _extract_screening_summary(row.get("field_screening_result"))
            site = row.get("breeding_site_type") or "Unspecified site"
            pcr = row.get("pcr_status", "not_submitted")
            photos = row.get("photo_urls") or []
            photo_html = ""
            if photos and isinstance(photos, list) and len(photos) > 0:
                photo_html = (
                    f'<img src="{photos[0]}" width="100%" '
                    f'style="max-height:110px; object-fit:cover; margin-top:6px; border-radius:4px;" />'
                )

            popup_html = f"""
            <div style='font-family:Arial,sans-serif; width:190px; font-size:12px; line-height:1.4;'>
                <b>{site}</b><br>
                Screening: {summary}<br>
                PCR status: {pcr}
                {photo_html}
            </div>
            """
            pcr_color = "green" if pcr == "confirmed" else "orange" if pcr == "pending" else "cadetblue"
            folium.Marker(
                location=[row["gps_lat"], row["gps_lon"]],
                popup=folium.Popup(popup_html, max_width=220),
                icon=folium.Icon(color=pcr_color, icon="tint"),
            ).add_to(m)

        st_folium(m, width=1100, height=520, returned_objects=[])
    else:
        st.info("No specimen records have GPS coordinates recorded yet.")

    st.markdown("---")

    # ── Genus distribution + collection timeline ─────────────────────────
    graph_col1, graph_col2 = st.columns(2)

    with graph_col1:
        st.subheader("Genus Distribution")
        genus_counts = df["genus"].dropna().value_counts()
        if not genus_counts.empty:
            st.bar_chart(genus_counts)
        else:
            st.info("No specimens have a resolvable genus yet.")

    with graph_col2:
        st.subheader("Collection Timeline")
        if "collection_date" in df.columns:
            timeline = df.copy()
            timeline["collection_date"] = pd.to_datetime(timeline["collection_date"], errors="coerce")
            timeline = timeline.dropna(subset=["collection_date"])
            if not timeline.empty:
                daily_counts = timeline.groupby(timeline["collection_date"].dt.date).size()
                st.line_chart(daily_counts)
            else:
                st.info("No valid collection dates recorded yet.")
        else:
            st.info("collection_date column not present in this dataset.")

    st.markdown("---")

    # ── Photo evidence feed ───────────────────────────────────────────────
    has_photos = df["photo_urls"].apply(lambda x: isinstance(x, list) and len(x) > 0)
    if has_photos.any():
        st.subheader("Recent Photo Evidence")
        photo_df = df[has_photos].copy()
        if "collection_date" in photo_df.columns:
            photo_df = photo_df.sort_values(by="collection_date", ascending=False)

        photo_cols = st.columns(4)
        for i, (_, row) in enumerate(photo_df.head(4).iterrows()):
            with photo_cols[i % 4]:
                st.image(
                    row["photo_urls"][0],
                    caption=f"{row.get('breeding_site_type', 'Site')} ({row.get('collection_date', 'n/a')})",
                    use_container_width=True,
                )
        st.markdown("---")

    # ── Full ledger ────────────────────────────────────────────────────────
    with st.expander("View Complete Specimen Ledger"):
        # Show who recorded each specimen: collector_id alone is a UUID, which identifies
        # nobody to a human reader.
        ledger = add_collector_column(df.drop(columns=["genus"], errors="ignore"))
        st.dataframe(ledger, use_container_width=True)

    # ── Footer / subscribe (real persistence, no fake success) ───────────
    st.markdown("<br><hr style='border-top:1px solid #e2e8f0; opacity:0.5;'>", unsafe_allow_html=True)
    ft_info, ft_action = st.columns([2, 1])

    with ft_info:
        st.markdown(
            """
            <div style='color:#94A3B8; font-size:12.5px; line-height:1.5;'>
                <b>Vector Sentinel Portal</b><br>
                Specimen data is stored in the specimen_records table and is not
                fabricated, sampled, or estimated for display purposes.
            </div>
            """,
            unsafe_allow_html=True,
        )

    with ft_action:
        with st.expander("Subscribe to Outbreak Bulletins", expanded=False):
            st.caption("Adds your email to the notification list stored by this app.")
            sub_email = st.text_input(
                "Email", placeholder="user@domain.edu.ng", label_visibility="collapsed", key="dash_sub_email"
            )
            if st.button("Enroll", use_container_width=True, key="dash_sub_btn"):
                if not sub_email or "@" not in sub_email:
                    st.error("Please enter a valid email address.")
                elif _save_subscriber(sub_email):
                    st.success(f"Saved: {sub_email}")
                else:
                    st.error("Could not save your subscription — check database/storage connection.")
