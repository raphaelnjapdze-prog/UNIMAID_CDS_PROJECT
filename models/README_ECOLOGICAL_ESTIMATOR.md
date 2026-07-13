# Ecological Probability Estimator for Cryptic Complexes

## Overview

The ecological probability estimator is a **completely separate layer** from the image classification pipeline that provides probabilistic estimates of which species is most likely within a morphologically indistinguishable complex, based on **ecological context alone** (not visual features).

### Why This Exists

Morphologically identical species complexes cannot be separated by any image classifier, no matter how well trained. However, ecological data (where and when a specimen was collected, what habitat it was found in) provides strong predictive signals:

- **An. coluzzii** strongly prefers permanent man-made freshwater (containers, cisterns)
- **An. gambiae s.s.** prefers temporary rain-fed pools and is abundant in wet seasons
- **An. arabiensis** is more arid-adapted and found in irrigation schemes
- **An. merus** (East African coast) and **An. melas** (West African coast) strictly breed in saline/brackish water

This estimator **does NOT replace molecular identification (PCR)**, but it provides ecologically-grounded guidance for:
- Prioritizing which species to validate by PCR
- Understanding likely species composition in a region
- Informing field sampling strategies

### Critical Distinction

| Method | Output | What It Means |
|--------|--------|--------------|
| Image Classifier | "An. gambiae complex" | Visually matches complex; cannot distinguish members |
| Ecological Estimator | {coluzzii: 0.62, gambiae_ss: 0.28, arabiensis: 0.10} | Based on geography+habitat+season, these likelihoods |
| **PCR (Definitive)** | **"An. coluzzii s.s."** | **Confirmed at molecular level** |

---

## How It Works

### Input Parameters

```python
context = EcologicalContext(
    complex_name="Anopheles gambiae complex",
    coordinates=(14.0, -12.0),  # Latitude, Longitude (optional)
    region_name="Senegal",      # OR region name (optional)
    breeding_site_type="permanent container",
    month=3,  # 1-12 (month of collection)
)
result = estimate_species_probability(context)
```

### Scoring Model

For each species in the complex:

1. **Habitat Score**: How well-suited the breeding site is for this species (0.0–1.0)
2. **Geographic Score**: How common this species is in the region (0.0–1.0)
3. **Seasonal Score**: How abundant this species is at this time of year (0.0–1.0)

The combined score uses **geometric mean** (emphasizes cases where all three factors are favorable):

```
combined_score = (habitat_score × geographic_score × seasonal_score) ^ (1/3)
```

Scores are **normalized to probabilities** so they sum to 1.0:

```
probability = combined_score / sum(all_combined_scores)
```

### Output

```python
{
    "complex": "Anopheles gambiae complex",
    "estimate_type": "ecological_probability_estimate",
    "disclaimer": "[Long legal/scientific disclaimer]",
    "probability_distribution": {
        "coluzzii": 0.62,
        "gambiae_ss": 0.28,
        "arabiensis": 0.10,
        # ... other members ...
    },
    "reasoning": {
        "coluzzii": "Habitat: permanent_container (0.90), Region: Senegal (0.95), Month: 3 (0.55)",
        "gambiae_ss": "Habitat: permanent_container (0.30), Region: Senegal (0.60), Month: 3 (0.30)",
        # ... etc ...
    },
    "confidence_note": "estimate (not visual identification)",
    "input_summary": {
        "coordinates": (14.0, -12.0),
        "region": "Senegal",
        "breeding_site_type": "permanent_container",
        "month": 3,
    }
}
```

---

## Editing the Rules

All ecological rules are in the **`ECOLOGICAL_RULES` dict** at the top of `models/ecological_probability_estimator.py`. This is intentionally placed at the module level for easy discovery and editing.

### Structure

