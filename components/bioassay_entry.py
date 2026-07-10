"""
WHO Tube Bioassay Result Entry — submits one replicate's mortality/knockdown
result to bioassay_results. Pairs naturally with the tube labels generated
earlier (batch_reference matches the MMC-26-... prefix on physical tubes).
"""

from datetime import date

import streamlit as st

from utils.data_manager import (
    classify_resistance_status,
    clear_bioassay_results_cache,
    compute_mortality_percentage,
    load_bioassay_results,
    submit_bioassay_result,
)
from utils.icons import render_page_header

_TREATMENTS = [
    "PBO + Permethrin", "PBO + Alphacypermethrin", "PBO + Deltamethrin",
    "Permethrin", "Deltamethrin", "Alphacypermethrin", "Pirimiphos-methyl",
]


def render_bioassay_entry_page():
    render_page_header("Bioassay Result Entry", "lab")
    st.caption(
        "Submit one replicate's knockdown/mortality result. Use the batch "
        "reference matching your tube labels (e.g. MMC-26-DELT-0.05) to keep "
        "results traceable to physical specimens."
    )

    with st.form("bioassay_entry_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            assay_date = st.date_input("Assay date", value=date.today())
            treatment_name = st.selectbox("Treatment", _TREATMENTS)
            concentration_pct = st.number_input(
                "Concentration (%)", min_value=0.0, value=0.05, format="%.3f"
            )
            replicate_number = st.selectbox("Replicate", [1, 2, 3, 4])
            is_control = st.checkbox("This is a control replicate")

        with col2:
            mosquitoes_exposed = st.number_input("Mosquitoes exposed", min_value=1, value=20, step=1)
            exposure_time_minutes = st.number_input("Exposure time (minutes)", min_value=0.0, value=60.0)
            knockdown_60min = st.number_input(
                "Knockdown at 60 min (optional, -1 if not recorded)", min_value=-1, value=-1, step=1
            )
            mortality_24hr = st.number_input("Mortality at 24hr", min_value=0, value=0, step=1)

        species_tested = st.text_input(
            "Species tested", placeholder="e.g. Anopheles gambiae s.l."
        )
        batch_reference = st.text_input(
            "Batch reference", placeholder="e.g. MMC-26-DELT-0.05"
        )
        notes = st.text_area("Notes", placeholder="Any anomalies, weather, colony source, etc.")

        submitted = st.form_submit_button("Save Bioassay Result", type="primary", use_container_width=True)

        if submitted:
            if mortality_24hr > mosquitoes_exposed:
                st.error("Mortality cannot exceed the number of mosquitoes exposed.")
            elif knockdown_60min != -1 and knockdown_60min > mosquitoes_exposed:
                st.error("Knockdown cannot exceed the number of mosquitoes exposed.")
            else:
                saved = submit_bioassay_result(
                    assay_date=assay_date,
                    treatment_name=treatment_name,
                    concentration_pct=concentration_pct,
                    replicate_number=replicate_number,
                    is_control=is_control,
                    mosquitoes_exposed=mosquitoes_exposed,
                    mortality_24hr=mortality_24hr,
                    exposure_time_minutes=exposure_time_minutes,
                    knockdown_60min=None if knockdown_60min == -1 else knockdown_60min,
                    species_tested=species_tested,
                    batch_reference=batch_reference,
                    notes=notes,
                )
                if saved:
                    clear_bioassay_results_cache()
                    mortality_pct = compute_mortality_percentage(mortality_24hr, mosquitoes_exposed)
                    status = classify_resistance_status(mortality_pct)
                    st.success(f"Saved. Raw mortality: {mortality_pct}% — {status}")
                    if not is_control:
                        st.caption(
                            "Note: this is raw mortality, not Abbott's-corrected. "
                            "Check the matching control replicate's mortality before "
                            "drawing conclusions — see the Insecticide Resistance tab."
                        )
                else:
                    st.error("Result was not saved — check the database connection.")

    st.markdown("---")
    _render_recent_results()


def _render_recent_results():
    st.subheader("Recent Bioassay Submissions")
    df = load_bioassay_results()
    if df.empty:
        st.info("No bioassay results submitted yet.")
        return

    df = df.sort_values("created_at", ascending=False)
    display_cols = [
        "assay_date", "treatment_name", "concentration_pct", "replicate_number",
        "is_control", "mosquitoes_exposed", "mortality_24hr", "batch_reference",
    ]
    display_cols = [c for c in display_cols if c in df.columns]
    st.dataframe(df[display_cols].head(15), use_container_width=True, hide_index=True)
