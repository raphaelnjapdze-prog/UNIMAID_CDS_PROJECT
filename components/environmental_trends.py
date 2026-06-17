# =========================================================================
# GLOBAL CHANGE ECO-FACTORS & RESISTANCE MONITORING (components/environmental_trends.py)
# =========================================================================
import streamlit as st
import pandas as pd
from utils.data_manager import _load_master_df

def render_environmental_trends_page():
    """Renders visual analytics for environmental change factors and bioassay resistance tracking."""
    st.markdown("## 🌍 Global Change Factors & Resistance Telemetry")
    st.markdown("---")

    df = _load_master_df()

    if df.empty:
        st.warning("Primary database layers are currently empty. Ingest field survey data to view ecological trends.")
        return

    tab1, tab2 = st.tabs(["Physicochemical & Canopy Dynamics", "Insecticide Resistance Profiling"])

    with tab1:
        st.subheader("Ecological Microclimate Tracking")
        st.write("Monitoring aquatic breeding site properties influenced by changing environmental and canopy frameworks.")

        eco_col1, eco_col2 = st.columns(2)

        with eco_col1:
            st.markdown("#### NDVI Canopy Density vs. Larval Yields")
            if "NDVI_Canopy" in df.columns and "Base_Larval_Count" in df.columns:
                # Remove NaN rows to prevent chart rendering failures
                ndvi_df = df.dropna(subset=["NDVI_Canopy", "Base_Larval_Count"])
                st.scatter_chart(
                    data=ndvi_df,
                    x="NDVI_Canopy",
                    y="Base_Larval_Count",
                    color="Zone_Name" if "Zone_Name" in df.columns else None,
                    use_container_width=True
                )
            else:
                st.info("NDVI telemetry indicators are absent from the current data layer.")

        with eco_col2:
            st.markdown("#### Water Quality Matrix (Mean Values)")
            # Compute averages for baseline physicochemical indicators
            metrics_list = ["Water_pH", "Salinity_ppt", "Dissolved_Oxygen_mgL", "Humidity_Pct"]
            available_metrics = [m for m in metrics_list if m in df.columns]

            if available_metrics:
                mean_values = df[available_metrics].mean().reset_index()
                mean_values.columns = ["Environmental Parameter", "Calculated Mean"]
                st.dataframe(mean_values, use_container_width=True, hide_index=True)
            else:
                st.info("Physicochemical parameters (pH, Salinity, DO) are unpopulated.")

    with tab2:
        st.subheader("Bioassay Resistance Surveillance")
        st.write("Distribution of metabolic or target-site resistance patterns captured during localized WHO bioassay exposures.")

        res_col1, res_col2 = st.columns(2)

        with res_col1:
            st.markdown("#### Pyrethroid Resistance Signal Breakdown")
            if "PyResistance_Detected" in df.columns:
                py_counts = df["PyResistance_Detected"].value_counts().reset_index()
                py_counts.columns = ["Resistance Identified", "Observed Node Count"]
                st.bar_chart(data=py_counts, x="Resistance Identified", y="Observed Node Count", use_container_width=True)
            else:
                st.info("Pyrethroid bioassay data blocks are missing.")

        with res_col2:
            st.markdown("#### Organophosphate Resistance Signal Breakdown")
            if "OpResistance_Detected" in df.columns:
                op_counts = df["OpResistance_Detected"].value_counts().reset_index()
                op_counts.columns = ["Resistance Identified", "Observed Node Count"]
                st.bar_chart(data=op_counts, x="Resistance Identified", y="Observed Node Count", use_container_width=True)
            else:
                st.info("Organophosphate susceptibility indices are missing.")