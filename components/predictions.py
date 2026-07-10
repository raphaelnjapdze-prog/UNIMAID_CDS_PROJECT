# =========================================================================
# RESISTANCE STATUS PREDICTION (components/predictions.py)
#
# Predicts WHO susceptibility classification from real bioassay_results
# data only. Shows real training sample counts and real test accuracy
# alongside every prediction — never a confident-looking number without
# its supporting evidence visible.
# =========================================================================
from datetime import date

import streamlit as st

from utils.icons import render_page_header
from utils.resistance_ml_engine import (
    check_training_readiness,
    get_last_training_metrics,
    predict_resistance_status,
    train_resistance_model,
)

_TREATMENTS = [
    "PBO + Permethrin", "PBO + Alphacypermethrin", "PBO + Deltamethrin",
    "Permethrin", "Deltamethrin", "Alphacypermethrin", "Pirimiphos-methyl",
]


def render_predictions_page():
    render_page_header(
        title="Resistance Status Prediction",
        icon_name="risk",
        caption="Predicts WHO susceptibility classification from real, logged bioassay results only.",
    )
    st.markdown("---")

    readiness = check_training_readiness()

    st.subheader("Model Data Status")
    c1, c2 = st.columns(2)
    c1.metric("Real bioassay replicates on file", readiness["real_samples"])
    c2.metric("Required to train", readiness["required_samples"])

    if not readiness["ready"]:
        st.warning(
            f"Only {readiness['real_samples']} real, non-control replicate(s) logged — "
            f"need at least {readiness['required_samples']} before a model can be trained. "
            "Log more results via Bioassay Result Entry."
        )
        return

    if readiness["class_distribution"]:
        st.caption("Current class distribution (real data): " + ", ".join(
            f"{k}: {v}" for k, v in readiness["class_distribution"].items()
        ))

    st.markdown("---")
    st.subheader("Train / Retrain Model")

    last_metrics = get_last_training_metrics()
    if last_metrics:
        st.caption(
            f"Last trained on {last_metrics['trained_on_real_samples']} real sample(s), "
            f"test accuracy {last_metrics['accuracy']*100:.1f}%, "
            f"at {last_metrics['training_timestamp']}."
        )
    else:
        st.caption("No model trained yet.")

    if st.button("Train Model on Current Real Data", type="primary"):
        with st.spinner("Training on real bioassay data..."):
            result = train_resistance_model()
        if result["trained"]:
            st.success(
                f"Trained on {result['metrics']['trained_on_real_samples']} real sample(s) — "
                f"test accuracy {result['metrics']['accuracy']*100:.1f}%."
            )
        else:
            st.error(result["reason"])

    st.markdown("---")
    st.subheader("Predict Resistance Status")
    st.caption(
        "Enter conditions for a planned or upcoming bioassay to see the model's "
        "prediction, based entirely on real data logged so far."
    )

    col1, col2 = st.columns(2)
    with col1:
        treatment_name = st.selectbox("Treatment", _TREATMENTS)
        concentration_pct = st.number_input("Concentration (%)", min_value=0.0, value=0.05, format="%.3f")
    with col2:
        species_tested = st.text_input("Species tested", placeholder="e.g. Anopheles gambiae s.l.")
        assay_month = st.selectbox("Month", list(range(1, 13)), index=date.today().month - 1)

    if st.button("Predict"):
        result = predict_resistance_status(treatment_name, concentration_pct, species_tested, assay_month)
        if not result["available"]:
            st.warning(result["reason"])
        else:
            status = result["predicted_status"]
            color = {"Susceptible": "success", "Resistant": "error"}.get(status, "warning")
            getattr(st, color)(f"Predicted status: **{status}**")

            st.markdown("**Class probabilities:**")
            for cls, prob in sorted(result["class_probabilities"].items(), key=lambda x: -x[1]):
                st.write(f"- {cls}: {prob*100:.1f}%")

            st.caption(
                f"Model trained on {result['model_trained_on_samples']} real sample(s), "
                f"test-set accuracy {result['model_test_accuracy']*100:.1f}% — "
                "treat this as a data-driven hint, not a certainty, especially with a "
                "modest sample size."
            )
