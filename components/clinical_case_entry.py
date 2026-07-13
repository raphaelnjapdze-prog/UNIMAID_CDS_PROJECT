"""
Clinical Case Data Entry — logs confirmed malaria case counts per facility
per reporting period. Feeds the real larval-density-vs-case-count
correlation in utils/epidemiology_engine.py. No fabricated case counts
anywhere in this pipeline — if this table is empty, correlation is
unavailable, and the Epidemiology page must say so honestly.
"""

from datetime import date

import streamlit as st

from utils.data_manager import (
    clear_clinical_case_data_cache,
    load_clinical_case_data,
    submit_clinical_case_record,
)
from utils.icons import render_page_header

_DIAGNOSTIC_METHODS = ["RDT", "Microscopy", "RDT + Microscopy", "Clinical diagnosis only"]
_AGE_GROUPS = ["All ages", "Under 5", "5 and older", "Pregnant women"]


def render_clinical_case_entry_page():
    render_page_header("Clinical Case Data Entry", "correlation")
    st.caption(
        "Log confirmed malaria case counts from clinic/facility records. This "
        "is the real data source behind larval density vs. case correlation — "
        "no figures here are estimated or simulated."
    )

    with st.form("clinical_case_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            report_date = st.date_input("Reporting period start date", value=date.today())
            facility_name = st.text_input("Facility name", placeholder="e.g. Mairi Basin Sentinel Clinic")
            lga_district = st.text_input("LGA / District (optional)")

        with col2:
            confirmed_cases = st.number_input("Confirmed malaria cases", min_value=0, value=0, step=1)
            suspected_cases = st.number_input(
                "Suspected cases tested (optional, -1 if unknown)", min_value=-1, value=-1, step=1
            )
            diagnostic_method = st.selectbox("Diagnostic method", _DIAGNOSTIC_METHODS)
            patient_age_group = st.selectbox("Patient age group", _AGE_GROUPS)

        notes = st.text_area("Notes", placeholder="Data source, reporting gaps, anomalies, etc.")

        submitted = st.form_submit_button("Save Case Record", type="primary", width="stretch")

        if submitted:
            if not facility_name.strip():
                st.error("Facility name is required.")
            else:
                saved = submit_clinical_case_record(
                    report_date=report_date,
                    facility_name=facility_name.strip(),
                    confirmed_cases=confirmed_cases,
                    lga_district=lga_district.strip(),
                    suspected_cases=None if suspected_cases == -1 else suspected_cases,
                    diagnostic_method=diagnostic_method,
                    patient_age_group=patient_age_group,
                    notes=notes,
                )
                if saved:
                    clear_clinical_case_data_cache()
                    st.success(f"Saved: {confirmed_cases} confirmed cases at {facility_name} for {report_date}.")
                else:
                    st.error("Record was not saved — check the database connection.")

    st.markdown("---")
    _render_recent_records()


def _render_recent_records():
    st.subheader("Recent Case Records")
    df = load_clinical_case_data()
    if df.empty:
        st.info("No clinical case records submitted yet.")
        return

    df = df.sort_values("created_at", ascending=False)
    display_cols = [c for c in [
        "report_date", "facility_name", "lga_district",
        "confirmed_cases", "suspected_cases", "diagnostic_method",
    ] if c in df.columns]
    st.dataframe(df[display_cols].head(15), width="stretch", hide_index=True)
