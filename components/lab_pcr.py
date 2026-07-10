import streamlit as st

from utils.icons import render_page_header
from utils.pcr_and_accuracy import render_accuracy_dashboard, render_pcr_confirmation_form


def render_lab_pcr_page():
    render_page_header("PCR Lab Confirmation", "lab")
    st.caption("Link each physical specimen to its database record and submit PCR confirmation results.")
    render_pcr_confirmation_form()
    st.markdown("---")
    render_accuracy_dashboard()
