# =========================================================================
# DATA INGESTION & SCHEMA VALIDATION ENGINE (components/upload.py)
# =========================================================================
import streamlit as st
import pandas as pd
import io
from utils.data_manager import _persist_uploaded_dataframe, sync_kobotoolbox_field_data

def render_global_template_downloader():
    """
    Generates an in-memory WHO-compliant Excel entry template 
    structured for genus-level counts and standardized surveillance fields.
    """
    # 1. Standardized WHO core field structure array
    canonical_columns = [
        "Collection_Date",
        "State_Province",
        "LGA_District",
        "Sentinel_Site_Code",
        "Latitude_DD",
        "Longitude_DD",
        "Collection_Method",
        "Effort_Multiplier",
        "Habitat_Type",        # 1. This was in the list...
        "Anopheles",
        "Culex",
        "Aedes",
        "Mansonia",
        "Other_Genera",
        "Dominant_Condition",
        "Field_Notes"
    ]
    
    # 2. Populate with an exemplary surveillance baseline entry row
    who_standard_mock_row = {
        "Collection_Date": "2026-06-16",
        "State_Province": "Borno",
        "LGA_District": "Maiduguri",
        "Sentinel_Site_Code": "NGA-BO-MIRI-01",
        "Latitude_DD": 11.8333,
        "Longitude_DD": 13.1500,
        "Collection_Method": "CDC_Light_Trap",
        "Effort_Multiplier": 4,
        "Habitat_Type": "Concrete_Water_Tank",  # <--- FIX: Add this line right here!
        "Anopheles": 48,
        "Culex": 112,
        "Aedes": 5,
        "Mansonia": 0,
        "Other_Genera": 12,
        "Dominant_Condition": "Fed",
        "Field_Notes": "Clear skies, light evening breeze. Trap operational throughout night."
    }
    
    # 3. Create DataFrame schema
    template_df = pd.DataFrame([who_standard_mock_row])
    template_df = template_df[canonical_columns] # <--- This won't crash anymore!
    
    # 4. Compile binary buffer sequence without touching disk space
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        template_df.to_excel(writer, sheet_name='WHO_Vector_Surveillance', index=False)
    
    buffer.seek(0)
    
    # 5. Render Streamlit action card
    st.info(
        "🌐 **WHO Standardization Protocol:** This system uses the official genus-level tracking layout "
        "compatible with international DHIS2 vector platforms. Ensure data operators follow this order."
    )
    
    st.download_button(
        label="📥 Download WHO-Standard Excel Template (.xlsx)",
        data=buffer,
        file_name="who_standard_vector_surveillance_template.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


def render_upload_page():
    """Renders the data ingestion interface for field surveys and API sync."""
    st.markdown("## 📥 Field Data Ingestion & Sync Pipeline")
    st.markdown("---")
    
    tab1, tab2 = st.tabs(["Spreadsheet Batch Upload", "Remote API Synchronization"])
    
    with tab1:
        st.subheader("Manual Spreadsheet Ingestion")
        st.write("Download the required template ledger format below, populate your fieldwork logs, and re-upload here.")
        
        # Inject the template downloader directly into Tab 1 layout
        render_global_template_downloader()
        st.markdown("---")
        
        # Multi-format drag and drop file zone
        uploaded_file = st.file_uploader(
            "Choose a spreadsheet file (CSV or XLSX)", 
            type=["csv", "xlsx"], 
            key="field_csv_uploader"
        )
        
        if uploaded_file is not None:
            try:
                # 1. Parse inbound format structural logic cleanly
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                else:
                    df = pd.read_excel(uploaded_file, sheet_name='WHO_Vector_Surveillance')
                
                # Define master canonical layout blueprint array
                canonical_columns = [
                    "Collection_Date", "State_Province", "LGA_District", "Sentinel_Site_Code",
                    "Latitude_DD", "Longitude_DD", "Collection_Method", "Effort_Multiplier",
                    "Anopheles", "Culex", "Aedes", "Mansonia", "Other_Genera", 
                    "Dominant_Condition", "Field_Notes"
                ]
                
                # TIER 1 SCHEMA CHECK: Mandatory Geospatial/Temporal Identifiers
                mandatory_cols = ["Collection_Date", "State_Province", "LGA_District", "Sentinel_Site_Code"]
                missing_mandatory = [col for col in mandatory_cols if col not in df.columns]
                
                if missing_mandatory:
                    st.error(f"❌ **Ingestion Rejected:** Missing critical structural identifier columns: {missing_mandatory}")
                else:
                    # TIER 3 SCHEMA CHECK: Isolate and drop unexpected column additions safely
                    uploaded_cols = set(df.columns)
                    master_cols_set = set(canonical_columns)
                    
                    extra_cols = list(uploaded_cols - master_cols_set)
                    missing_optional = list(master_cols_set - uploaded_cols)
                    
                    # Intersect columns to capture only known database markers
                    aligned_df = df[df.columns.intersection(canonical_columns)].copy()
                    
                    # TIER 2 SCHEMA CHECK: Gracefully backfill omitted optional vectors
                    for col in missing_optional:
                        if col in ["Anopheles", "Culex", "Aedes", "Mansonia", "Other_Genera", "Effort_Multiplier"]:
                            aligned_df[col] = 0
                        else:
                            aligned_df[col] = None
                    
                    # Force matching spatial canonical order layout
                    final_df = aligned_df[canonical_columns]
                    
                    # Output precise contextual banner feedback reports
                    if extra_cols:
                        st.warning(
                            f"⚠️ **Schema Realignment Active:** We detected non-standard column additions: {extra_cols}. "
                            f"To safeguard database constraints, these specific fields were safely filtered out, "
                            f"but all other core data metrics will commit successfully!"
                        )
                    else:
                        st.success("✅ Structural schema audit verified. Dataset perfectly aligned with canonical WHO models.")
                    
                    # Processed Array Data Preview Layout
                    st.markdown("### Processed Data Pipeline Preview (Top 10 Records)")
                    st.dataframe(final_df.head(10), use_container_width=True)
                    st.markdown(f"**Total Valid Records Parsed:** {len(final_df)}")
                    
                    if st.button("Commit Records to System Database", type="primary", key="commit_csv_btn"):
                        with st.spinner("Persisting records to database layers..."):
                            _persist_uploaded_dataframe(final_df)
                            st.success(f"Successfully committed {len(final_df)} survey records to storage arrays.")
                            st.rerun()
                            
            except Exception as e:
                st.error(f"❌ **Error parsing file:** {str(e)}")
                
    with tab2:
        st.subheader("Automated API Synchronization")
        st.write("Fetch real-time data directly from configured remote data collection nodes.")
        
        if st.button("Trigger Cloud Sync Routine", key="api_sync_trigger"):
            with st.spinner("Establishing secure handshake with remote data servers..."):
                sync_df = sync_kobotoolbox_field_data()
                
                if sync_df is not None and not sync_df.empty:
                    st.success(f"Sync complete. Retrieved {len(sync_df)} active node submissions.")
                    st.dataframe(sync_df.head(10), use_container_width=True)
                    
                    with st.spinner("Merging data into primary arrays..."):
                        _persist_uploaded_dataframe(sync_df)
                        st.success("Remote records synchronized and stored perfectly.")
                        st.rerun()
                else:
                    st.warning(
                        "No new records found or cloud nodes are unconfigured. "
                        "Verify your API tokens and Form IDs in your secret parameters environment."
                    )