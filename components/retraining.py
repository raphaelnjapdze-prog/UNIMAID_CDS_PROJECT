import json
from pathlib import Path

import streamlit as st

from utils.icons import render_page_header
from utils.pcr_and_accuracy import get_supabase_client


def _load_retraining_workflow():
    """
    Import the torch-backed retraining entry point lazily.

    Returns (workflow_callable, None) on success, or (None, error) if the
    training dependency is missing OR fails to load — e.g. a torch DLL that
    won't initialize on this machine raises OSError, not ModuleNotFoundError.
    Kept out of module import (and deliberately broad in what it catches) so a
    missing or broken torch never crashes app startup; only this page is
    affected.
    """
    try:
        from models.local_retraining_pipeline import run_continuous_learning_workflow
        return run_continuous_learning_workflow, None
    except Exception as exc:  # ImportError, OSError (DLL init), RuntimeError, ...
        return None, exc


def render_retraining_page():
    render_page_header("Local Retraining", "retraining")
    st.caption("Batch confirmed specimens into a retraining run, compare with the current model, and review the latest audit trail.")

    run_continuous_learning_workflow, import_error = _load_retraining_workflow()
    if import_error is not None:
        st.warning(
            "The retraining backend is currently unavailable because the training dependency could not be loaded. "
            f"Details: {import_error}"
        )
        st.info("Install or repair the training dependencies (see requirements-ml.txt, e.g. torch) before using this page.")
        return

    client = get_supabase_client()
    if client is None:
        st.warning("Supabase is not configured. Set your Supabase secrets to enable retraining from confirmed specimens.")
        return

    st.info("The workflow retrains only when there is a meaningful batch of confirmed records, avoiding noisy single-sample retrains.")

    col1, col2 = st.columns([1, 1])
    with col1:
        genus = st.selectbox("Genus", ["Anopheles", "Culex", "Aedes"], index=0)
    with col2:
        output_root = st.text_input("Output root", value="data/continuous_learning")

    log_path = Path(output_root) / "retraining_audit.jsonl"
    if st.button("Run retraining workflow"):
        with st.spinner("Querying confirmed specimens and running retraining workflow..."):
            result = run_continuous_learning_workflow(
                client=client,
                genus=genus,
                output_root=output_root,
                current_checkpoint_path=None,
                log_path=str(log_path),
            )
        st.write(result)

    if log_path.exists():
        st.subheader("Latest retraining report")
        with log_path.open("r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        if lines:
            latest = lines[-1]
            st.json(latest)
        else:
            st.info("No retraining events logged yet.")
    else:
        st.info("No retraining log exists yet. Run the workflow once to create one.")
