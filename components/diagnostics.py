# =========================================================================
# WHO-LEVEL DIAGNOSTIC MATRIX INTERFACE (components/diagnostics.py)
# =========================================================================
import streamlit as st
from utils.data_manager import (
    _load_master_df, 
    analyze_advanced_adult_morphology, 
    process_adult_image_inference, 
    process_larval_image_inference,
    generate_ai_intervention_response
)

def render_diagnostics_page():
    """Renders the upgraded world-class vector classification workspace."""
    st.markdown("## 🔬 Advanced Anopheles Taxonomy & AI Diagnostics")
    st.markdown("---")

    tab1, tab2, tab3 = st.tabs([
        "Adult Morphological Diagnostic Key", 
        "Larval Computer Vision Portal",
        "AI Operational Response System"
    ])

    # TAB 1: ADULT TAXONOMIC MATRIX
    with tab1:
        st.subheader("WHO-Standard Adult Verification Node")
        st.write("Isolate 11 African and invasive vector species using advanced dichotomous keys or computer vision feature maps.")

        input_method = st.radio(
            "Choose Analysis Modality",
            ["Microscopic Manual Key Entry", "Instant Image CV Diagnostic Scan"],
            horizontal=True,
            key="adult_modality_toggle"
        )
        st.markdown("---")

        if input_method == "Microscopic Manual Key Entry":
            col1, col2 = st.columns([5, 4])
            with col1:
                st.markdown("#### High-Resolution Morphological Landmark Inputs")
                
                antenna = st.radio(
                    "Antennal Whorls (Sex Separation)",
                    ["Sparsely Hairs/Unbrushed (Pilose - Female)", "Heavily Brushed (Plumose - Male)"]
                )
                
                # Critical Palpal Band Selection
                palpal_bands = st.selectbox(
                    "Maxillary Palps Banding Profile",
                    [
                        "3 Pale Bands (Standard)", 
                        "2 Broad Apical Bands + 1 Narrow Base Band", 
                        "1 Single Apical Pale Band",
                        "Dark / Completely Unbanded"
                    ]
                )
                
                # Leg Speckling Check
                leg_speckling = st.radio(
                    "Femora & Tibiae Speckling (Leg Ornamentation)",
                    ["Completely Smooth / Unspeckled", "Heavily Speckled / Mottled"]
                )
                
                # Hind Tarsi Check
                hind_tarsi = st.selectbox(
                    "Hind Leg Tarsomeres Shading Arrays",
                    [
                        "White Bands at Tarsal Joints Only",
                        "Tarsomeres 3, 4, 5 Completely White (Snow-Boots appearance)", 
                        "Tarsomeres 4 & 5 White, 3 White-Tipped", 
                        "Entirely Dark / Unbanded"
                    ]
                )
                
                # Abdominal Tufts Check
                abdominal_tufts = st.radio(
                    "Abdominal Tergites Post-Lateral Margins",
                    ["Absence of lateral scale tufts", "Prominent Lateral Dark Scale Tufts Present (Shaggy)"]
                )
                
                # Baseline markers for routing fallbacks
                wing_bands = st.selectbox("Wing Costa Scale Layout", ["Distinct Dark/Pale Costal Spots", "Uniformly Dark / Clear", "Asymmetric Dense Shaggy Scale Layout"])
                thorax_color = st.selectbox("General Thorax Body Color Shading (Cryptic Sibling Splitter)", ["Ash Gray / Pale", "Dark Brown / Black", "Tan / Ochre"])
                thorax_back = st.selectbox("Scutum Markings Profile", ["Dark/Pale Shaded Patterns without clear lines", "Uniform Dull Brown/Golden Scales", "Silvery Lyre-Shaped Pattern"])

                taxonomic_payload = {
                    "antenna": antenna, "palpal_bands": palpal_bands, "leg_speckling": leg_speckling,
                    "hind_tarsi": hind_tarsi, "abdominal_tufts": abdominal_tufts, "wing_bands": wing_bands,
                    "thorax_color": thorax_color, "thorax_back": thorax_back
                }
                
                execute_adult_calc = st.button("Execute Taxonomic Key Resolution", type="primary", use_container_width=True)

            with col2:
                st.markdown("#### Real-Time Key Resolution Output")
                if execute_adult_calc:
                    with st.spinner("Resolving taxonomical definitions..."):
                        res = analyze_advanced_adult_morphology(taxonomic_payload)
                        
                        if "stephensi" in res["species"].lower():
                            st.error(f"⚠️ TARGET DETECTED: {res['species']}")
                        elif "Anopheles" in res["genus"]:
                            st.success(f"Verified Genus: {res['genus']}")
                        else:
                            st.warning(f"Identified Genus: {res['genus']}")
                            
                        st.markdown(f"**Resolved Species Profile:** *{res['species']}*")
                        if res["subspecies"] != "N/A":
                            st.markdown(f"**Identified Sub-Species/Variant:** ` {res['subspecies']} `")
                        st.markdown(f"**Surveillance Sex Flag:** {res['sex']}")
                        
                        st.markdown("---")
                        st.write(res["significance"])
                        st.metric("Identification Confidence Level", res["confidence"])
                else:
                    st.info("Adjust morphological markers on the left and select execute to run classification trees.")

        else:
            # INSTANT IMAGE DIAGNOSTIC SCAN INTERFACE
            col1, col2 = st.columns([4, 5])
            with col1:
                st.markdown("#### Adult Specimen Ingestion Portal")
                uploaded_adult = st.file_uploader("Upload Adult Image Asset (JPG/PNG)", type=["jpg", "jpeg", "png"], key="adult_img_uploader")
                if uploaded_adult:
                    st.image(uploaded_adult, caption="Ingested Adult Specimen Node", use_container_width=True)
            
            with col2:
                st.markdown("#### Automated Landmark Feature Extraction")
                if uploaded_adult:
                    with st.spinner("Executing neural feature parsing passes..."):
                        cv_res = process_adult_image_inference(uploaded_adult)
                        
                        if "stephensi" in cv_res["species"].lower():
                            st.error(f"**AI Classification Result:** {cv_res['species']}")
                        else:
                            st.success(f"**AI Classification Result:** {cv_res['species']}")
                            
                        st.metric("Taxonomic Accuracy Confidence Score", cv_res["confidence"])
                        st.markdown(f"**Isolate Sub-species Profile:** ` {cv_res['subspecies']} `")
                        st.markdown(f"**Demographic Determination:** {cv_res['sex']}")
                        
                        st.markdown("##### 🔍 Segmented WHO Landmark Indicators")
                        for feature, diagnostic in cv_res["extracted_landmarks"].items():
                            st.markdown(f"- **{feature}:** {diagnostic}")
                            
                        st.markdown("---")
                        st.write(cv_res["significance"])
                else:
                    st.info("Upload an image of an adult mosquito to extract structural landmarks and identify the specimen instantly.")

    # TAB 2: LARVAL PORTAL (UNCHANGED FUNCTIONALITY)
    with tab2:
        st.subheader("Automated Immature Stage (Larval) Recognition")
        st.write("Upload clear microscopic or high-resolution field photos of collected fourth-instar larvae to audit diagnostic siphon structures.")
        uploaded_img = st.file_uploader("Upload Larval Ingestion Asset (JPG / PNG)", type=["jpg", "jpeg", "png"], key="larval_image_uploader")

        if uploaded_img is not None:
            l_col1, l_col2 = st.columns(2)
            with l_col1:
                st.image(uploaded_img, caption="Ingested Field Larval Specimen", use_container_width=True)
            with l_col2:
                st.markdown("#### Neural Network Structural Feature Map")
                with st.spinner("Running tensor segmentation passes..."):
                    larva_res = process_larval_image_inference(uploaded_img)
                    st.success(f"**Classification Hit:** {larva_res['detected_genus']} Larva")
                    st.markdown(f"**Developmental Progress:** {larva_res['stage']}")
                    st.markdown(f"**WHO Reference Proxy:** *{larva_res['who_classification']}*")
                    st.info(f"**Observed Morphological Keys:**\n{larva_res['taxonomic_markers']}")
                    st.metric("Visual Match Confidence Score", larva_res["confidence"])
        else:
            st.info("Upload field larval imagery arrays to process automated diagnostic segmentation pipelines.")

    # TAB 3: OPERATIONAL RESPONSE
    with tab3:
        st.subheader("Epidemiological Threat Modeling")
        st.write("Synthesize real-time environmental data with vector counts to map response protocols.")
        df = _load_master_df()
        if df.empty:
            st.warning("No data layers present to construct models.")
        else:
            query_in = st.text_input("Input custom epidemiological query guidelines:")
            if st.button("Compile Advisory Briefing", type="primary"):
                st.markdown(generate_ai_intervention_response(df, query_in))