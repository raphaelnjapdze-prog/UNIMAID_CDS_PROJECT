"""
Ecological Probability Estimator for Cryptic Mosquito Complexes.

This module provides probabilistic estimates of species composition within
morphologically indistinguishable complexes (e.g., Anopheles gambiae complex)
based on ecological context (geography, habitat, season) — NOT visual features.

CRITICAL: This module produces estimates based on published ecological
associations, NOT identifications. All outputs are explicitly labeled as
estimates and include a disclaimer that PCR is the only definitive method.

This is an INTERPRETABLE WEIGHTED-RULES SYSTEM, not a black-box ML model.
All rules and weights are documented and easily editable in the config
section below.

References:
-----------
- Malaria Atlas Project (MAP): https://malariaatlas.org/
- IR Mapper: https://irmapper.lstmed.ac.uk/
- Gillies & Coetzee (1987): A supplement to the Anophelinae of the Afrotropical Region
- Coetzee et al. (2020): Anopheles coluzzii and Anopheles amharicus, new members of the
  Anopheles gambiae complex. Zootaxa.
"""

from typing import Dict, Optional, Tuple, List, Any
from dataclasses import dataclass
import warnings


# ============================================================================
# CONFIGURATION SECTION — EDIT THIS TO ADJUST ECOLOGICAL RULES
# ============================================================================
# All weights are normalized to probabilities. Rules are based on published
# ecological associations and geographic distributions.