```python
ECOLOGICAL_RULES = {
    "Anopheles gambiae complex": {
        "coluzzii": {
            "habitat_scores": {
                "permanent_freshwater_container": 0.90,
                "man_made_pond": 0.85,
                "temporary_pool": 0.15,
                # ...
            },
            "geographic_scores": {
                "Senegal": 0.95,
                "Kenya": 0.05,
                "unknown": 0.50,
                # ...
            },
            "season_scores": {
                1: 0.55,  # January
                6: 0.40,  # June (wet season, temporary pools more competitive)
                # ...
            },
        },
        # ... other species ...
    },
    # ... other complexes ...
}
```

### How to Adjust Scores

1. **Increase a habitat score** if new research shows a species strongly prefers it
   - Example: "An. coluzzii now documented breeding in rice paddies" → increase `"irrigated_field": 0.80`

2. **Decrease a geographic score** if field data shows lower prevalence
   - Example: "An. coluzzii much rarer in Uganda than expected" → decrease `"Uganda": 0.15`

3. **Shift seasonal scores** if feeding/breeding patterns change
   - Example: "An. arabiensis peaks during dry season irrigation" → increase dry-season months

### Example: Updating Rules Based on New Literature

**Scenario**: You read a paper showing *An. coluzzii* is expanding into East African irrigation schemes.

**Action**:
1. Open `models/ecological_probability_estimator.py`
2. Find `ECOLOGICAL_RULES["Anopheles gambiae complex"]["coluzzii"]["geographic_scores"]`
3. Change:
   ```python
   "Kenya": 0.05,      # OLD
   "Kenya": 0.25,      # NEW (up from 0.05)
   "Uganda": 0.10,     # OLD
   "Uganda": 0.20,     # NEW (acknowledging expansion)
   ```
4. Re-run validation:
   ```bash
   python models/ecological_probability_estimator.py
   ```

---

## Supported Complexes

### Anopheles gambiae complex
- **Members**: coluzzii, gambiae_ss, arabiensis, merus, melas, quadriannulatus
- **Ecological references**: Gillies & Coetzee (1987), Coetzee et al. (2020), Malaria Atlas Project
- **Common in**: Sub-Saharan Africa

### Anopheles funestus group
- **Members**: funestus_ss, rivulorum, parensis, leesoni, vaneedeni
- **Ecological references**: Gillies & Coetzee (1987), Coetzee et al. (2020)
- **Common in**: Sub-Saharan Africa, East Africa particularly

---

## Integration with Image Classification

### Workflow

```
Image of mosquito specimen
        ↓
[IMAGE CLASSIFIER: Stage 1 → Stage 2]
        ↓
Returns: {genus, species, resolution_level, confidence}
        ↓
If resolution_level == "complex":
    Get GPS + habitat + season from collection metadata
        ↓
    [ECOLOGICAL ESTIMATOR]
        ↓
    Returns: {probability_distribution within complex}
        ↓
    Combined result shows:
    - "Image looks like An. gambiae complex"
    - "Based on Senegal (GPS), permanent container (habitat), March (season):"
    - "  An. coluzzii: 62% likely"
    - "  An. gambiae s.s.: 28% likely"
    - "  [DISCLAIMER: PCR needed for confirmation]"
```

### Code Example

```python
from models.inference_pipeline import MosquitoIdentificationPipeline
from models.ecological_probability_estimator import (
    EcologicalContext, estimate_species_probability
)

# Step 1: Image classification
pipeline = MosquitoIdentificationPipeline(
    stage1_checkpoint="models/stage1_genus_classifier.pth",
    stage2_checkpoints={...}
)
image_result = pipeline.identify("specimen.jpg")

# Step 2: If cryptic complex, add ecological context
if image_result["resolution_level"] == "complex":
    context = EcologicalContext(
        complex_name=image_result["species"],
        coordinates=(gps_lat, gps_lon),  # From field data
        breeding_site_type="permanent container",
        month=3,
    )
    ecological_result = estimate_species_probability(context)
    print(f"Image: {image_result['species']}")
    print(f"Most likely member: {max(ecological_result['probability_distribution'].items())}")
```

