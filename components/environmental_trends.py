# =========================================================================
# COLLECTION & COMPOSITION TRENDS (components/environmental_trends.py)
#
# Previously displayed NDVI canopy, water chemistry, and insecticide
# resistance charts sourced from columns that never existed on the real
# specimen_records schema (Base_Larval_Count, Zone_Name, Water_pH, etc.) —
# every chart silently showed "data missing" regardless of how much real
# data existed. Rebuilt around what specimen_records actually contains:
# breeding site composition, collection activity, and genus trends.
#
# Insecticide resistance tracking has no real data source yet — see the
# honest note in Tab 2 rather than a fabricated chart.
# =========================================================================
import pandas as pd
import streamlit as st

from utils.data_manager import extract_genus_counts_from_screening, load_specimen_records


def render_environmental_trends_page():
    st.markdown("### Collection Activity & Vector Composition Trends")
    st.markdown("---")

    df = load_specimen_records()

    if df.empty:
        st.warning("No specimen records yet. Log entries via Site Log Entry or Diagnostics to see trends here.")
        return

    df["collection_date"] = pd.to_datetime(df.get("collection_date"), errors="coerce")

    tab1, tab2 = st.tabs(["Site & Collection Trends", "Insecticide Resistance Profiling"])

    # ── TAB 1: real, derived entirely from specimen_records ──────────────
    with tab1:
        st.subheader("Breeding Site Composition")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("#### Records by Site Type")
            if "breeding_site_type" in df.columns:
                site_counts = df["breeding_site_type"].fillna("Unspecified").value_counts()
                if not site_counts.empty:
                    st.bar_chart(site_counts)
                else:
                    st.info("No breeding site types recorded yet.")
            else:
                st.info("breeding_site_type column not present in this dataset.")

        with col2:
            st.markdown("#### Collection Volume Over Time")
            valid_dates = df.dropna(subset=["collection_date"])
            if not valid_dates.empty:
                daily = valid_dates.groupby(valid_dates["collection_date"].dt.date).size()
                st.line_chart(daily)
            else:
                st.info("No valid collection dates recorded yet.")

        st.markdown("---")
        st.subheader("Vector Genus Composition")

        genus_rows = []
        for _, row in df.iterrows():
            counts = extract_genus_counts_from_screening(row.get("field_screening_result"))
            for genus, count in counts.items():
                genus_rows.append({
                    "collection_date": row.get("collection_date"),
                    "breeding_site_type": row.get("breeding_site_type") or "Unspecified",
                    "genus": genus,
                    "count": count,
                })

        if genus_rows:
            genus_df = pd.DataFrame(genus_rows)

            gcol1, gcol2 = st.columns(2)
            with gcol1:
                st.markdown("#### Total by Genus")
                totals = genus_df.groupby("genus")["count"].sum()
                st.bar_chart(totals)

            with gcol2:
                st.markdown("#### By Genus and Site Type")
                pivot = genus_df.pivot_table(
                    index="breeding_site_type", columns="genus", values="count", aggfunc="sum", fill_value=0
                )
                st.dataframe(pivot, use_container_width=True)
        else:
            st.info(
                "No genus data available yet. This populates once specimens are "
                "logged with counts (Site Log Entry) or identified (Diagnostics)."
            )

    # ── TAB 2: honest — no real data source exists yet ───────────────────
    with tab2:
        st.subheader("Bioassay Resistance Surveillance")
        st.info(
            "**Not yet available.** This app can generate WHO tube bioassay tube "
            "labels for insecticide susceptibility testing, but there is currently "
            "no table capturing actual bioassay mortality/knockdown results — so "
            "there is nothing real to chart here yet.\n\n"
            "To enable this tab, a `bioassay_results` table would need to be built "
            "(treatment, concentration, replicate, knockdown/mortality counts, "
            "exposure time) and a form to submit results after each assay run. "
            "Ask to have this built if resistance tracking is a priority."
        )
