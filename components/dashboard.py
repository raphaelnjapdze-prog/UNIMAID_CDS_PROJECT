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
    build_collection_events,
    extract_genus_counts_from_screening,
    extract_primary_genus,
    load_specimen_records,
)
from utils.dhis2_client import (
    configured_period_type,
    convert_date_to_dhis2_period,
    data_element_for_genus,
    is_unmapped,
    org_unit_for_lga,
    unmapped_code,
)
from utils.icons import render_page_header
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Teal accent — the one the metric-card spine, styled H2s, and active nav item use.
_ACCENT = "#0d9488"


def _section(title: str, caption: str | None = None) -> None:
    """Consistent section header: a teal accent bar + title, with an optional caption.

    Replaces the old st.subheader + horizontal-rule pattern, which chopped the page
    into hard-lined bands. The accent bar and generous top margin give the sections
    rhythm without a divider line between every block.
    """
    caption_html = (
        f"<div style='color:#64748b; font-size:0.9rem; margin:4px 0 0 15px;'>{caption}</div>"
        if caption
        else ""
    )
    # Flat single-line HTML, empty parts dropped. Streamlit dedents the string before
    # markdown parses it, and a blank line closes a raw-HTML block — so `caption_html`
    # alone on its own source line collapsed to a blank line on every captionless
    # section, cutting the header's wrapper div out of the block. Only a closing tag
    # trailed it here, so nothing visible leaked; adding anything below the caption
    # would have escaped it onto the page. Same rule as the Diagnostics result cards.
    inner = "".join(p for p in [
        "<div style='display:flex; align-items:center; gap:11px;'>"
        f"<span style='width:4px; height:21px; background:{_ACCENT}; "
        "border-radius:2px; display:inline-block;'></span>"
        f"<span style='font-size:1.18rem; font-weight:700; color:#0f172a;'>{title}</span>"
        "</div>",
        caption_html,
    ] if p)
    st.markdown(
        f"<div style='margin:1.7rem 0 0.9rem 0;'>{inner}</div>",
        unsafe_allow_html=True,
    )


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
    """Aggregate real specimen counts into a DHIS2 DataValueSet, keyed (period, LGA, genus).

    Org unit and data element UIDs come from the operator's configured mappings; a name
    with no mapping is written as a visible UNMAPPED_ code, never omitted. The period type
    (Monthly by default) comes from DHIS2_PERIOD_TYPE.
    """
    if df.empty:
        return json.dumps({"dataValues": []}, indent=2)

    # Two things this deliberately does not do.
    #
    # It does not count rows. A row is not a specimen: a manual_field_log row is a whole
    # batch holding raw genus counts, and it resolves to no single genus, so grouping on
    # extract_primary_genus dropped every batch from the export — a batch of 500 with 100
    # vialed out reported 100 and lost the other 400. extract_genus_counts_from_screening
    # is the same helper the on-screen totals use, so export and dashboard agree, and it
    # nets out vialed_out so a batch and its children are never both counted.
    #
    # And it does not group by breeding_site_type. A DHIS2 org unit is a *place*; a habitat
    # category is not one, so that key produced identifiers ("SITE_RICE_FIELD…") no instance
    # could match. Habitat stays on every row for analysis here — it is simply not the
    # dimension DHIS2 aggregates by.
    # Keyed on the PERIOD, not the collection date. (dataElement, period, orgUnit) is the
    # identity of a DHIS2 data value, so under a monthly period type two collections in the
    # same month at the same LGA are one value — summed here. Keying on the date instead
    # would emit two values with identical identity, and the server keeps whichever arrives
    # last: the export would look complete and silently report one collection's catch.
    period_type = configured_period_type()
    totals: dict[tuple, int] = {}
    for _, row in df.iterrows():
        counts = extract_genus_counts_from_screening(row.get("field_screening_result"))
        if not counts:
            continue
        date = row.get("collection_date")
        period = (
            convert_date_to_dhis2_period(date, period_type) if pd.notna(date)
            else convert_date_to_dhis2_period(datetime.now(), period_type)
        )
        for genus, count in counts.items():
            key = (period, row.get("lga"), genus)
            totals[key] = totals.get(key, 0) + int(count)

    data_values = []
    for (period, lga, genus), count in sorted(totals.items(), key=lambda kv: str(kv[0])):
        # Real UIDs when the operator has mapped them, a visible UNMAPPED_ placeholder when
        # not. Never a silent omission: a row logged before the LGA column existed has no
        # place at all, and dropping it would quietly shrink the submitted totals.
        data_values.append({
            "dataElement": data_element_for_genus(genus) or unmapped_code("genus", genus),
            "period": period,
            "orgUnit": org_unit_for_lga(lga) or unmapped_code("lga", lga),
            "value": str(int(count)),
        })

    return json.dumps({"dataValues": data_values}, indent=2)