ECOLOGICAL_RULES = {
    "Anopheles gambiae complex": {
        # An. coluzzii: permanent/artificial freshwater, West African distribution
        "coluzzii": {
            "habitat_scores": {
                "permanent_freshwater_container": 0.90,
                "man_made_pond": 0.85,
                "irrigated_field": 0.80,
                "temporary_pool": 0.15,
                "saline_coastal_pool": 0.05,
                "rain_pool": 0.10,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # West Africa dominant
                "Senegal": 0.95, "Mali": 0.85, "Burkina_Faso": 0.90,
                "Guinea": 0.88, "Guinea_Bissau": 0.80, "Sierra_Leone": 0.85,
                "Liberia": 0.80, "Cote_d_Ivoire": 0.85, "Ghana": 0.75,
                "Benin": 0.70, "Togo": 0.65, "Nigeria": 0.60,
                "Cameroon": 0.50,  # Transition zone
                # Central/East Africa lower
                "Chad": 0.30, "Sudan": 0.20, "Ethiopia": 0.05,
                "Kenya": 0.05, "Uganda": 0.10, "Tanzania": 0.15,
                "Mozambique": 0.05, "Zambia": 0.05,
                # Default (if no region specified)
                "unknown": 0.50,
            },
            "season_scores": {
                # Dry season slight advantage (less competition from temporary-pool specialists)
                1: 0.55, 2: 0.55, 3: 0.50,  # Jan, Feb, Mar (dry)
                4: 0.50, 5: 0.45,  # Apr, May (transition)
                6: 0.40, 7: 0.35, 8: 0.35, 9: 0.40,  # Jun-Sep (wet, temp pools up)
                10: 0.50, 11: 0.55, 12: 0.55,  # Oct-Dec (dry)
                0: 0.50,  # Unknown
            },
        },
        
        # An. gambiae s.s.: temporary rain-pools, pans, more flexible distribution
        "gambiae_ss": {
            "habitat_scores": {
                "temporary_pool": 0.90,
                "rain_pool": 0.95,
                "puddle": 0.85,
                "man_made_pond": 0.50,
                "permanent_freshwater_container": 0.30,
                "saline_coastal_pool": 0.10,
                "irrigated_field": 0.60,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # Pan-African, but lower in extreme arid/coastal zones
                "Senegal": 0.60, "Mali": 0.70, "Mauritania": 0.40,
                "Burkina_Faso": 0.85, "Niger": 0.60, "Nigeria": 0.85,
                "Cameroon": 0.80, "Chad": 0.65, "Sudan": 0.70,
                "Ethiopia": 0.75, "Kenya": 0.80, "Uganda": 0.85,
                "Tanzania": 0.85, "Mozambique": 0.80, "Zambia": 0.80,
                "Zimbabwe": 0.80, "Botswana": 0.60, "South_Africa": 0.40,
                "unknown": 0.60,
            },
            "season_scores": {
                # Strong wet season preference (when temporary pools form)
                1: 0.30, 2: 0.25, 3: 0.30,  # Jan-Mar (dry)
                4: 0.45, 5: 0.65,  # Apr, May (transition/start of rains)
                6: 0.85, 7: 0.90, 8: 0.85, 9: 0.75,  # Jun-Sep (peak wet)
                10: 0.55, 11: 0.35, 12: 0.25,  # Oct-Dec (dry)
                0: 0.60,  # Unknown
            },
        },
        
        # An. arabiensis: arid-adapted, more zoophilic, inland/Sahelian distribution
        "arabiensis": {
            "habitat_scores": {
                "temporary_pool": 0.70,
                "rain_pool": 0.75,
                "irrigated_field": 0.85,
                "permanent_freshwater_container": 0.50,
                "man_made_pond": 0.40,
                "saline_coastal_pool": 0.30,
                "puddle": 0.65,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # Sahelian/arid-adapted, East Africa preferred
                "Mauritania": 0.80, "Mali": 0.85, "Senegal": 0.30,
                "Burkina_Faso": 0.50, "Niger": 0.85, "Chad": 0.85,
                "Sudan": 0.80, "Ethiopia": 0.85, "Kenya": 0.75,
                "Uganda": 0.50, "Tanzania": 0.60, "Mozambique": 0.70,
                "Zambia": 0.70, "Zimbabwe": 0.75, "Botswana": 0.85,
                "South_Africa": 0.65,
                "Nigeria": 0.25, "Cameroon": 0.30,  # Lower in humid zones
                "unknown": 0.50,
            },
            "season_scores": {
                # Flexible, but slight dry season advantage (irrigation)
                1: 0.60, 2: 0.60, 3: 0.65,  # Jan-Mar (dry)
                4: 0.55, 5: 0.50,  # Apr, May (transition)
                6: 0.45, 7: 0.40, 8: 0.40, 9: 0.50,  # Jun-Sep (wet)
                10: 0.60, 11: 0.65, 12: 0.65,  # Oct-Dec (dry)
                0: 0.55,  # Unknown
            },
        },
        
        # An. merus: saline/brackish water specialist, East African coastal
        "merus": {
            "habitat_scores": {
                "saline_coastal_pool": 0.95,
                "brackish_water": 0.90,
                "mangrove_swamp": 0.85,
                "temporary_pool": 0.05,
                "permanent_freshwater_container": 0.02,
                "rain_pool": 0.02,
                "unknown": 0.20,
            },
            "geographic_scores": {
                # East African coast only
                "Kenya": 0.90, "Tanzania": 0.85, "Mozambique": 0.70,
                "Uganda": 0.05, "Ethiopia": 0.10,
                # Not in West Africa
                "Senegal": 0.01, "Mali": 0.01, "Nigeria": 0.01,
                "Cameroon": 0.02, "Ghana": 0.01,
                "unknown": 0.20,
            },
            "season_scores": {
                # Year-round in coastal areas
                1: 0.80, 2: 0.80, 3: 0.80,
                4: 0.80, 5: 0.80, 6: 0.80,
                7: 0.80, 8: 0.80, 9: 0.80,
                10: 0.80, 11: 0.80, 12: 0.80,
                0: 0.80,
            },
        },
        
        # An. melas: saline specialist, West African coastal
        "melas": {
            "habitat_scores": {
                "saline_coastal_pool": 0.95,
                "brackish_water": 0.90,
                "mangrove_swamp": 0.85,
                "temporary_pool": 0.05,
                "permanent_freshwater_container": 0.02,
                "rain_pool": 0.02,
                "unknown": 0.20,
            },
            "geographic_scores": {
                # West African coast
                "Senegal": 0.90, "Guinea_Bissau": 0.95, "Guinea": 0.85,
                "Sierra_Leone": 0.85, "Liberia": 0.80, "Cote_d_Ivoire": 0.70,
                "Ghana": 0.65, "Benin": 0.60, "Cameroon": 0.50,
                # Not in East Africa
                "Kenya": 0.01, "Tanzania": 0.02, "Mozambique": 0.01,
                "Uganda": 0.01,
                "unknown": 0.20,
            },
            "season_scores": {
                # Year-round in coastal areas
                1: 0.80, 2: 0.80, 3: 0.80,
                4: 0.80, 5: 0.80, 6: 0.80,
                7: 0.80, 8: 0.80, 9: 0.80,
                10: 0.80, 11: 0.80, 12: 0.80,
                0: 0.80,
            },
        },
        
        # An. quadriannulatus: saline-tolerant, arid/savanna adapted
        "quadriannulatus": {
            "habitat_scores": {
                "saline_coastal_pool": 0.70,
                "temporary_pool": 0.65,
                "rain_pool": 0.60,
                "irrigated_field": 0.70,
                "permanent_freshwater_container": 0.40,
                "puddle": 0.65,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # Southern Africa primarily
                "South_Africa": 0.95, "Botswana": 0.90, "Zimbabwe": 0.85,
                "Mozambique": 0.75, "Zambia": 0.70, "Namibia": 0.80,
                # Rare elsewhere
                "Tanzania": 0.20, "Kenya": 0.10,
                "unknown": 0.30,
            },
            "season_scores": {
                1: 0.70, 2: 0.70, 3: 0.70,
                4: 0.60, 5: 0.50,
                6: 0.40, 7: 0.40, 8: 0.40, 9: 0.50,
                10: 0.70, 11: 0.75, 12: 0.75,
                0: 0.60,
            },
        },
    },
    
    "Anopheles funestus group": {
        # An. funestus s.s.: permanent freshwater, widespread sub-Saharan
        "funestus_ss": {
            "habitat_scores": {
                "permanent_freshwater_container": 0.90,
                "swamp": 0.85,
                "marsh": 0.80,
                "temporary_pool": 0.40,
                "rain_pool": 0.30,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # Widespread
                "Cameroon": 0.85, "Nigeria": 0.80, "Uganda": 0.85,
                "Tanzania": 0.80, "Kenya": 0.75, "Mozambique": 0.85,
                "Zambia": 0.80, "Zimbabwe": 0.80, "South_Africa": 0.70,
                "Malawi": 0.85, "DRC": 0.80, "Senegal": 0.40,
                "unknown": 0.60,
            },
            "season_scores": {
                1: 0.60, 2: 0.60, 3: 0.60,
                4: 0.65, 5: 0.70,
                6: 0.75, 7: 0.80, 8: 0.75, 9: 0.70,
                10: 0.65, 11: 0.60, 12: 0.60,
                0: 0.65,
            },
        },
        
        # An. rivulorum: river/stream margins, forested areas
        "rivulorum": {
            "habitat_scores": {
                "river_stream_margin": 0.90,
                "marsh": 0.85,
                "swamp": 0.80,
                "permanent_freshwater_container": 0.60,
                "temporary_pool": 0.20,
                "unknown": 0.40,
            },
            "geographic_scores": {
                # Central African forests
                "DRC": 0.85, "Uganda": 0.80, "Kenya": 0.70,
                "Tanzania": 0.65, "Cameroon": 0.60, "Gabon": 0.80,
                "South_Africa": 0.20, "Zambia": 0.30,
                "unknown": 0.40,
            },
            "season_scores": {
                1: 0.70, 2: 0.65, 3: 0.60,
                4: 0.70, 5: 0.80,
                6: 0.85, 7: 0.85, 8: 0.80, 9: 0.75,
                10: 0.70, 11: 0.65, 12: 0.70,
                0: 0.70,
            },
        },
        
        # An. parensis: forest/woodland, permanent water
        "parensis": {
            "habitat_scores": {
                "swamp": 0.85,
                "marsh": 0.80,
                "permanent_freshwater_container": 0.75,
                "temporary_pool": 0.25,
                "rain_pool": 0.15,
                "unknown": 0.50,
            },
            "geographic_scores": {
                # East/Southern African woodlands
                "Tanzania": 0.85, "Kenya": 0.70, "Uganda": 0.60,
                "Mozambique": 0.75, "Zambia": 0.80, "Zimbabwe": 0.75,
                "Malawi": 0.80, "South_Africa": 0.50,
                "unknown": 0.50,
            },
            "season_scores": {
                1: 0.65, 2: 0.60, 3: 0.55,
                4: 0.65, 5: 0.75,
                6: 0.80, 7: 0.85, 8: 0.80, 9: 0.75,
                10: 0.70, 11: 0.65, 12: 0.65,
                0: 0.68,
            },
        },
        
        # An. leesoni: rare, forest/humid zones
        "leesoni": {
            "habitat_scores": {
                "swamp": 0.80,
                "marsh": 0.75,
                "permanent_freshwater_container": 0.60,
                "temporary_pool": 0.15,
                "unknown": 0.30,
            },
            "geographic_scores": {
                # Very rare, localized
                "DRC": 0.40, "Uganda": 0.30, "Gabon": 0.35,
                "Cameroon": 0.20, "Kenya": 0.10, "Tanzania": 0.10,
                "unknown": 0.20,
            },
            "season_scores": {
                1: 0.50, 2: 0.45, 3: 0.40,
                4: 0.50, 5: 0.65,
                6: 0.70, 7: 0.75, 8: 0.70, 9: 0.60,
                10: 0.55, 11: 0.50, 12: 0.50,
                0: 0.55,
            },
        },
        
        # An. vaneedeni: rare, cryptic, permanent water
        "vaneedeni": {
            "habitat_scores": {
                "swamp": 0.80,
                "marsh": 0.75,
                "permanent_freshwater_container": 0.70,
                "temporary_pool": 0.15,
                "unknown": 0.30,
            },
            "geographic_scores": {
                # Very rare
                "Uganda": 0.40, "DRC": 0.35, "Kenya": 0.15,
                "Tanzania": 0.10, "unknown": 0.20,
            },
            "season_scores": {
                1: 0.55, 2: 0.50, 3: 0.45,
                4: 0.55, 5: 0.70,
                6: 0.75, 7: 0.80, 8: 0.75, 9: 0.65,
                10: 0.60, 11: 0.55, 12: 0.55,
                0: 0.60,
            },
        },
    },
}

