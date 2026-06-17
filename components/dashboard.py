# =========================================================================
# ENTOMOLOGICAL ANALYTICS & HOTSPOT VISUALIZATION (components/dashboard.py)
# =========================================================================
import streamlit as st
import pandas as pd
from utils.data_manager import _load_master_df, _render_dashboard_header_metrics

def render_dashboard_page():
    """Renders the primary analytical surveillance dashboard view."""
    st.markdown("## 📊 Vector Surveillance Analytics Dashboard")
    st.markdown("---")
    
    # Retrieve localized dataframe context based on identity constraints
    df = _load_master_df()
    
    if df.empty:
        st.warning("No entomological surveillance records found. Please ingest field survey logs to populate metrics.")
        return
        
    # Render the unified KPI indicators across the dashboard ceiling
    _render_dashboard_header_metrics(df)
    st.markdown("---")
    
    # Dual-column visualization matrices
    graph_col1, graph_col2 = st.columns(2)
    
    with graph_col1:
        st.subheader("Species Abundance Composition")
        
        # Aggregate absolute vector yields dynamically
        anopheles_tot = float(df["Anopheles_Count"].sum()) if "Anopheles_Count" in df.columns else 0.0
        culex_tot = float(df["Culex_Count"].sum()) if "Culex_Count" in df.columns else 0.0
        aedes_tot = float(df["Aedes_Count"].sum()) if "Aedes_Count" in df.columns else 0.0
        
        species_matrix = pd.DataFrame({
            "Vector Genus": ["Anopheles", "Culex", "Aedes"],
            "Collected Population": [anopheles_tot, culex_tot, aedes_tot]
        })
        
        st.bar_chart(
            data=species_matrix,
            x="Vector Genus",
            y="Collected Population",
            color="Vector Genus",
            use_container_width=True
        )
        
    with graph_col2:
        st.subheader("Thermal Influence on Breeding Dynamics")
        
        required_scatter_keys = ["Temperature_C", "Base_Larval_Count"]
        if all(key in df.columns for key in required_scatter_keys):
            scatter_df = df.dropna(subset=required_scatter_keys)
            st.scatter_chart(
                data=scatter_df,
                x="Temperature_C",
                y="Base_Larval_Count",
                color="Zone_Name" if "Zone_Name" in df.columns else None,
                use_container_width=True
            )
        else:
            st.info("Thermal profiles or larval dipping aggregates are missing from this dataset schema baseline.")
            
    st.markdown("---")
    
    # Geospatial Surveillance Hotspot Node Matrix
    st.subheader("Geospatial Hotspot Risk Projection Map")
    st.write("Real-time geographic distribution of active aquatic breeding focus vectors across inspected coordinates.")
    
    required_geo_keys = ["Latitude", "Longitude"]
    if all(key in df.columns for key in required_geo_keys):
        map_data = df.dropna(subset=required_geo_keys).copy()
        
        if not map_data.empty:
            # Format explicitly for Streamlit map configurations
            map_data["latitude"] = pd.to_numeric(map_data["Latitude"])
            map_data["longitude"] = pd.to_numeric(map_data["Longitude"])
            
            st.map(map_data, size="Base_Larval_Count" if "Base_Larval_Count" in map_data.columns else None, use_container_width=True)
        else:
            st.info("Geospatial mapping arrays are currently empty or coordinate properties contain null values.")
    else:
        st.info("Coordinate attributes (Latitude/Longitude) are absent from the structural configuration layer.")

    st.markdown("---")
    
    # Tabular Database Inspect Grid
    with st.expander("🔍 View Complete Active Ledger Records"):
        st.dataframe(df, use_container_width=True)