def _payload_value_count(payload: str) -> int:
    """How many dataValues the generated payload holds, for the confirmation line.

    The payload is a string in session_state, so this re-reads it. A payload we cannot
    parse reports 0 rather than raising — the count is a convenience, and it must never be
    the thing that breaks the dashboard.
    """
    try:
        return len(json.loads(payload).get("dataValues", []))
    except Exception:
        logger.debug("Could not count dataValues in the DHIS2 payload", exc_info=True)
        return 0


def _unmapped_names(payload: str) -> set[str]:
    """The org units and data elements in the payload that have no real DHIS2 UID.

    Read back out of the built payload rather than tracked alongside it, so the warning can
    never disagree with the file the operator downloads.
    """
    try:
        values = json.loads(payload).get("dataValues", [])
    except Exception:
        logger.debug("Could not scan the DHIS2 payload for unmapped codes", exc_info=True)
        return set()
    return {
        uid for value in values
        for uid in (value.get("orgUnit"), value.get("dataElement"))
        if is_unmapped(uid)
    }


def _render_dhis2_payload_preview() -> None:
    """Show the generated DHIS2 payload full-width, below the header.

    Collapsed by default: the payload is generated to be downloaded, so the JSON is there
    to be checked, not read top to bottom.
    """
    payload = st.session_state.get("dhis2_payload")
    if not payload:
        return

    count = _payload_value_count(payload)
    unmapped = _unmapped_names(payload)

    with st.expander(f"DHIS2 payload — {count} data value(s)", expanded=False):
        st.caption(
            f"Aggregated by **{configured_period_type().lower()}** period, LGA, and genus. "
            "Org units are LGAs, because a DHIS2 org unit is a place; breeding site type is "
            "recorded per row but is not the dimension DHIS2 aggregates by. The period type "
            "must match the target dataset's — set `DHIS2_PERIOD_TYPE` if yours differs."
        )
        if unmapped:
            st.warning(
                "No DHIS2 UID for: **" + "**, **".join(sorted(unmapped)) + "**. These "
                "appear as `UNMAPPED_…` in the payload rather than being dropped, so the "
                "totals stay complete — but DHIS2 will reject the set until they are "
                "mapped. Set `DHIS2_ORG_UNIT_MAP` and `DHIS2_DATA_ELEMENT_MAP` in secrets; "
                "`python scripts/fetch_dhis2_uids.py` prints the UIDs your instance uses."
            )
        st.code(payload, language="json", height=320, wrap_lines=True)
        if st.button("Clear payload", width="content"):
            st.session_state.pop("dhis2_payload", None)
            st.rerun()


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