# Habitat type standardization mapping (for handling variations in input)
HABITAT_ALIASES = {
    "permanent": "permanent_freshwater_container",
    "container": "permanent_freshwater_container",
    "man_made": "man_made_pond",
    "artificial": "man_made_pond",
    "pond": "man_made_pond",
    "temporary": "temporary_pool",
    "rain": "rain_pool",
    "puddle": "puddle",
    "saline": "saline_coastal_pool",
    "coastal": "saline_coastal_pool",
    "brackish": "brackish_water",
    "swamp": "swamp",
    "marsh": "marsh",
    "irrigated": "irrigated_field",
    "river": "river_stream_margin",
    "stream": "river_stream_margin",
}

# ============================================================================
# DISCLAIMER AND CONSTANT TEXT
# ============================================================================

DISCLAIMER = (
    "ECOLOGICAL PROBABILITY ESTIMATE — NOT A VISUAL IDENTIFICATION. "
    "This is a probabilistic inference based on ecological associations and geographic distribution data, "
    "derived from published sources (Malaria Atlas Project, IR Mapper, peer-reviewed taxonomy). "
    "PCR is the ONLY method to confirm the actual species identity, especially for members of the "
    "Anopheles gambiae complex and Anopheles funestus group, which are morphologically identical. "
    "Use this estimate to guide field sampling and prioritize specimen collection, not to make "
    "definitive species identifications."
)