For a full integration example, see `models/integration_example.py`.

---

## Caveats & Limitations

1. **Not a replacement for PCR**: This is an ecological estimate, not a definitive identification.

2. **Garbage in, garbage out**: If GPS/habitat/month data is wrong, the estimate is wrong.

3. **Limited to documented regions**: If you enter a region not in the rules (e.g., a new country), the estimator falls back to `"unknown"` scores (typically 0.3–0.5).
   - To add a new region: Find the relevant `geographic_scores` dict for each species and add the region with an estimated score.

4. **Seasonal assumptions**: Scores assume a single hemisphere's dry/wet season. If you collect year-round in a region with two seasons, you may need to adjust.

5. **Rare species may be underestimated**: Species like *An. leesoni* and *An. vaneedeni* have sparse published distribution data, so their scores are more uncertain.

---

## Validation & Testing

### Run Self-Test

```bash
cd models/
python ecological_probability_estimator.py
```

This prints three test scenarios:
1. An. gambiae complex in Senegal (permanent freshwater, March)
2. An. gambiae complex in Kenya (rain pool, August)
3. An. funestus group in Mozambique (swamp, July)

**Expected behavior**:
- Test 1: *An. coluzzii* and *An. melas* should be high (West Africa permanent-water specialists)
- Test 2: *An. gambiae s.s.* should be highest (temporary pool preference, wet season)
- Test 3: *An. funestus s.s.* and *An. parensis* should be high (permanent-water specialists in East Africa)

If results don't match expectations, check:
- Typos in species names (use underscores, not spaces: `gambiae_ss` not `gambiae ss`)
- Coordinate-to-region mapping (very basic; use a proper geocoder for production)
- Habitat name standardization (the `HABITAT_ALIASES` dict handles common variations)

---

## References

1. **Malaria Atlas Project (MAP)**: https://malariaatlas.org/
   - Global distribution maps of Anopheles species
   - Regular updates based on field surveys

2. **IR Mapper**: https://irmapper.lstmed.ac.uk/
   - Insecticide resistance prevalence maps
   - Species-level geographic data

3. **Gillies & Coetzee (1987)**: *A supplement to the Anophelinae of the Afrotropical Region*
   - Classical taxonomy and ecology reference
   - Standard for morphological identification

4. **Coetzee et al. (2020)**: *Anopheles coluzzii and Anopheles amharicus, new members of the Anopheles gambiae complex*
   - Recent cryptic complex updates
   - Distribution data for newly described species

5. **White et al. (2011)**: *Anopheles gambiae complex: species groups within the complex*
   - Detailed ecological partitioning data
   - Sympatry and allopatry zones

---

## Troubleshooting

### Q: Why does *An. arabiensis* have 0% probability in my result?

**A**: Check your `geographic_score`. If you're in a region where it's rare (e.g., humid West African coast), it will be downweighted. If that's unexpected, verify:
- You entered the correct region name (exact spelling, underscores not spaces)
- The region is covered in the rules (see `geographic_scores` dicts)
- Your field observations match; if you actually found *An. arabiensis*, the rules may need updating

### Q: The ecological probabilities don't match field data—should I adjust the rules?

**A**: Possibly, but gather evidence first:
1. Collect *n*>30 specimens per species in a region
2. Genotype by PCR or DNA sequencing to confirm identities
3. Tabulate species composition vs. habitat/season
4. Update the relevant scores in `ECOLOGICAL_RULES`
5. Document the change with a comment citing your data

### Q: Can I add a new species to a complex?

**A**: No—new species should first be formally described in peer-reviewed literature. Once published, add it:
1. Create a new entry in the complex's `ECOLOGICAL_RULES` dict
2. Fill in habitat, geographic, and seasonal scores based on the literature
3. Test with `python ecological_probability_estimator.py`

---

## Version History

- **v1.0** (2026): Initial implementation based on Gillies & Coetzee (1987), Malaria Atlas Project, and published distribution surveys.

