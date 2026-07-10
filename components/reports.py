# =========================================================================
# AUTOMATED SURVEILLANCE & BIOASSAY REPORTING (components/reports.py)
#
# Previously crashed on load (KeyError on LGA_District, Collection_Date,
# etc. — none of which exist on specimen_records) and had a duplicate
# render_reports_page() definition that silently discarded the header
# call. Rebuilt entirely around the real schema: specimen_records for
# surveillance exports, bioassay_results for resistance exports.
# =========================================================================
import datetime
import io

import pandas as pd
import streamlit as st

from utils.data_manager import (
    classify_resistance_status,
    compute_mortality_percentage,
    extract_genus_counts_from_screening,
    load_bioassay_results,
    load_specimen_records,
)
from utils.icons import render_page_header


# =========================================================================
# Helpers — specimen surveillance side
# =========================================================================
def _flatten_specimen_df(df: pd.DataFrame) -> pd.DataFrame:
    """Adds readable genus count and identification-summary columns derived
    from field_screening_result, without mutating the caller's copy."""
    out = df.copy()
    out["collection_date"] = pd.to_datetime(out.get("collection_date"), errors="coerce")

    genus_totals = {"Anopheles": [], "Culex": [], "Aedes": [], "Other": []}
    methods = []
    for _, row in out.iterrows():
        counts = extract_genus_counts_from_screening(row.get("field_screening_result"))
        for g in genus_totals:
            genus_totals[g].append(counts.get(g, 0))
        result = row.get("field_screening_result")
        methods.append(result.get("screening_method") if isinstance(result, dict) else None)

    for g, values in genus_totals.items():
        out[g] = values
    out["screening_method"] = methods
    return out


def _first_photo_url(photo_urls) -> str | None:
    if isinstance(photo_urls, list) and len(photo_urls) > 0:
        return photo_urls[0]
    return None


