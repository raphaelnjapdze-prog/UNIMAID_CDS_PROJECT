"""
Integration Guide: Using the Ecological Probability Estimator with Image Classification.

This module demonstrates how to integrate the ecological probability estimator
with your two-stage image classification pipeline to provide:

1. Visual identification → Cryptic complex assignment (image classifier)
2. Ecological context estimate → Likely species within complex (ecological model)
3. Combined insight → "This image looks like An. gambiae complex, and based on
   where/when/where-collected it was found, An. coluzzii is most likely (~62%)"

CRITICAL: The ecological estimate is ALWAYS clearly labeled as an estimate,
never as a definitive identification.
"""

from typing import Dict, Any, Optional, Tuple
from models.inference_pipeline import MosquitoIdentificationPipeline
from models.ecological_probability_estimator import (
    EcologicalContext,
    estimate_species_probability,
    combine_image_and_ecological_estimates,
)


class IntegratedMosquitoIdentificationSystem:
    """
    Combined image + ecological inference system for mosquito species identification.
    
    Workflow:
    1. Take photo of specimen
    2. Run image classifier → get genus + species/complex + confidence
    3. If result is a cryptic complex, optionally add ecological context
    4. Return integrated result with visual + ecological insights
    """

    def __init__(
        self,
        stage1_checkpoint: str = "models/stage1_genus_classifier.pth",
        stage2_checkpoints: Optional[Dict[str, str]] = None,
    ):
        """Initialize with image classification pipeline."""
        self.pipeline = MosquitoIdentificationPipeline(
            stage1_checkpoint=stage1_checkpoint,
            stage2_checkpoints=stage2_checkpoints,
        )

    def identify_with_context(
        self,
        image_input,
        gps_coordinates: Optional[Tuple[float, float]] = None,
        region_name: Optional[str] = None,
        breeding_site_type: str = "unknown",
        month: int = 6,
    ) -> Dict[str, Any]:
        """
        Full identification pipeline: image classification + ecological context.
        
        Parameters
        ----------
        image_input : str or PIL.Image or np.ndarray
            Input image (file path, PIL Image, or numpy array)
        gps_coordinates : tuple or None
            (latitude, longitude) of collection site
        region_name : str or None
            Region/country name (used if GPS not available)
        breeding_site_type : str
            Type of breeding habitat (e.g., "permanent container", "rain pool")
        month : int
            Month of collection (1-12; 0 = unknown)
        
        Returns
        -------
        dict
            Integrated result with image classification + ecological context
        """
        # Step 1: Image classification
        image_result = self.pipeline.identify(image_input)
        
        # Step 2: If it's a cryptic complex, get ecological context
        ecological_result = None
        if image_result.get("resolution_level") == "complex":
            try:
                context = EcologicalContext(
                    complex_name=image_result["species"],
                    coordinates=gps_coordinates,
                    region_name=region_name,
                    breeding_site_type=breeding_site_type,
                    month=month,
                )
                ecological_result = estimate_species_probability(context)
            except ValueError as e:
                # Ecological context not available for this complex
                print(f"Note: Ecological context unavailable: {e}")
                ecological_result = None
        
        # Step 3: Combine results
        combined_result = combine_image_and_ecological_estimates(
            image_result, ecological_result
        )
        
        # Add metadata
        combined_result["input_metadata"] = {
            "gps_coordinates": gps_coordinates,
            "region_name": region_name,
            "breeding_site_type": breeding_site_type,
            "collection_month": month,
        }
        
        return combined_result

    def format_for_display(self, result: Dict[str, Any]) -> str:
        """
        Format the integrated result for user-friendly display.
        
        Returns
        -------
        str
            Formatted text suitable for Streamlit/UI rendering
        """
        lines = []
        
        # Image classification result
        lines.append("="*60)
        lines.append("VISUAL IDENTIFICATION (from specimen image)")
        lines.append("="*60)
        img_cls = result["image_classification"]
        lines.append(f"Genus: {img_cls['genus']}")
        lines.append(f"Predicted: {img_cls['predicted_class']}")
        lines.append(f"Resolution: {img_cls['resolution_level']} (not {img_cls['resolution_level']} ID)")
        lines.append(f"Confidence: {img_cls['confidence']:.1%}" if img_cls['confidence'] else "Confidence: N/A")
        
        # Ecological context (if available)
        if result["ecological_context"]:
            lines.append("\n" + "="*60)
            lines.append("ECOLOGICAL CONTEXT ESTIMATE (not visual ID)")
            lines.append("="*60)
            eco = result["ecological_context"]
            lines.append(f"Complex: {eco['complex']}")
            lines.append(f"Most likely species: {eco['most_likely_species']}")
            
            lines.append("\nProbability distribution:")
            for species, prob in eco["probability_distribution"].items():
                prob_pct = int(prob * 100)
                bar = "█" * (prob_pct // 5) + "░" * (20 - prob_pct // 5)
                lines.append(f"  {species:20} [{bar}] {prob_pct:3d}%")
        
        # Combined note
        lines.append("\n" + "="*60)
        lines.append("INTERPRETATION GUIDE")
        lines.append("="*60)
        lines.append(result["combined_note"])
        
        # Disclaimer
        lines.append("\n" + "="*60)
        lines.append("DISCLAIMER")
        lines.append("="*60)
        lines.append(result["disclaimer"])
        
        return "\n".join(lines)


# ============================================================================
# EXAMPLE USAGE IN STREAMLIT
# ============================================================================


def example_streamlit_integration():
    """
    Example of how to use in your Streamlit app.
    Add this to your capture component after image collection.
    """
    import streamlit as st
    
    # Initialize system once (cache it)
    @st.cache_resource
    def load_system():
        return IntegratedMosquitoIdentificationSystem(
            stage1_checkpoint="models/stage1_genus_classifier.pth",
            stage2_checkpoints={
                "Anopheles": "models/stage2_anopheles.pth",
                "Culex": "models/stage2_culex.pth",
                "Aedes": "models/stage2_aedes.pth",
            }
        )
    
    system = load_system()
    
    # Get image and metadata from user
    st.subheader("Specimen Classification")
    
    col1, col2 = st.columns([1, 1])
    with col1:
        uploaded_file = st.file_uploader("Upload specimen image", type=["jpg", "png"])
    with col2:
        st.write("Metadata (optional for context):")
        region = st.selectbox("Region", ["Senegal", "Kenya", "Mozambique", "Other"])
        habitat = st.selectbox("Breeding site", [
            "permanent container",
            "rain pool",
            "irrigated field",
            "swamp",
            "unknown"
        ])
        month = st.slider("Collection month", 1, 12, 6)
    
    if uploaded_file:
        # Run identification
        with st.spinner("Analyzing specimen..."):
            result = system.identify_with_context(
                image_input=uploaded_file,
                region_name=region,
                breeding_site_type=habitat,
                month=month,
            )
        
        # Display results
        st.markdown(system.format_for_display(result))
        
        # Show raw data for expert review
        with st.expander("Show raw result (for experts)"):
            import json
            st.json(result)


if __name__ == "__main__":
    # For testing without Streamlit
    print("Integration guide loaded. Use in Streamlit app as shown in example_streamlit_integration().")
    
    # Quick example
    system = IntegratedMosquitoIdentificationSystem()
    
    # Mock identification result (normally from actual image)
    mock_result = {
        "image_classification": {
            "genus": "Anopheles",
            "predicted_class": "An. gambiae complex",
            "resolution_level": "complex",
            "confidence": 0.92,
            "note": "This is the output of visual classification on the specimen image.",
        },
        "ecological_context": {
            "complex": "Anopheles gambiae complex",
            "probability_distribution": {
                "coluzzii": 0.62,
                "gambiae_ss": 0.28,
                "arabiensis": 0.10,
            },
            "most_likely_species": "coluzzii",
            "note": "This is an ecological inference based on geography, habitat, season — NOT visual identification.",
        },
        "combined_note": "...",
    }
    
    print("\nExample formatted output:")
    print(system.format_for_display(mock_result))