# ============================================================================
# MAIN API
# ============================================================================


@dataclass
class EcologicalContext:
    """Container for ecological inputs."""
    complex_name: str
    coordinates: Optional[Tuple[float, float]] = None  # (latitude, longitude)
    region_name: Optional[str] = None
    breeding_site_type: str = "unknown"
    month: int = 6  # 1-12; 0 = unknown
    
    def __post_init__(self):
        if self.month < 0 or self.month > 12:
            raise ValueError("month must be 0-12 (0 = unknown)")
        if self.coordinates and len(self.coordinates) != 2:
            raise ValueError("coordinates must be (latitude, longitude)")


def _normalize_habitat_name(habitat_input: str) -> str:
    """Convert user input habitat to canonical form."""
    normalized = habitat_input.lower().replace(" ", "_").replace("-", "_")
    return HABITAT_ALIASES.get(normalized, normalized)


def _get_region_from_coordinates(
    latitude: float, longitude: float
) -> str:
    """
    Rough mapping of GPS coordinates to African regions.
    This is a simple heuristic; for production, use a proper geocoding library.
    
    Parameters
    ----------
    latitude : float
        Latitude (-90 to 90)
    longitude : float
        Longitude (-180 to 180)
    
    Returns
    -------
    str
        Country/region name
    """
    # Very rough mapping (for illustration; use geocoding library in production)
    # Format: (lat_min, lat_max, lon_min, lon_max) -> region
    
    regions = [
        # West Africa
        (12, 15, -18, -8, "Senegal"),
        (11, 13, -15, -5, "Mali"),
        (9, 14, -8, 2, "Guinea"),
        (6, 12, -15, -3, "Nigeria"),
        (3, 13, 8, 15, "Cameroon"),
        (2, 7, -1, 35, "Uganda"),
        (1, 12, 28, 41, "Kenya"),
        (-1, 5, 35, 42, "Tanzania"),
        (-5, 2, 25, 35, "Mozambique"),
        (-8, -4, 24, 33, "Zambia"),
        (-20, -10, 24, 33, "Zimbabwe"),
        (-30, -20, 20, 35, "South_Africa"),
        (-25, -20, 12, 25, "Botswana"),
    ]
    
    for lat_min, lat_max, lon_min, lon_max, region in regions:
        if lat_min <= latitude <= lat_max and lon_min <= longitude <= lon_max:
            return region
    
    return "unknown"