def _compile_specimen_excel(df: pd.DataFrame) -> io.BytesIO:
    buffer = io.BytesIO()

    total_records = len(df)
    genus_cols = [c for c in ["Anopheles", "Culex", "Aedes", "Other"] if c in df.columns]
    genus_totals = df[genus_cols].sum() if genus_cols else pd.Series(dtype=float)
    pcr_counts = df["pcr_status"].value_counts() if "pcr_status" in df.columns else pd.Series(dtype=int)

    summary_rows = [("Total Specimens Logged", total_records)]
    for g in genus_cols:
        summary_rows.append((f"Total {g} Count", int(genus_totals.get(g, 0))))
    for status, count in pcr_counts.items():
        summary_rows.append((f"PCR Status: {status}", int(count)))

    summary_df = pd.DataFrame(summary_rows, columns=["Metric", "Value"])

    site_breakdown = pd.DataFrame()
    if "breeding_site_type" in df.columns and genus_cols:
        site_breakdown = df.groupby(df["breeding_site_type"].fillna("Unspecified"))[genus_cols].sum().reset_index()
        site_breakdown.columns = ["Breeding Site Type"] + genus_cols

    raw_export = df.drop(columns=["field_screening_result"], errors="ignore").copy()
    if "photo_urls" in raw_export.columns:
        raw_export["photo_urls"] = raw_export["photo_urls"].apply(
            lambda x: ", ".join(x) if isinstance(x, list) else ""
        )

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Executive_Summary", index=False)
        if not site_breakdown.empty:
            site_breakdown.to_excel(writer, sheet_name="Site_Type_Breakdown", index=False)
        raw_export.to_excel(writer, sheet_name="Raw_Records", index=False)

        workbook = writer.book
        for sheet_name in workbook.sheetnames:
            ws = workbook[sheet_name]
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for col in ws.columns:
                max_len = max((len(str(c.value or "")) for c in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = max(max_len + 3, 12)

    buffer.seek(0)
    return buffer


# =========================================================================
# Helpers — bioassay / resistance side
# =========================================================================
def _flatten_bioassay_df(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["mortality_pct"] = out.apply(
        lambda r: compute_mortality_percentage(r.get("mortality_24hr", 0), r.get("mosquitoes_exposed", 0)),
        axis=1,
    )
    out["resistance_status"] = out["mortality_pct"].apply(classify_resistance_status)
    return out


def _compile_bioassay_excel(df: pd.DataFrame) -> io.BytesIO:
    buffer = io.BytesIO()

    summary = df.groupby(["treatment_name", "concentration_pct", "is_control"]).agg(
        total_exposed=("mosquitoes_exposed", "sum"),
        total_mortality=("mortality_24hr", "sum"),
        replicates=("replicate_number", "nunique"),
    ).reset_index()
    summary["mortality_pct"] = summary.apply(
        lambda r: compute_mortality_percentage(r["total_mortality"], r["total_exposed"]), axis=1
    )
    summary["resistance_status"] = summary["mortality_pct"].apply(classify_resistance_status)

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="Treatment_Summary", index=False)
        df.to_excel(writer, sheet_name="Raw_Replicates", index=False)

        workbook = writer.book
        for sheet_name in workbook.sheetnames:
            ws = workbook[sheet_name]
            for cell in ws[1]:
                cell.font = cell.font.copy(bold=True)
            for col in ws.columns:
                max_len = max((len(str(c.value or "")) for c in col), default=10)
                ws.column_dimensions[col[0].column_letter].width = max(max_len + 3, 12)

    buffer.seek(0)
    return buffer


# =========================================================================
# Page
# =========================================================================
def render_reports_page():
    render_page_header(
        title="Automated Reports",
        icon_name="reports",
        caption="Filter, review, and export specimen surveillance and bioassay resistance data.",
    )
    st.markdown("---")

    tab1, tab2 = st.tabs(["Specimen Surveillance Report", "Bioassay Resistance Report"])

    # ── TAB 1: specimen_records ──────────────────────────────────────────
    with tab1:
        raw_df = load_specimen_records()
        if raw_df.empty:
            st.warning("No specimen records yet. Log entries via Site Log Entry or Diagnostics first.")
        else:
            df = _flatten_specimen_df(raw_df)
            valid_dates = df.dropna(subset=["collection_date"])

            st.subheader("Filters")
            fcol1, fcol2, fcol3 = st.columns(3)

            with fcol1:
                if not valid_dates.empty:
                    min_date, max_date = valid_dates["collection_date"].min().date(), valid_dates["collection_date"].max().date()
                    if min_date == max_date:
                        start_date, end_date = min_date, max_date
                        st.info(f"Single date in dataset: {min_date}")
                    else:
                        start_date, end_date = st.date_input(
                            "Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date
                        )
                else:
                    start_date, end_date = None, None
                    st.info("No valid collection dates in this dataset.")

            with fcol2:
                site_options = sorted(df["breeding_site_type"].dropna().unique()) if "breeding_site_type" in df.columns else []
                selected_sites = st.multiselect("Breeding site type (all if empty)", site_options)

            with fcol3:
                pcr_options = sorted(df["pcr_status"].dropna().unique()) if "pcr_status" in df.columns else []
                selected_pcr = st.multiselect("PCR status (all if empty)", pcr_options)

            processed = df.copy()
            if start_date and end_date and "collection_date" in processed.columns:
                mask = processed["collection_date"].dt.date.between(start_date, end_date) | processed["collection_date"].isna()
                processed = processed[mask]
            if selected_sites:
                processed = processed[processed["breeding_site_type"].isin(selected_sites)]
            if selected_pcr:
                processed = processed[processed["pcr_status"].isin(selected_pcr)]

            st.markdown("---")
            st.subheader("Query Results")

            if processed.empty:
                st.error("No records match the current filters.")
            else:
                st.markdown(f"**{len(processed)}** record(s) matched.")

                kpi1, kpi2, kpi3, kpi4 = st.columns(4)
                kpi1.metric("Anopheles", int(processed.get("Anopheles", pd.Series(dtype=int)).sum()))
                kpi2.metric("Culex", int(processed.get("Culex", pd.Series(dtype=int)).sum()))
                kpi3.metric("Aedes", int(processed.get("Aedes", pd.Series(dtype=int)).sum()))
                kpi4.metric(
                    "PCR Confirmed",
                    int((processed["pcr_status"] == "confirmed").sum()) if "pcr_status" in processed.columns else 0,
                )

                display_cols = [c for c in [
                    "collection_date", "breeding_site_type", "screening_method",
                    "Anopheles", "Culex", "Aedes", "Other", "pcr_status", "pcr_confirmed_species",
                ] if c in processed.columns]
                st.dataframe(processed[display_cols].head(20), use_container_width=True)
                if len(processed) > 20:
                    st.caption(f"Showing 20 of {len(processed)} — full set included in exports below.")

                st.markdown("---")
                st.subheader("Photo Evidence")
                show_photos_only = st.checkbox("Show only entries with a photo", value=False)

                photo_col = processed["photo_urls"].apply(_first_photo_url) if "photo_urls" in processed.columns else None
                evidence_df = processed.copy()
                if photo_col is not None:
                    evidence_df["_first_photo"] = photo_col
                    if show_photos_only:
                        evidence_df = evidence_df[evidence_df["_first_photo"].notna()]
                else:
                    evidence_df["_first_photo"] = None

                if evidence_df.empty:
                    st.info("No entries with photos in the current filter.")
                else:
                    for _, row in evidence_df.head(10).iterrows():
                        col_text, col_img = st.columns([2, 1])
                        with col_text:
                            st.markdown(f"**Specimen:** `{row.get('specimen_id', 'n/a')}`")
                            st.write(f"Date: {row.get('collection_date', 'N/A')}")
                            st.write(f"Site: {row.get('breeding_site_type', 'Not recorded')}")
                            st.write(f"GPS: `{row.get('gps_lat', 'N/A')}, {row.get('gps_lon', 'N/A')}`")
                            st.write(f"Genus counts — An: {row.get('Anopheles',0)} Cx: {row.get('Culex',0)} Ae: {row.get('Aedes',0)}")
                            st.write(f"PCR status: {row.get('pcr_status', 'not_submitted')}")
                        with col_img:
                            if row.get("_first_photo"):
                                st.image(row["_first_photo"], use_container_width=True)
                            else:
                                st.caption("No photo for this entry.")
                        st.markdown("<hr style='border-style:dashed; opacity:0.4;'>", unsafe_allow_html=True)

                st.markdown("---")
                st.subheader("Export")
                ex1, ex2 = st.columns(2)
                timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")

                with ex1:
                    excel_buf = _compile_specimen_excel(processed)
                    st.download_button(
                        "Download Excel (.xlsx)", data=excel_buf,
                        file_name=f"specimen_report_{timestamp_str}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        type="primary", use_container_width=True,
                    )
                with ex2:
                    csv_export = processed.drop(columns=["field_screening_result"], errors="ignore")
                    st.download_button(
                        "Download CSV", data=csv_export.to_csv(index=False),
                        file_name=f"specimen_report_{timestamp_str}.csv",
                        mime="text/csv", use_container_width=True,
                    )

    # ── TAB 2: bioassay_results ───────────────────────────────────────────
    with tab2:
        bio_df = load_bioassay_results()
        if bio_df.empty:
            st.info("No bioassay results submitted yet. Use Bioassay Result Entry to log results.")
        else:
            flat = _flatten_bioassay_df(bio_df)

            st.subheader("Treatment Summary")
            summary = flat.groupby(["treatment_name", "concentration_pct", "is_control"]).agg(
                total_exposed=("mosquitoes_exposed", "sum"),
                total_mortality=("mortality_24hr", "sum"),
                replicates=("replicate_number", "nunique"),
            ).reset_index()
            summary["mortality_pct"] = summary.apply(
                lambda r: compute_mortality_percentage(r["total_mortality"], r["total_exposed"]), axis=1
            )
            summary["resistance_status"] = summary["mortality_pct"].apply(classify_resistance_status)

            st.dataframe(
                summary.rename(columns={
                    "treatment_name": "Treatment", "concentration_pct": "Concentration (%)",
                    "is_control": "Control", "total_exposed": "Total Exposed",
                    "total_mortality": "Total Mortality", "replicates": "Replicates",
                    "mortality_pct": "Mortality (%)", "resistance_status": "Status",
                }),
                use_container_width=True, hide_index=True,
            )
            st.caption(
                "Mortality shown is raw, not Abbott's-corrected. Where control mortality "
                "exceeds 5%, results should be corrected against the matching control "
                "before drawing resistance conclusions (WHO 2016 guidelines)."
            )

            st.markdown("---")
            st.subheader("Export")
            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M")
            bio_excel = _compile_bioassay_excel(flat)
            st.download_button(
                "Download Bioassay Report (.xlsx)", data=bio_excel,
                file_name=f"bioassay_report_{timestamp_str}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                type="primary", use_container_width=True,
            )