def _render_collection_events(df: pd.DataFrame) -> None:
    """The ledger as collection events, with each vialed individual nested under its batch.

    A flat ledger lists a vialed mosquito as an unrelated new specimen ID, which hides the
    very relationship subsampling exists to record. Here each batch shows what was caught,
    how much of it has been vialed out, and what remains in the bulk sample — and the
    individuals sit underneath the catch they came from.
    """
    events, other_rows = build_collection_events(df)

    if not events:
        st.info("No batch collection events yet. Save a site log entry to create one.")
    for event in events:
        counts = event["genus_counts"]
        summary = " · ".join(
            f"{genus} {c['caught']}" for genus, c in counts.items() if c["caught"]
        ) or "no counts recorded"
        vialed_note = f" · {event['total_vialed']} vialed" if event["total_vialed"] else ""

        header = (
            f"{event['collection_date'] or 'undated'} — {event['breeding_site_type'] or 'site not recorded'}"
            f"  ·  {summary}{vialed_note}"
        )

        with st.expander(header):
            st.caption(
                f"Collected by {event['collector']} · batch `{event['specimen_id'][:8]}…`"
            )

            if counts:
                # caught = vialed + in_batch, always. Showing all three makes the
                # no-double-count invariant visible rather than merely true.
                breakdown = pd.DataFrame(
                    [
                        {
                            "Genus": genus,
                            "Caught": c["caught"],
                            "Vialed out": c["vialed"],
                            "Still in batch": c["in_batch"],
                        }
                        for genus, c in counts.items()
                    ]
                )
                st.dataframe(breakdown, width="stretch", hide_index=True)

            if event["field_notes"]:
                st.caption(f"Notes: {event['field_notes']}")

            children = event["children"]
            if not children:
                st.caption("No individuals vialed out of this batch yet.")
            else:
                st.markdown(f"**Vialed individuals ({len(children)})**")
                child_table = pd.DataFrame(
                    [
                        {
                            "Tube": c["tube_label"] or "—",
                            "Specimen ID (QR)": c["specimen_id"],
                            "Genus": c["genus"] or "—",
                            "Identified as": c["identified_as"] or "Pending identification",
                            "PCR": c["pcr_confirmed_species"] or (c["pcr_status"] or "not_submitted"),
                        }
                        for c in children
                    ]
                )
                st.dataframe(child_table, width="stretch", hide_index=True)

    # Identifications and captures that belong to no batch. Not dropped — a row that
    # silently disappears from every view is worse than one shown out of context.
    if other_rows is not None and not other_rows.empty:
        with st.expander(f"Records not part of a collection event ({len(other_rows)})"):
            st.caption(
                "Standalone identifications and multi-angle captures — saved without being "
                "vialed out of a batch field log."
            )
            standalone = add_collector_column(other_rows.drop(columns=["genus"], errors="ignore"))
            cols = [
                c
                for c in ["Collector", "specimen_id", "collection_date", "screening_method", "pcr_status"]
                if c in standalone.columns
            ]
            st.dataframe(standalone[cols] if cols else standalone, width="stretch", hide_index=True)


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
        with st.popover("⋮ More Actions", width="stretch"):
            st.markdown("**Data Export**")
            st.caption(
                "Org unit codes below are derived from breeding_site_type as a "
                "placeholder — map these to real DHIS2 facility codes before use."
            )
            st.markdown("---")
            if st.button("Generate DHIS2 Payload", type="primary", width="stretch"):
                st.session_state["dhis2_payload"] = _build_dhis2_payload(df)

            # Held in session_state rather than drawn inside the button block: clicking the
            # download button triggers a rerun on which that block is False, so the payload
            # and its own download button disappeared before the file could be saved.
            payload = st.session_state.get("dhis2_payload")
            if payload:
                st.success(f"{_payload_value_count(payload)} data value(s) ready — shown below.")
                st.download_button(
                    "Download payload JSON", data=payload,
                    file_name=f"dhis2_payload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json", width="stretch",
                )
            st.markdown("---")
            if not df.empty:
                st.download_button(
                    "Download raw specimen records (CSV)",
                    data=df.to_csv(index=False),
                    file_name=f"specimen_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv", width="stretch",
                )

    # Drawn out here, in the page body, rather than inside the popover above. The popover is
    # anchored to a 1/5-width column, so a JSON block rendered in it overflowed its own
    # container — the "code spill". Full page width plus wrap_lines keeps every line inside
    # the viewport on a phone, and the fixed height stops a large export from burying the
    # dashboard under a wall of JSON.
    _render_dhis2_payload_preview()

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

    # ── Map ───────────────────────────────────────────────────────────────
    _section(
        "Geospatial Collection Map",
        "Real collection sites from specimen_records. Click a marker for screening details and photos.",
    )

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

    # ── Genus distribution + collection timeline ─────────────────────────
    graph_col1, graph_col2 = st.columns(2)

    with graph_col1:
        _section("Genus Distribution")
        genus_counts = df["genus"].dropna().value_counts()
        if not genus_counts.empty:
            st.bar_chart(genus_counts)
        else:
            st.info("No specimens have a resolvable genus yet.")

    with graph_col2:
        _section("Collection Timeline")
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

    # ── Photo evidence feed ───────────────────────────────────────────────
    has_photos = df["photo_urls"].apply(lambda x: isinstance(x, list) and len(x) > 0)
    if has_photos.any():
        _section("Recent Photo Evidence")
        photo_df = df[has_photos].copy()
        if "collection_date" in photo_df.columns:
            photo_df = photo_df.sort_values(by="collection_date", ascending=False)

        photo_cols = st.columns(4)
        for i, (_, row) in enumerate(photo_df.head(4).iterrows()):
            with photo_cols[i % 4]:
                st.image(
                    row["photo_urls"][0],
                    caption=f"{row.get('breeding_site_type', 'Site')} ({row.get('collection_date', 'n/a')})",
                    width="stretch",
                )

    # ── Ledger ─────────────────────────────────────────────────────────────
    _section("Specimen Ledger")
    events_tab, records_tab = st.tabs(["Collection events", "All records"])

    with events_tab:
        _render_collection_events(df)

    with records_tab:
        st.caption(
            "Every row in specimen_records, including each vialed individual as its own "
            "record. This is the raw ledger the counts are computed from."
        )
        # Replace raw collector_id with the readable Collector, rather than showing both.
        # The raw column is a UUID (or the 'unattributed-legacy' sentinel) and identifies
        # nobody to a human reader; the resolved name is derived from it and says the same
        # thing in words. Move it to the front, where a reader looks for who did the work.
        ledger = add_collector_column(df.drop(columns=["genus"], errors="ignore"))
        ledger = ledger.drop(columns=["collector_id"], errors="ignore")
        ordered = ["Collector"] + [c for c in ledger.columns if c != "Collector"]
        st.dataframe(ledger[ordered], width="stretch")

    # ── Footer / subscribe (real persistence, no fake success) ───────────
    st.markdown("<br><hr style='border-top:1px solid #e2e8f0; opacity:0.5;'>", unsafe_allow_html=True)
    ft_info, ft_action = st.columns([2, 1])

    with ft_info:
        st.markdown(
            """
            <div style='color:#94A3B8; font-size:12.5px; line-height:1.5;'>
                <b>Vector Sentinel Engine</b><br>
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
            if st.button("Enroll", width="stretch", key="dash_sub_btn"):
                if not sub_email or "@" not in sub_email:
                    st.error("Please enter a valid email address.")
                elif _save_subscriber(sub_email):
                    st.success(f"Saved: {sub_email}")
                else:
                    st.error("Could not save your subscription — check database/storage connection.")