def estimate_species_probability(
    context: EcologicalContext,
) -> Dict[str, Any]:
    """
    Estimate the probability distribution of species within a cryptic complex
    based on ecological context.
    
    Parameters
    ----------
    context : EcologicalContext
        Container with complex_name, coordinates/region, breeding site, month
    
    Returns
    -------
    dict
        Result with keys:
        - complex: str — name of complex
        - estimate_type: str — always "ecological_probability_estimate"
        - disclaimer: str — legal/scientific disclaimer
        - probability_distribution: dict — {species_name: probability}
        - reasoning: dict — {species_name: explanation}
        - confidence_note: str — "estimate (not visual identification)"
        - input_summary: dict — what inputs were used
    
    Raises
    ------
    ValueError
        If complex_name is not in ECOLOGICAL_RULES
    """
    if context.complex_name not in ECOLOGICAL_RULES:
        raise ValueError(
            f"Complex '{context.complex_name}' not in ECOLOGICAL_RULES. "
            f"Available: {list(ECOLOGICAL_RULES.keys())}"
        )
    
    # Get region if coordinates provided
    region = context.region_name
    if not region and context.coordinates:
        region = _get_region_from_coordinates(*context.coordinates)
    if not region:
        region = "unknown"
    
    # Normalize habitat name
    habitat = _normalize_habitat_name(context.breeding_site_type)
    
    # Get rules for this complex
    complex_rules = ECOLOGICAL_RULES[context.complex_name]
    species_list = list(complex_rules.keys())
    
    # Compute scores for each species
    scores = {}
    reasoning = {}
    
    for species in species_list:
        rules = complex_rules[species]
        
        # Get individual scores
        habitat_score = rules["habitat_scores"].get(habitat, 0.3)
        geographic_score = rules["geographic_scores"].get(region, 0.3)
        season_score = rules["season_scores"].get(context.month, 0.5)
        
        # Geometric mean of scores (emphasizes cases where ALL are high)
        combined_score = (habitat_score * geographic_score * season_score) ** (1/3)
        scores[species] = combined_score
        
        # Build reasoning
        reasoning[species] = (
            f"Habitat: {habitat} (score={habitat_score:.2f}), "
            f"Region: {region} (score={geographic_score:.2f}), "
            f"Month: {context.month} (score={season_score:.2f})"
        )
    
    # Normalize to probability distribution
    total_score = sum(scores.values())
    probabilities = {s: scores[s] / total_score for s in species_list}
    
    # Sort by probability (descending)
    probabilities = dict(sorted(probabilities.items(), key=lambda x: x[1], reverse=True))
    reasoning = {k: reasoning[k] for k in probabilities.keys()}
    
    return {
        "complex": context.complex_name,
        "estimate_type": "ecological_probability_estimate",
        "disclaimer": DISCLAIMER,
        "probability_distribution": {k: round(v, 3) for k, v in probabilities.items()},
        "reasoning": reasoning,
        "confidence_note": "estimate (not visual identification)",
        "input_summary": {
            "coordinates": context.coordinates,
            "region": region,
            "breeding_site_type": habitat,
            "month": context.month,
        },
    }


def combine_image_and_ecological_estimates(
    image_classification_result: Dict[str, Any],
    ecological_estimate: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combine image classification (cryptic complex assignment) with ecological
    probability estimates to provide a richer result that shows:
    1. What the image classifier says (complex name)
    2. What ecology suggests as most likely species within that complex
    3. Clear caveats about both sources
    
    Parameters
    ----------
    image_classification_result : dict
        Output from inference_pipeline.identify() with species (complex name)
    ecological_estimate : dict or None
        Output from estimate_species_probability(). If None, only image result returned.
    
    Returns
    -------
    dict
        Combined result with image + ecological insights and disclaimers
    """
    result = {
        "image_classification": {
            "genus": image_classification_result.get("genus"),
            "predicted_class": image_classification_result.get("species"),
            "resolution_level": image_classification_result.get("resolution_level"),
            "confidence": image_classification_result.get("stage2_confidence"),
            "note": "This is the output of visual classification on the specimen image.",
        },
        "ecological_context": None,
    }
    
    if ecological_estimate:
        result["ecological_context"] = {
            "complex": ecological_estimate.get("complex"),
            "probability_distribution": ecological_estimate.get("probability_distribution"),
            "most_likely_species": max(
                ecological_estimate.get("probability_distribution", {}).items(),
                key=lambda x: x[1]
            )[0] if ecological_estimate.get("probability_distribution") else None,
            "note": "This is an ecological inference based on geography, habitat, season — NOT visual identification.",
        }
    
    result["combined_note"] = (
        "IMPORTANT: For cryptic complexes (An. gambiae complex, An. funestus group), "
        "the image classifier assigns to the complex level, and ecological context suggests "
        "likely members. PCR is required for definitive species identity."
    )
    result["disclaimer"] = DISCLAIMER
    
    return result


if __name__ == "__main__":
    # Example usage
    print("Ecological Probability Estimator for Cryptic Complexes\n")
    
    # Example 1: Anopheles gambiae complex in West Africa, permanent freshwater
    context1 = EcologicalContext(
        complex_name="Anopheles gambiae complex",
        coordinates=(14.0, -12.0),  # Senegal region
        breeding_site_type="permanent container",
        month=3,  # March (dry season)
    )
    result1 = estimate_species_probability(context1)
    print("Example 1: West Africa (Senegal area), permanent freshwater, March")
    print(f"  Probabilities: {result1['probability_distribution']}\n")
    
    # Example 2: Same complex, different habitat/season
    context2 = EcologicalContext(
        complex_name="Anopheles gambiae complex",
        region_name="Kenya",
        breeding_site_type="rain pool",
        month=8,  # August (wet season)
    )
    result2 = estimate_species_probability(context2)
    print("Example 2: Kenya, rain pool, August (wet season)")
    print(f"  Probabilities: {result2['probability_distribution']}\n")
    
    # Example 3: Anopheles funestus group
    context3 = EcologicalContext(
        complex_name="Anopheles funestus group",
        region_name="Mozambique",
        breeding_site_type="swamp",
        month=7,
    )
    result3 = estimate_species_probability(context3)
    print("Example 3: Mozambique, swamp, July")
    print(f"  Probabilities: {result3['probability_distribution']}\n")
