"""
Taxonomic Reference & Morphological Screening Engine for Afrotropical Vectors.
Implements genus-level triage arrays, larval separation mechanics, and comprehensive
species reference catalogs for 60 distinct African mosquito profiles.

Grounded completely in standard reference criteria: Coetzee (2020), Gillies &
Coetzee (1987), Service (1990), and Jupp (1996).

── Anopheles Deep-Key Engine ──────────────────────────────────────────────
Beyond the genus/marker triage above, this module carries a dedicated,
character-driven identification engine for adult female *Anopheles* — the
genus that matters most for malaria surveillance. It has three pillars:

  1. ANOPHELES_CHARACTERS      — a controlled vocabulary of the real
     diagnostic characters used in the standard adult keys (wing pale/dark
     spots, maxillary-palp banding, hind-tarsi banding, leg speckling, …),
     each weighted by discriminating power.
  2. identify_anopheles_species() — a transparent weighted-agreement scorer
     that ranks catalogued species against observed characters and reports a
     per-character audit trail (what matched, what contradicted).
  3. ANOPHELES_COUPLET_KEY + anopheles_key_step() — a genuine dichotomous
     couplet walker mirroring Gillies & Coetzee (1987).

DOMAIN GUARDRAIL (hard rule, matches models/ and vision_inference.py): the
*An. gambiae* complex and *An. funestus* group are morphologically
inseparable to species. Both engines here therefore expose a per-taxon
`resolution_level` (`species` / `group` / `complex`) and **collapse** any
complex/group hit to the complex/group name with `molecular_id_required=True`
— they never manufacture a single-species answer the morphology can't support.
This is a screening aid, not a validated diagnostic device.
"""

# --- GENUS LEVEL DEFINITIONS ---
GENUS_TRIAGE_MATRIX = {
    "Anopheles": {
        "resting_posture": "Abdomen angled away from surface (head-down, body tilted ~45°)",
        "female_palps": "Long — nearly as long as proboscis",
        "male_palps": "Long, often clubbed at tip",
        "wing_scales": "Often patterned with pale/dark spots",
        "female_abdomen_tip": "Pointed, no obvious scale tufts",
        "scutum_pattern": "Variable, often plain",
        "postspiracular_setae": "Present in many spp.",
        "body_color": "Brownish, subdued"
    },
    "Culex": {
        "resting_posture": "Abdomen roughly parallel to surface",
        "female_palps": "Short — much shorter than proboscis",
        "male_palps": "Long, upcurved at tip",
        "wing_scales": "Usually uniform brown, unpatterned",
        "female_abdomen_tip": "Blunt/rounded, scale-covered",
        "scutum_pattern": "Plain brown/tan",
        "postspiracular_setae": "Absent",
        "body_color": "Brown/tan, dull"
    },
    "Aedes": {
        "resting_posture": "Abdomen parallel to surface",
        "female_palps": "Short — much shorter than proboscis",
        "male_palps": "Long, upcurved at tip",
        "wing_scales": "Often unpatterned, but body usually patterned",
        "female_abdomen_tip": "Pointed, with terminal cerci visible",
        "scutum_pattern": "Frequently silver/white scale patterns (lines, lyre-shapes) on dark background",
        "postspiracular_setae": "Absent",
        "body_color": "Often strikingly black-and-white or black-and-silver banded"
    }
}

# --- COMPLETE SPECIES CATALOG MATRIX (ALL 60 SPECIES) ---
SPECIES_CATALOG = {
    "Anopheles": [
        {
            "id": 1,
            "name": "Anopheles gambiae (s.s.)",
            "vector_status": "Primary malaria vector",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "Microscopic key sorting required"],
            "notes": "Morphologically indistinguishable from coluzzii, arabiensis, merus, melas, quadriannulatus, bwambae. PCR (Scott et al. 1993) mandatory for confirmation."
        },
        {
            "id": 2,
            "name": "Anopheles coluzzii",
            "vector_status": "Primary malaria vector",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "Permanent or man-made aquatic breeding associations"],
            "notes": "Visually identical to other complex members. Ecologically associated with permanent/man-made water bodies vs. gambiae s.s.'s rain-pool preference."
        },
        {
            "id": 3,
            "name": "Anopheles arabiensis",
            "vector_status": "Primary malaria vector",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "Exophilic / Zoophilic behavioural trends"],
            "notes": "Visually identical to other complex members. Shows more zoophilic/exophilic tendency than An. gambiae s.s."
        },
        {
            "id": 4,
            "name": "Anopheles merus",
            "vector_status": "Secondary/local vector",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "Coastal saline-water breeding habitat"],
            "notes": "Gambiae complex member strictly limited to coastal saline-water environments."
        },
        {
            "id": 5,
            "name": "Anopheles melas",
            "vector_status": "Secondary/local vector",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "West African mangrove / saline-water breeding habitat"],
            "notes": "Gambiae complex member restricted to West African mangrove/saline eco-zones."
        },
        {
            "id": 6,
            "name": "Anopheles quadriannulatus",
            "vector_status": "Non-vector (zoophilic)",
            "molecular_id_required": True,
            "group_complex": "An. gambiae complex",
            "field_markers": ["Standard gambiae complex features", "Strictly zoophilic responses"],
            "notes": "Gambiae complex member. Strictly zoophilic feeding habits render it a non-vector of human malaria."
        },
        {
            "id": 7,
            "name": "Anopheles funestus (s.s.)",
            "vector_status": "Primary malaria vector",
            "molecular_id_required": True,
            "group_complex": "An. funestus group",
            "field_markers": ["Dark wings", "Pale spotting concentrated at wing tip and costa"],
            "notes": "Member of An. funestus group (rivulorum, parensis, leesoni, vaneedeni, rivulorum-like). Prefers clean, vegetated, permanent water bodies."
        },
        {
            "id": 8,
            "name": "Anopheles rivulorum",
            "vector_status": "Secondary vector",
            "molecular_id_required": True,
            "group_complex": "An. funestus group",
            "field_markers": ["Standard funestus group features"],
            "notes": "Funestus group member. Indistinguishable from An. funestus s.s. under field conditions; requires PCR."
        },
        {
            "id": 9,
            "name": "Anopheles leesoni",
            "vector_status": "Non-vector",
            "molecular_id_required": True,
            "group_complex": "An. funestus group",
            "field_markers": ["Standard funestus group features"],
            "notes": "Funestus group member. Captured in field vector screens but poses no transmission risks."
        },
        {
            "id": 10,
            "name": "Anopheles nili",
            "vector_status": "Primary/secondary vector (Central/West Africa)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Wing with a pale spot at base of vein 6", "Pale fringe spots evenly distributed"],
            "notes": "Genuinely morphologically distinguishable from the funestus group. Breeds preferentially in fast-flowing, well-oxygenated streams."
        },
        {
            "id": 11,
            "name": "Anopheles moucheti",
            "vector_status": "Primary vector (Central Africa, riverine)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Dark wings", "Relatively unpatterned wing scales"],
            "notes": "Associated with slow river margins and backwaters with floating vegetation. Adult separation benefits from molecular tools in zones of sympatry."
        },
        {
            "id": 12,
            "name": "Anopheles pharoensis",
            "vector_status": "Secondary vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Larger-bodied structure", "Broad, distinct pale and dark scale blocks along costal margin"],
            "notes": "One of the most morphologically distinctive African Anopheles. Breeds in heavily vegetated swamps and rice fields."
        },
        {
            "id": 13,
            "name": "Anopheles squamosus",
            "vector_status": "Secondary/minor vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Pale, lightly-scaled wings", "Widespread savanna distribution"],
            "notes": "Widespread savanna species. Frequently confused with coustani; fine separation requires careful evaluation of tarsal banding structures."
        },
        {
            "id": 14,
            "name": "Anopheles coustani",
            "vector_status": "Secondary/minor vector",
            "molecular_id_required": False,
            "group_complex": "An. coustani group",
            "field_markers": ["Wing pattern similar to squamosus", "Hindtarsi with narrow pale rings at joints"],
            "notes": "Treat as a collective species group in routine field surveys unless advanced dichotomous sorting keys are explicitly utilized."
        },
        {
            "id": 15,
            "name": "Anopheles ziemanni",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "An. coustani group",
            "field_markers": ["Resembles coustani macro-profile", "Grassy swamp margin breeding habitat"],
            "notes": "Resembles the coustani group framework. Field separation is highly unreliable; log as coustani-group unless laboratory dissection is executed."
        },
        {
            "id": 16,
            "name": "Anopheles rufipes",
            "vector_status": "Minor vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Legs with reddish-brown tarsal banding ('red-footed')"],
            "notes": "Widespread savanna species closely linked with seasonal rice-field cultivation environments."
        },
        {
            "id": 17,
            "name": "Anopheles wellcomei",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Small, pale species structure", "Sahelian distribution profile"],
            "notes": "Sahelian distribution. Confirmed strictly through couplet keys; not reliably identifiable by macro field observation alone."
        },
        {
            "id": 18,
            "name": "Anopheles maculipalpis",
            "vector_status": "Non-vector/minor",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Distinct dark-spotted palpi"],
            "notes": "Possesses a genuinely field-visible, name-diagnostic palp marker that simplifies structural identification."
        },
        {
            "id": 19,
            "name": "Anopheles demeilloni",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Cool-climate highland structural attributes"],
            "notes": "East and Central African highland species associated with cooler montane conditions; requires complete stereomicroscopic keying."
        },
        {
            "id": 20,
            "name": "Anopheles stephensi",
            "vector_status": "Emerging invasive primary vector",
            "molecular_id_required": True,
            "biosecurity_alert": True,
            "group_complex": "Invasive Strain",
            "field_markers": ["Container / urban water breeder", "Unique palpal banding sequences (see 2020 key)"],
            "notes": "⚠️ CRITICAL SURVEILLANCE TARGET: Invasive Asian urban vector expanding across the Horn of Africa and Nigeria. Breeds in artificial containers and urban settings, mimicking Aedes aegypti bionomics."
        },
        # ── Desert / oasis, highland and additional cryptic-group Anopheles ──
        {"id": 21, "name": "Anopheles pretoriensis", "vector_status": "Non-vector / very minor",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Speckled legs", "Pale-tipped palps", "Drier savanna, rock pools"],
         "notes": "Widespread in drier/rocky savanna. Superficially coustani-like but structurally separable; not an important vector."},
        {"id": 22, "name": "Anopheles sergentii", "vector_status": "Oasis malaria vector (N. Africa / Sahara)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Desert oasis breeder", "Narrow apical tarsal pale bands"],
         "notes": "The classic Saharan 'oasis' malaria vector; localised to spring-fed oases and desert margins."},
        {"id": 23, "name": "Anopheles multicolor", "vector_status": "Minor / local vector (arid zones)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Very pale body", "Broad pale tarsal banding", "Saline oasis / arid habitats"],
         "notes": "Pale desert species of saline oasis waters across North Africa and the Sahel fringe."},
        {"id": 24, "name": "Anopheles dthali", "vector_status": "Minor / local vector (arid zones)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Distinctly speckled legs", "Rocky wadi / mountain-desert pools"],
         "notes": "Rock-pool breeder of arid mountain wadis (Saharo-Arabian). Speckled legs; can be locally involved in transmission."},
        {"id": 25, "name": "Anopheles cinereus", "vector_status": "Minor / local vector (highland)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Pale, greyish body", "Ethiopian / East African highland distribution"],
         "notes": "Cool highland species (notably the Ethiopian highlands). Pale; confirm with full couplet key."},
        {"id": 26, "name": "Anopheles carnevalei", "vector_status": "Secondary vector (Central Africa)",
         "molecular_id_required": True, "group_complex": "An. nili group",
         "field_markers": ["Standard nili-group features"], "notes": "Nili-group member; field-inseparable from An. nili — PCR required."},
        {"id": 27, "name": "Anopheles ovengensis", "vector_status": "Secondary vector (Central Africa)",
         "molecular_id_required": True, "group_complex": "An. nili group",
         "field_markers": ["Standard nili-group features"], "notes": "Nili-group member; PCR required to separate from An. nili."},
        {"id": 28, "name": "Anopheles somalicus", "vector_status": "Non-vector / minor",
         "molecular_id_required": True, "group_complex": "An. nili group",
         "field_markers": ["Standard nili-group features"], "notes": "Nili-group member; PCR required."},
        {"id": 29, "name": "Anopheles vaneedeni", "vector_status": "Secondary vector",
         "molecular_id_required": True, "group_complex": "An. funestus group",
         "field_markers": ["Standard funestus-group features"], "notes": "Funestus-group member; competent in the lab. Field-inseparable — PCR required."},
        {"id": 30, "name": "Anopheles parensis", "vector_status": "Non-vector",
         "molecular_id_required": True, "group_complex": "An. funestus group",
         "field_markers": ["Standard funestus-group features"], "notes": "Funestus-group non-vector; PCR required."},
        {"id": 31, "name": "Anopheles rivulorum-like", "vector_status": "Minor / uncertain vector",
         "molecular_id_required": True, "group_complex": "An. funestus group",
         "field_markers": ["Standard funestus-group features"], "notes": "Undescribed funestus-group taxon resolved only by molecular assay."},
        {"id": 32, "name": "Anopheles paludis", "vector_status": "Secondary vector (Central Africa)",
         "molecular_id_required": False, "group_complex": "An. coustani group",
         "field_markers": ["Coustani-group profile", "Forest / swamp habitats"], "notes": "Coustani-group member; log as coustani-group in routine surveys."},
        {"id": 33, "name": "Anopheles tenebrosus", "vector_status": "Minor / local vector",
         "molecular_id_required": False, "group_complex": "An. coustani group",
         "field_markers": ["Coustani-group profile"], "notes": "Coustani-group member; field-inseparable from coustani — record as group."},
        {"id": 34, "name": "Anopheles marshallii", "vector_status": "Minor / local vector",
         "molecular_id_required": True, "group_complex": "An. marshallii group",
         "field_markers": ["Spotted wings", "Forest / montane"], "notes": "Nominotypical marshallii-group member; group is a species-rich cryptic assemblage — PCR/keys required."},
        {"id": 35, "name": "Anopheles hancocki", "vector_status": "Minor / local vector",
         "molecular_id_required": True, "group_complex": "An. marshallii group",
         "field_markers": ["Marshallii-group profile"], "notes": "Marshallii-group member; molecular confirmation advised."},
        {"id": 36, "name": "Anopheles longipalpis", "vector_status": "Non-vector / minor",
         "molecular_id_required": True, "group_complex": "An. marshallii group",
         "field_markers": ["Conspicuously long palps", "Marshallii-group profile"],
         "notes": "Marshallii-group member with notably long palps (the 'type C' form); still resolved to group without molecular work."},
        {"id": 37, "name": "Anopheles amharicus", "vector_status": "Non-vector (zoophilic)",
         "molecular_id_required": True, "group_complex": "An. gambiae complex",
         "field_markers": ["Standard gambiae-complex features", "Ethiopian highland, zoophilic"],
         "notes": "Gambiae-complex member (formerly An. quadriannulatus species B). Morphologically identical to the complex — PCR mandatory."}
    ],
    "Culex": [
        {
            "id": 1,
            "name": "Culex quinquefasciatus",
            "vector_status": "Lymphatic filariasis, West Nile, RVF vector",
            "molecular_id_required": True,
            "group_complex": "Culex pipiens complex",
            "field_markers": ["Proboscis without pale median band", "Tarsi entirely dark", "Dominant urban nuisance"],
            "notes": "Dominant urban/peri-urban vector. Male genitalia dissection or molecular testing (COI barcoding) is required to resolve complex members."
        },
        {
            "id": 2,
            "name": "Culex pipiens",
            "vector_status": "West Nile virus vector",
            "molecular_id_required": True,
            "group_complex": "Culex pipiens complex",
            "field_markers": ["Proboscis without pale median band", "Overlaps/hybridizes with quinquefasciatus"],
            "notes": "Pipiens complex member. Overlaps and hybridizes extensively in specific zones of North and East Africa; requires molecular confirmation."
        },
        {
            "id": 3,
            "name": "Culex antennatus",
            "vector_status": "Rift Valley Fever vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Pale-banded tarsi", "Irrigated/flooded habitat associations"],
            "notes": "Common across major agricultural schemes and flood zones; easily tracked via distinct leg banding sequences."
        },
        {
            "id": 4,
            "name": "Culex poicilipes",
            "vector_status": "Rift Valley Fever, WNV vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Legs with distinct pale rings ('variegated feet')"],
            "notes": "Savanna floodplain breeder playing an active amplification role during Sahelian RVF outbreaks."
        },
        {
            "id": 5,
            "name": "Culex perfuscus",
            "vector_status": "Minor arbovirus vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Forest-associated distribution", "Dark, relatively unbanded legs"],
            "notes": "Separated cleanly from antennatus and poicilipes by the complete lack of distinct tarsal pale rings."
        },
        {
            "id": 6,
            "name": "Culex univittatus",
            "vector_status": "West Nile virus vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Pale scutal stripe ('single-striped' marker)"],
            "notes": "Savanna and grassland species showing high affinity for open sunny aquatic configurations."
        },
        {
            "id": 7,
            "name": "Culex neavei",
            "vector_status": "WNV, Sindbis vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Resembles univittatus scutum lines"],
            "notes": "Morphologically mirrors univittatus closely; final separation depends on precise wing and leg scale arrangement couplets."
        },
        {
            "id": 8,
            "name": "Culex theileri",
            "vector_status": "WNV vector (secondary)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Pale, sandy-colored body scaling", "Cattle-associated habitats (hoof prints)"],
            "notes": "Commonly encountered across arid and semi-arid landscapes where livestock production dominates."
        },
        {
            "id": 9,
            "name": "Culex tritaeniorhynchus",
            "vector_status": "Japanese encephalitis vector (where JEV occurs)",
            "molecular_id_required": True,
            "group_complex": "Vishnui Subgroup",
            "field_markers": ["Three pale longitudinal bands on a dark proboscis"],
            "notes": "The triple-banded proboscis is highly diagnostic of the subgroup, but species resolution inside the cluster demands molecular work."
        },
        {
            "id": 10,
            "name": "Culex duttoni",
            "vector_status": "Nuisance/minor vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Small, dark body architecture", "Domestic container breeding traits"],
            "notes": "Ubiquitous container breeder frequently collected in close proximity to urban and peri-urban human habitations."
        },
        {
            "id": 11,
            "name": "Culex decens",
            "vector_status": "Minor/nuisance vector",
            "molecular_id_required": False,
            "group_complex": "Cx. decens group",
            "field_markers": ["Forest-margin distribution", "Nondescript uniform brown scaling"],
            "notes": "Standard practice allows recording specimens as generic decens-group during routine surveillance pipelines."
        },
        {
            "id": 12,
            "name": "Culex nebulosus",
            "vector_status": "Minor vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["'Cloudy'-winged membrane scaling hints"],
            "notes": "Displays a unique scale density disparity across the wing membrane that produces a cloudy macroscopic appearance."
        },
        {
            "id": 13,
            "name": "Culex simpsoni",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Container / tree-hole breeding traits", "Nondescript brown morphology"],
            "notes": "Relies entirely on dichotomous structural key verification due to lack of distinct field-visible color bands."
        },
        {
            "id": 14,
            "name": "Culex cinereus",
            "vector_status": "Minor/nuisance vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Ashy-grey body scaling profile"],
            "notes": "A widespread generalist breeder displaying muted grey scale structures across the thorax and abdominal segments."
        },
        {
            "id": 15,
            "name": "Culex ethiopicus",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["East African highland distribution"],
            "notes": "Principally localized within high-altitude configurations; demands targeted laboratory genital dissections for validation."
        },
        {
            "id": 16,
            "name": "Culex rubinotus",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Reddish scutal markings"],
            "notes": "The distinctive reddish tint across the scutum provides a helpful field clue, though full validation needs standard couplet lines."
        },
        {
            "id": 17,
            "name": "Culex weschei",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["West/Central African forest distribution"],
            "notes": "Sylvatic species rarely differentiated in field contexts without rigorous optical key tracking."
        },
        {
            "id": 18,
            "name": "Culex zombaensis",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Swamp-associated breeding bionomics"],
            "notes": "Geographically associated with East/Southern African river basins and permanent swamp ecosystems."
        },
        {
            "id": 19,
            "name": "Culex bitaeniorhynchus",
            "vector_status": "Minor arbovirus vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Proboscis features exactly two pale bands"],
            "notes": "Highly visible name-diagnostic field marker distinguishing it cleanly from the three-banded tritaeniorhynchus matrix."
        },
        {
            "id": 20,
            "name": "Culex tigripes",
            "vector_status": "NOT A VECTOR — Obligate Predatory Larva",
            "molecular_id_required": False,
            "biocontrol_indicator": True,
            "group_complex": "None",
            "field_markers": ["Distinctive striped adult legs", "Large, robust body", "Striking tiger larval bands"],
            "notes": "🎉 BIOLOGICAL CONTROL INDICATOR: Adults are completely harmless. The highly recognizable 'tiger' larvae actively consume vector larvae. Flag immediately as a positive ecological balancer."
        },
        # ── Coastal, highland and decens-group Culex ──
        {"id": 21, "name": "Culex thalassius", "vector_status": "WNV vector (coastal)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Pale scutal stripe", "Coastal saline / brackish habitats"],
         "notes": "Salt-tolerant coastal relative of the univittatus group; brackish pools and estuarine margins."},
        {"id": 22, "name": "Culex sitiens", "vector_status": "Arbovirus vector (coastal)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Pale-banded proboscis and tarsi", "Coastal / estuarine breeder"],
         "notes": "Estuarine, salt-tolerant species of the East African and Indian-Ocean coasts."},
        {"id": 23, "name": "Culex annulioris", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Distinctly banded legs", "Forest / swamp margins"],
         "notes": "Forest and swamp species with conspicuously ringed legs."},
        {"id": 24, "name": "Culex guiarti", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "Cx. decens group",
         "field_markers": ["Decens-group profile", "Nondescript brown scaling"],
         "notes": "Decens-group member; log as decens-group in routine surveillance."},
        {"id": 25, "name": "Culex trifilatus", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "Cx. decens group",
         "field_markers": ["Decens-group profile"], "notes": "Decens-group member; field-inseparable from Cx. decens."},
        {"id": 26, "name": "Culex invidiosus", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "Cx. decens group",
         "field_markers": ["Decens-group profile"], "notes": "Decens-group member; record as group."},
        {"id": 27, "name": "Culex nakuruensis", "vector_status": "Minor / local vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["East African highland distribution"], "notes": "High-altitude species (Kenyan highlands); genital dissection for validation."},
        {"id": 28, "name": "Culex vansomereni", "vector_status": "Minor / local vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Highland forest distribution"], "notes": "East African montane-forest species."},
        {"id": 29, "name": "Culex grahamii", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Very small", "Dark brown, unremarkable scaling"],
         "notes": "Tiny, widespread ground-pool breeder; easily overlooked, low vector significance."},
        {"id": 30, "name": "Culex horridus", "vector_status": "Minor / nuisance vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Forest distribution", "Dark legs"], "notes": "Forest species; requires optical key tracking."}
    ],
    "Aedes": [
        {
            "id": 1,
            "name": "Aedes aegypti",
            "vector_status": "Dengue, Zika, Chikungunya, Yellow Fever vector",
            "molecular_id_required": False,
            "group_complex": "None (Two behavioral forms)",
            "field_markers": ["Silvery-white lyre-shaped pattern on dark scutum", "White-banded tarsi"],
            "notes": "Highly recognizable field profile. Splits into domestic form (Ae. aegypti aegypti: urban, pale) and sylvatic form (Ae. aegypti formosus: darker, forest) via scale density."
        },
        {
            "id": 2,
            "name": "Aedes albopictus",
            "vector_status": "Dengue, Chikungunya vector",
            "molecular_id_required": False,
            "biosecurity_alert": True,
            "group_complex": "Invasive Species",
            "field_markers": ["Single, straight silver-white dorsal stripe down the center of scutum"],
            "notes": "⚠️ CRITICAL INVASIVE TARGET: Genuinely diagnostic field character (distinguishes it from aegypti's lyre shape). Expanding across West/Central African forest and urban fringes."
        },
        {
            "id": 3,
            "name": "Aedes africanus",
            "vector_status": "Yellow fever vector (sylvatic cycle)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Forest canopy bionomics", "Scutum with narrow pale median stripe", "Hindtarsi with broad basal white bands"],
            "notes": "A premier sylvatic Yellow Fever vector responsible for canopy transmission cycles in heavy forest zones."
        },
        {
            "id": 4,
            "name": "Aedes simpsoni (s.l.)",
            "vector_status": "Yellow fever vector (sylvatic/intermediate)",
            "molecular_id_required": True,
            "group_complex": "Ae. simpsoni complex",
            "field_markers": ["Plant-axil breeder (banana/cocoyam)", "Broad pale tarsal bands"],
            "notes": "Cryptic species complex requiring molecular assays. Heavily tracked via targeted searching of leaf axils and structural breeding habitats."
        },
        {
            "id": 5,
            "name": "Aedes vittatus",
            "vector_status": "Dengue (secondary), Chikungunya vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Silver/gold scutal pattern with pale longitudinal band", "Curved lateral flanking lines", "Rock-pool breeder"],
            "notes": "Highly distinctive rock-pool breeding vector exhibiting a complex but stable metallic scutal ornamentation sequence."
        },
        {
            "id": 6,
            "name": "Aedes furcifer",
            "vector_status": "Yellow fever, dengue vector (sylvatic)",
            "molecular_id_required": False,
            "group_complex": "Ae. furcifer-taylori group",
            "field_markers": ["Broad white tarsal bands", "Forest canopy distribution"],
            "notes": "Key driver of sylvatic viral amplification. Fine separation from taylori requires laboratory verification of diagnostic couplets."
        },
        {
            "id": 7,
            "name": "Aedes taylori",
            "vector_status": "Yellow fever vector (sylvatic)",
            "molecular_id_required": False,
            "group_complex": "Ae. furcifer-taylori group",
            "field_markers": ["Inseparable from furcifer under field constraints"],
            "notes": "Belongs to the furcifer-taylori cluster. Log as a collective group entry during field sorting workflows."
        },
        {
            "id": 8,
            "name": "Aedes luteocephalus",
            "vector_status": "Yellow fever, dengue vector (sylvatic)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Distinct pale / yellowish head scaling"],
            "notes": "The yellow-headed scale configuration offers a highly useful macro optical cue for identifying this West African forest vector."
        },
        {
            "id": 9,
            "name": "Aedes metallicus",
            "vector_status": "Minor arbovirus vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Striking metallic blue-black scutal sheen", "Complete absence of pale scutal stripes"],
            "notes": "Visually brilliant specimen easily sorted by its unbroken deep metallic blue-black thoracic coloration."
        },
        {
            "id": 10,
            "name": "Aedes unilineatus",
            "vector_status": "Minor vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Single fine pale scutal line"],
            "notes": "Possesses a single line, but it is noticeably smaller and duller than the bold stripe seen on albopictus. Confirm via key."
        },
        {
            "id": 11,
            "name": "Aedes dentatus",
            "vector_status": "Minor/nuisance vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Savanna floodwater breeding traits", "Pale tarsal banding", "Nondescript scutum"],
            "notes": "A widespread seasonal savanna species tracking standard temporary surface flood pools."
        },
        {
            "id": 12,
            "name": "Aedes circumluteolus",
            "vector_status": "Rift Valley Fever (secondary), Bunyamwera vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Temporary pan / floodwater pool habitats"],
            "notes": "Involved in localized RVF transmission cycles across Southern and East African savanna pan structures."
        },
        {
            "id": 13,
            "name": "Aedes mcintoshi",
            "vector_status": "Rift Valley Fever (primary floodwater vector)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Desiccation-resistant soil egg bionomics", "Mass floodwater dambo hatches"],
            "notes": "🚨 HIGH PRIORITY EPIDEMIC VECTOR: Eggs remain dormant in soil for years, hatching en masse after heavy rains to trigger catastrophic RVF outbreaks."
        },
        {
            "id": 14,
            "name": "Aedes ochraceus",
            "vector_status": "Rift Valley Fever vector (secondary)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Floodwater / dambo breeding habitats"],
            "notes": "Co-occurs predictably alongside mcintoshi in seasonal dambo systems during extreme rainfall events."
        },
        {
            "id": 15,
            "name": "Aedes sudanensis",
            "vector_status": "Minor/local vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Sahelian floodwater distribution profile"],
            "notes": "Adapted to hyper-seasonal Sahelian channels; demands explicit couplet confirmation."
        },
        {
            "id": 16,
            "name": "Aedes cumminsii",
            "vector_status": "Minor/nuisance vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Dull brown body", "Faint abdominal banding arrays"],
            "notes": "Widespread savanna generalist species driving localized nuisance biting spikes following rain events."
        },
        {
            "id": 17,
            "name": "Aedes apicoargenteus",
            "vector_status": "Yellow fever vector (minor sylvatic)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Silver scaling concentrated tightly at wing and leg apex"],
            "notes": "Apical silver scaling clusters provide an immediate screening cue under stereo magnification."
        },
        {
            "id": 18,
            "name": "Aedes opok",
            "vector_status": "Yellow fever vector (sylvatic)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Central African forest block localization"],
            "notes": "Morphologically mirrors the africanus/luteocephalus assembly. Geographical sorting is the most practical initial differentiator."
        },
        {
            "id": 19,
            "name": "Aedes neoafricanus",
            "vector_status": "Minor sylvatic vector",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Close structural relative of africanus"],
            "notes": "Requires fine laboratory-level reproductive tract dissections to safely isolate from true africanus in sympatric zones."
        },
        {
            "id": 20,
            "name": "Aedes argenteopunctatus",
            "vector_status": "Rift Valley Fever vector (secondary)",
            "molecular_id_required": False,
            "group_complex": "None",
            "field_markers": ["Distinct silver-spotted scutum pattern"],
            "notes": "Easily identified by its distinctive silver thoracic spotting; tied closely with floodwater systems in RVF-endemic zones."
        },
        # ── Floodwater (RVF), coastal and simpsoni-/caballus-group Aedes ──
        {"id": 21, "name": "Aedes vexans", "vector_status": "RVF (secondary), arbovirus vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Narrow pale tarsal bands", "Floodwater breeder", "Nondescript scutum"],
         "notes": "Near-cosmopolitan floodwater species; large seasonal broods can amplify RVF and other arboviruses."},
        {"id": 22, "name": "Aedes caballus", "vector_status": "RVF vector (Southern Africa)",
         "molecular_id_required": True, "group_complex": "Ae. caballus-juppi pair",
         "field_markers": ["Floodwater / pan breeder", "Pale-banded legs"],
         "notes": "Southern African floodwater RVF vector; sibling of Ae. juppi — reliable separation needs molecular/genitalic work."},
        {"id": 23, "name": "Aedes juppi", "vector_status": "RVF vector (Southern Africa)",
         "molecular_id_required": True, "group_complex": "Ae. caballus-juppi pair",
         "field_markers": ["Floodwater / pan breeder"], "notes": "Cryptic sibling of Ae. caballus; resolve the pair molecularly."},
        {"id": 24, "name": "Aedes fowleri", "vector_status": "RVF vector (secondary)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Floodwater breeder", "Pale-banded legs"], "notes": "Floodwater species implicated in RVF amplification in arid zones."},
        {"id": 25, "name": "Aedes dalzieli", "vector_status": "Arbovirus vector (sylvatic/savanna)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Savanna floodwater breeder", "Pale-banded tarsi"],
         "notes": "West African savanna species carrying several sylvatic arboviruses."},
        {"id": 26, "name": "Aedes pembaensis", "vector_status": "RVF vector (coastal)",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Coastal crab-hole breeder", "Broad pale tarsal bands"],
         "notes": "Coastal East African species breeding in crab holes; a recognised RVF vector in littoral zones."},
        {"id": 27, "name": "Aedes bromeliae", "vector_status": "Yellow fever vector (intermediate cycle)",
         "molecular_id_required": True, "group_complex": "Ae. simpsoni complex",
         "field_markers": ["Plant-axil breeder", "Simpsoni-complex profile"],
         "notes": "The anthropophilic simpsoni-complex member — the key YF bridge vector. Morphologically cryptic within the complex — PCR required."},
        {"id": 28, "name": "Aedes lilii", "vector_status": "Minor sylvatic vector",
         "molecular_id_required": True, "group_complex": "Ae. simpsoni complex",
         "field_markers": ["Plant-axil breeder", "Simpsoni-complex profile"],
         "notes": "Simpsoni-complex member; not anthropophilic. Resolve the complex molecularly."},
        {"id": 29, "name": "Aedes hirsutus", "vector_status": "Minor arbovirus vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Pale-banded legs", "Savanna floodwater"], "notes": "Savanna floodwater species of minor arboviral significance."},
        {"id": 30, "name": "Aedes tarsalis", "vector_status": "Minor sylvatic vector",
         "molecular_id_required": False, "group_complex": "None",
         "field_markers": ["Forest distribution", "Pale-banded tarsi"], "notes": "Forest species; confirm via structural key."}
    ]
}

# ==========================================================================
#  CRYPTIC SPECIES-COMPLEX MEMBERSHIP — SINGLE SOURCE OF TRUTH
# --------------------------------------------------------------------------
#  Members of these complexes/groups are morphologically inseparable, so a
#  field/image identification can only ever name the complex, never a member
#  species. This one table is the authoritative membership list for the whole
#  app: the deep-key engine caps results at these complexes, and PCR accuracy
#  scoring (utils/pcr_and_accuracy.py) derives its "credit a complex prediction
#  against any confirmed member" logic from here — so the two can never drift.
#
#  `trigger` is the lowercase word that appears in a complex/group label
#  (e.g. "An. gambiae complex" -> "gambiae"); `members` are lowercase species
#  epithets, a curated SUPERSET of the field catalog (PCR can confirm a member
#  that never appears in routine field screening, e.g. An. bwambae).
# ==========================================================================
SPECIES_COMPLEXES = {
    "An. gambiae complex":   {"genus": "Anopheles", "trigger": "gambiae",
                              "members": ["gambiae", "coluzzii", "arabiensis", "merus",
                                          "melas", "quadriannulatus", "amharicus", "bwambae"]},
    "An. funestus group":    {"genus": "Anopheles", "trigger": "funestus",
                              "members": ["funestus", "rivulorum", "rivulorum-like",
                                          "parensis", "leesoni", "vaneedeni"]},
    "An. coustani group":    {"genus": "Anopheles", "trigger": "coustani",
                              "members": ["coustani", "ziemanni", "paludis",
                                          "tenebrosus", "namibiensis"]},
    "An. nili group":        {"genus": "Anopheles", "trigger": "nili",
                              "members": ["nili", "ovengensis", "somalicus", "carnevalei"]},
    "An. moucheti group":    {"genus": "Anopheles", "trigger": "moucheti",
                              "members": ["moucheti", "nigeriensis", "bervoetsi"]},
    "An. marshallii group":  {"genus": "Anopheles", "trigger": "marshallii",
                              "members": ["marshallii", "demeilloni", "hancocki", "longipalpis"]},
    "Culex pipiens complex": {"genus": "Culex", "trigger": "pipiens",
                              "members": ["pipiens", "quinquefasciatus", "molestus"]},
    "Vishnui Subgroup":      {"genus": "Culex", "trigger": "vishnui",
                              "members": ["tritaeniorhynchus", "vishnui", "pseudovishnui"]},
    "Cx. decens group":      {"genus": "Culex", "trigger": "decens",
                              "members": ["decens", "guiarti", "trifilatus", "invidiosus"]},
    "Aedes simpsoni complex": {"genus": "Aedes", "trigger": "simpsoni",
                               "members": ["simpsoni", "bromeliae", "lilii"]},
    "Ae. furcifer-taylori group": {"genus": "Aedes", "trigger": "furcifer",
                                   "members": ["furcifer", "taylori"]},
    "Ae. caballus-juppi pair": {"genus": "Aedes", "trigger": "caballus",
                                "members": ["caballus", "juppi"]},
}


def complex_membership_by_trigger() -> dict:
    """trigger-word -> member epithets, for matching against free-text labels.

    Consumers (e.g. PCR accuracy scoring) that only have a taxon *string* use
    this to decide whether a complex/group prediction covers a confirmed
    species, without re-hardcoding the membership lists."""
    return {c["trigger"]: list(c["members"]) for c in SPECIES_COMPLEXES.values()}


def evaluate_genus_triage(input_features: dict) -> dict:
    """
    Scores adult morphological screening entries against standard genus parameters.
    Returns the top matching genus accompanied by a deterministic diagnostic index.
    """
    scores = {"Anopheles": 0, "Culex": 0, "Aedes": 0}
    total_matchable = len(input_features)

    if total_matchable == 0:
        return {"genus": "Undetermined", "confidence": 0, "reason": "No features provided."}

    for genus, traits in GENUS_TRIAGE_MATRIX.items():
        for key, value in input_features.items():
            if traits.get(key) == value:
                scores[genus] += 1

    sorted_genus = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    top_genus, top_score = sorted_genus[0]

    confidence = int((top_score / total_matchable) * 100) if top_score > 0 else 0

    if confidence < 50:
        return {
            "genus": "Undetermined",
            "confidence": confidence,
            "reason": "Insufficient character correlation to guarantee diagnostic separation."
        }

    return {
        "genus": top_genus,
        "confidence": confidence,
        "reason": f"Matches {top_score} of {total_matchable} checked macro-characters cleanly."
    }

def evaluate_larval_triage(posture: str, siphon_length: str, setal_tufts: str) -> dict:
    """
    Resolves immature specimens directly to Genus level based on high-confidence
    4th-instar macro structural characters outlined by Service (1990).
    """
    # Normalize inputs (setal_tufts not used in this triage tier)
    p, s, _ = posture.lower(), siphon_length.lower(), setal_tufts.lower()

    if "parallel" in p or "absent" in s or "none" in s:
        return {
            "resolved_genus": "Anopheles",
            "confidence_tier": "High Confidence Genus Triage",
            "siphon_status": "Absent. Respiratory spiracular plate rests flush with surface film.",
            "posture_status": "Floats completely parallel/horizontal to surface.",
            "notes": "Anopheline signature verified. Cryptic complexes make species-level calls invalid on wild field-caught larvae without larval setal slide counts or molecular assays."
        }
    elif "angle" in p and "long" in s:
        return {
            "resolved_genus": "Culex",
            "confidence_tier": "High Confidence Genus Triage",
            "siphon_status": "Present. Characterized as long, slender, with multiple subventral setal tufts.",
            "posture_status": "Hangs suspended head-downward at a clear angle from surface.",
            "notes": "Culicine signature verified. Encompasses major vectors of Filariasis and WNV. Note: If the larva is uniquely large, striped, and lacks pathogenetic risks, evaluate for the predator Culex tigripes (biocontrol indicator)."
        }
    elif "angle" in p and "short" in s:
        return {
            "resolved_genus": "Aedes",
            "confidence_tier": "High Confidence Genus Triage",
            "siphon_status": "Present. Shorter, stouter respiratory siphon containing a single pair of setal tufts (the pecten).",
            "posture_status": "Hangs downward at an acute or near-vertical line from surface film.",
            "notes": "Aedine signature verified. Major vectors for Dengue, Zika, and Yellow Fever. Larvae frequently appear within temporary container environments or floodwater dambos."
        }

    return {
        "resolved_genus": "Undetermined Culicinae",
        "confidence_tier": "Inconclusive",
        "siphon_status": "Ambiguous trait layout.",
        "posture_status": "Unknown orientation.",
        "notes": "Traits do not line up cleanly with standard 4th-instar keys. Re-verify segment arrays under magnification."
    }

def search_species_reference(genus: str, observed_markers: list[str]) -> list[dict]:
    """
    Scans the complete dictionary of 60 species profiles for a given genus,
    scoring match strength based on overlapping field markers and notes keywords.
    """
    if genus not in SPECIES_CATALOG:
        return []

    matched_candidates = []
    normalized_markers = [m.lower() for m in observed_markers]

    for species in SPECIES_CATALOG[genus]:
        score = 0
        # Check explicit field markers
        for marker in species["field_markers"]:
            if any(nm in marker.lower() for nm in normalized_markers):
                score += 2

        # Check notes text for auxiliary keywords
        for nm in normalized_markers:
            if nm in species["notes"].lower():
                score += 1

        if score > 0 or not observed_markers:
            matched_candidates.append({
                "species_name": species["name"],
                "vector_status": species["vector_status"],
                "molecular_id_required": species.get("molecular_id_required", False),
                "biosecurity_alert": species.get("biosecurity_alert", False),
                "biocontrol_indicator": species.get("biocontrol_indicator", False),
                "group_complex": species["group_complex"],
                "field_diagnostic_notes": species["notes"],
                "match_score": score
            })

    # Return sorted by match relevance
    return sorted(matched_candidates, key=lambda x: x["match_score"], reverse=True)
# --- BACKWARD COMPATIBILITY WRAPPERS FOR DIAGNOSTICS COMPONENT ---

def match_adult_morphology(input_features: dict) -> dict:
    """
    Legacy wrapper matching components/diagnostics.py expectations.
    Bridges old UI inputs with the new genus triage and 60-species reference matrix.
    """
    # 1. Run the new structural genus scoring engine
    triage_result = evaluate_genus_triage(input_features)
    detected_genus = triage_result.get("genus", "Undetermined")

    # 2. Extract observed values to parse out potential species candidates
    # Convert feature values (e.g., 'Long', 'Silvery-white lyre-shaped pattern...') into a query list
    observed_markers = [str(val) for val in input_features.values() if val]

    candidates = []
    if detected_genus != "Undetermined":
        candidates = search_species_reference(detected_genus, observed_markers)

    # 3. Build a comprehensive response object tailored for Streamlit UI parsing
    top_candidate = candidates[0] if candidates else None
    resolved_name = top_candidate["species_name"] if top_candidate else f"{detected_genus} spp."
    if detected_genus == "Undetermined":
        resolved_name = "Culicinae / Anophelinae Undetermined"

    return {
        "genus": detected_genus,
        "confidence": triage_result.get("confidence", 0),
        "reason": triage_result.get("reason", ""),
        "resolved_taxonomic_name": resolved_name,
        "group_complex": top_candidate["group_complex"] if top_candidate else "N/A",
        "vector_status": top_candidate["vector_status"] if top_candidate else "Unknown",
        "molecular_id_required": top_candidate["molecular_id_required"] if top_candidate else False,
        "biosecurity_alert": top_candidate["biosecurity_alert"] if top_candidate else False,
        "biocontrol_indicator": top_candidate["biocontrol_indicator"] if top_candidate else False,
        "notes": top_candidate["field_diagnostic_notes"] if top_candidate else triage_result.get("reason", ""),
        "candidates": candidates
    }

def match_larval_morphology(*args, **kwargs):
    """
    Flexible wrapper that safely catches both a single dictionary argument
    and unpacked dictionary keyword arguments (**kwargs) from the UI.
    Sanitizes None values into safe strings to prevent crash downstream.
    """
    # 1. Determine if the UI passed a single dictionary or unpacked keyword arguments
    if args and isinstance(args[0], dict):
        payload = args[0]
    else:
        payload = kwargs

    # 2. Extract variables safely and provide default fallback strings ("unknown")
    # This prevents NoneType errors when .lower() is executed inside evaluate_larval_triage
    siphon_length = payload.get("siphon_length") or "unknown"
    setal_tufts = payload.get("setal_tufts") or "unknown"
    posture = payload.get("posture") or payload.get("resting_posture") or "unknown"

    # 3. Route clean string variables directly to your 4th-instar larval triage mechanics
    triage = evaluate_larval_triage(posture, siphon_length, setal_tufts)

    # 4. Normalize dictionary keys to support older UI lookups if needed
    triage["genus"] = triage.get("resolved_genus", "Undetermined")
    triage["resolved_taxonomic_name"] = triage.get("resolved_genus", "Undetermined Genus")

    return triage


# ==========================================================================
#  ANOPHELES DEEP-KEY IDENTIFICATION ENGINE
# --------------------------------------------------------------------------
#  Adult-female Anopheles are the malaria-relevant genus, so they get a
#  dedicated, character-resolved engine. Character states and weights are a
#  faithful (if simplified) reduction of the standard Afrotropical adult keys
#  — Gillies & Coetzee (1987), Coetzee (2020). Weights encode how much
#  discriminating power a character carries (5 = strongly diagnostic).
# ==========================================================================

ANOPHELES_CHARACTERS = {
    "proboscis": {
        "label": "Proboscis coloration",
        "weight": 3,
        "states": {
            "dark_uniform": "Uniformly dark along its length",
            "pale_tipped": "Apical portion distinctly pale / pale-scaled",
        },
    },
    "palp_pale_bands": {
        "label": "Maxillary palp — number of pale bands",
        "weight": 3,
        "states": {
            "three_bands": "Three pale bands (typical gambiae / funestus pattern)",
            "four_bands": "Four pale bands",
            "faint_or_none": "Pale bands faint, speckled or effectively absent",
        },
    },
    "palp_apical_band": {
        "label": "Palp apical (tip) pale band",
        "weight": 2,
        "states": {
            "broad_pale_apical": "Broad / long apical pale band",
            "narrow_pale_apical": "Narrow apical pale band",
            "speckled_palp": "Palp irregularly speckled / dark-spotted",
        },
    },
    "vein6_dark_spots": {
        "label": "Wing vein 6 (1A) — dark spots",
        "weight": 4,
        "states": {
            "two_spots": "Two dark spots",
            "one_spot": "One dark spot",
            "none": "No distinct dark spots",
        },
    },
    "costa_wing_spots": {
        "label": "Wing costa — pale spotting",
        "weight": 2,
        "states": {
            "many_pale_spots": "Several distinct pale spots (strongly patterned costa)",
            "few_pale_spots": "Mostly dark with a few pale interruptions",
            "largely_pale": "Costa largely pale / lightly scaled",
        },
    },
    "hind_tarsi": {
        "label": "Hind tarsi — pale banding",
        "weight": 4,
        "states": {
            "broad_white_bands": "Broad, conspicuous white bands",
            "narrow_pale_bands": "Narrow pale rings at the joints",
            "dark_no_bands": "Entirely dark, no pale bands",
        },
    },
    "hind_tarsomere5": {
        "label": "Hind tarsomere 5 (last segment)",
        "weight": 3,
        "states": {
            "all_pale": "Entirely pale / white",
            "dark": "Dark",
        },
    },
    "leg_speckling": {
        "label": "Femora & tibiae speckling",
        "weight": 3,
        "states": {
            "speckled": "Distinctly speckled with pale specks",
            "unspeckled": "Not speckled (uniformly scaled)",
        },
    },
    "wing_fringe_spots": {
        "label": "Wing fringe pale spots",
        "weight": 2,
        "states": {
            "present": "Distinct pale fringe spots present",
            "faint_absent": "Faint or absent",
        },
    },
    "body_size": {
        "label": "Overall body size",
        "weight": 2,
        "states": {
            "large": "Large / robust",
            "medium": "Medium",
            "small": "Small",
        },
    },
    # ── Named costa pale/dark spots (Gillies & Coetzee 1987 terminology),
    #    base → apex, plus maxillary-palp length. Field/stereo-visible subset. ──
    "humeral_pale_spot": {
        "label": "Costa — humeral pale spot (wing base)", "weight": 2,
        "states": {"present": "Present", "absent": "Absent"},
    },
    "presector_pale_spot": {
        "label": "Costa — presector pale spot", "weight": 2,
        "states": {"present": "Present", "absent": "Absent"},
    },
    "accessory_sector_pale_spot": {
        "label": "Costa — accessory sector pale spot", "weight": 3,
        "states": {"present": "Present", "absent": "Absent"},
    },
    "subcostal_pale_spot": {
        "label": "Costa — subcostal pale spot", "weight": 2,
        "states": {"present": "Present", "absent": "Absent"},
    },
    "preapical_dark_spot": {
        "label": "Costa — preapical dark spot", "weight": 2,
        "states": {"present": "Present", "absent": "Absent"},
    },
    "palp_length": {
        "label": "Maxillary palp length (relative to proboscis)", "weight": 2,
        "states": {"normal": "About as long as proboscis", "long": "Conspicuously long / slender"},
    },
}

# Shared state templates for cryptic taxa whose members are structurally identical.
# The named costa pale/dark-spot states are backfilled here (only confident,
# defensible directions) so recording those characters actually discriminates.
_GAMBIAE_COMPLEX_STATES = {
    "proboscis": "dark_uniform",
    "palp_pale_bands": "three_bands",
    "palp_apical_band": "broad_pale_apical",
    "vein6_dark_spots": "two_spots",
    "costa_wing_spots": "few_pale_spots",
    "hind_tarsi": "narrow_pale_bands",
    "hind_tarsomere5": "dark",
    "leg_speckling": "unspeckled",
    "wing_fringe_spots": "present",
    "body_size": "medium",
    "humeral_pale_spot": "absent",
    "presector_pale_spot": "present",
    "accessory_sector_pale_spot": "absent",
    "subcostal_pale_spot": "present",
    "preapical_dark_spot": "present",
    "palp_length": "normal",
}
_FUNESTUS_GROUP_STATES = {
    "proboscis": "dark_uniform",
    "palp_pale_bands": "three_bands",
    "palp_apical_band": "broad_pale_apical",
    "vein6_dark_spots": "two_spots",
    "costa_wing_spots": "many_pale_spots",
    "hind_tarsi": "dark_no_bands",   # dark hind tarsi separate funestus grp from gambiae cplx
    "hind_tarsomere5": "dark",
    "leg_speckling": "unspeckled",
    "wing_fringe_spots": "present",
    "body_size": "medium",
    "humeral_pale_spot": "present",
    "presector_pale_spot": "present",
    "accessory_sector_pale_spot": "present",
    "subcostal_pale_spot": "present",
    "preapical_dark_spot": "present",
    "palp_length": "normal",
}
_COUSTANI_GROUP_STATES = {
    "proboscis": "pale_tipped",
    "palp_pale_bands": "three_bands",
    "palp_apical_band": "narrow_pale_apical",
    "vein6_dark_spots": "two_spots",
    "hind_tarsi": "narrow_pale_bands",
    "leg_speckling": "speckled",
    "wing_fringe_spots": "present",
    "body_size": "medium",
    "presector_pale_spot": "present",
    "accessory_sector_pale_spot": "present",
    "palp_length": "normal",
}

# species_name -> structural profile. Names MUST match SPECIES_CATALOG["Anopheles"].
ANOPHELES_KEY_PROFILES = {
    # ── An. gambiae complex — morphologically inseparable (PCR only) ──
    "Anopheles gambiae (s.s.)": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["Inseparable from other complex members by morphology — PCR (Scott et al. 1993) required"],
    },
    "Anopheles coluzzii": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["Ecology (permanent/man-made water) differs, morphology does not — PCR required"],
    },
    "Anopheles arabiensis": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["More exophilic/zoophilic, but structurally identical — PCR required"],
    },
    "Anopheles merus": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["Coastal saline breeder; structurally identical — PCR required"],
    },
    "Anopheles melas": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["West African mangrove/saline breeder; structurally identical — PCR required"],
    },
    "Anopheles quadriannulatus": {
        "resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": _GAMBIAE_COMPLEX_STATES,
        "discriminators": ["Zoophilic non-vector; structurally identical — PCR required"],
    },
    # ── An. funestus group — inseparable to species in the field ──
    "Anopheles funestus (s.s.)": {
        "resolution_level": "group", "complex": "An. funestus group",
        "character_states": _FUNESTUS_GROUP_STATES,
        "discriminators": ["Entirely dark hind tarsi + long apical palp band separate the group from gambiae cplx",
                           "Species split within the group needs PCR (Koekemoer et al. 2002)"],
    },
    "Anopheles rivulorum": {
        "resolution_level": "group", "complex": "An. funestus group",
        "character_states": _FUNESTUS_GROUP_STATES,
        "discriminators": ["Field-inseparable from funestus s.s. — PCR required"],
    },
    "Anopheles leesoni": {
        "resolution_level": "group", "complex": "An. funestus group",
        "character_states": _FUNESTUS_GROUP_STATES,
        "discriminators": ["Non-vector funestus-group member — PCR required to confirm"],
    },
    # ── Distinguishable / group-level Anopheles ──
    "Anopheles nili": {
        "resolution_level": "group", "complex": "An. nili group",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "palp_apical_band": "broad_pale_apical", "vein6_dark_spots": "two_spots",
            "costa_wing_spots": "few_pale_spots", "hind_tarsi": "dark_no_bands",
            "hind_tarsomere5": "dark", "leg_speckling": "unspeckled",
            "wing_fringe_spots": "present", "body_size": "medium",
        },
        "discriminators": ["Pale spot at base of vein 6; evenly distributed fringe spots",
                           "Fast-flowing, well-oxygenated stream breeder"],
    },
    "Anopheles moucheti": {
        "resolution_level": "group", "complex": "An. moucheti group",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "vein6_dark_spots": "one_spot", "costa_wing_spots": "few_pale_spots",
            "hind_tarsi": "dark_no_bands", "hind_tarsomere5": "dark",
            "leg_speckling": "unspeckled", "wing_fringe_spots": "faint_absent",
            "body_size": "medium",
        },
        "discriminators": ["Dark, relatively unpatterned wings", "Slow riverine / floating-vegetation margins"],
    },
    "Anopheles pharoensis": {
        "resolution_level": "species", "complex": "None",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "four_bands",
            "palp_apical_band": "broad_pale_apical", "vein6_dark_spots": "two_spots",
            "costa_wing_spots": "many_pale_spots", "hind_tarsi": "broad_white_bands",
            "hind_tarsomere5": "all_pale", "leg_speckling": "speckled",
            "wing_fringe_spots": "present", "body_size": "large",
        },
        "discriminators": ["Large body + 4 palpal pale bands + speckled legs + broad pale tarsal blocks",
                           "One of the most structurally distinctive African Anopheles"],
    },
    "Anopheles squamosus": {
        "resolution_level": "species", "complex": "None",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "vein6_dark_spots": "one_spot", "costa_wing_spots": "largely_pale",
            "hind_tarsi": "narrow_pale_bands", "hind_tarsomere5": "dark",
            "leg_speckling": "unspeckled", "wing_fringe_spots": "faint_absent",
            "body_size": "medium",
        },
        "discriminators": ["Pale, lightly-scaled wings; savanna", "Separate from coustani via tarsal banding detail"],
    },
    "Anopheles coustani": {
        "resolution_level": "group", "complex": "An. coustani group",
        "character_states": _COUSTANI_GROUP_STATES,
        "discriminators": ["Pale-tipped proboscis/palps + narrow pale tarsal rings", "Treat as coustani group in routine surveys"],
    },
    "Anopheles ziemanni": {
        "resolution_level": "group", "complex": "An. coustani group",
        "character_states": _COUSTANI_GROUP_STATES,
        "discriminators": ["Field-inseparable from the coustani group; log as group"],
    },
    "Anopheles rufipes": {
        "resolution_level": "species", "complex": "None",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "vein6_dark_spots": "two_spots", "hind_tarsi": "broad_white_bands",
            "hind_tarsomere5": "all_pale", "leg_speckling": "speckled",
            "wing_fringe_spots": "present", "body_size": "medium",
        },
        "discriminators": ["Reddish-brown / pale hind tarsi ('red-footed')", "Speckled femora & tibiae"],
    },
    "Anopheles wellcomei": {
        "resolution_level": "species", "complex": "None",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "costa_wing_spots": "largely_pale", "hind_tarsi": "narrow_pale_bands",
            "leg_speckling": "unspeckled", "body_size": "small",
        },
        "discriminators": ["Small, pale Sahelian species — confirm with the full couplet key"],
    },
    "Anopheles maculipalpis": {
        "resolution_level": "species", "complex": "None",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "faint_or_none",
            "palp_apical_band": "speckled_palp", "hind_tarsi": "narrow_pale_bands",
            "leg_speckling": "speckled", "body_size": "medium",
        },
        "discriminators": ["Distinctly speckled / dark-spotted palps — a rare field-visible name-diagnostic character"],
    },
    "Anopheles demeilloni": {
        "resolution_level": "group", "complex": "An. marshallii group",
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "vein6_dark_spots": "two_spots", "hind_tarsi": "narrow_pale_bands",
            "leg_speckling": "unspeckled", "body_size": "medium",
        },
        "discriminators": ["East/Central African highland species; needs full stereomicroscope keying"],
    },
    "Anopheles stephensi": {
        "resolution_level": "species", "complex": "None (invasive)", "biosecurity_alert": True,
        "character_states": {
            "proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "palp_apical_band": "narrow_pale_apical", "vein6_dark_spots": "two_spots",
            "costa_wing_spots": "few_pale_spots", "hind_tarsi": "narrow_pale_bands",
            "hind_tarsomere5": "dark", "leg_speckling": "unspeckled",
            "wing_fringe_spots": "present", "body_size": "medium",
        },
        "discriminators": ["Container / urban breeder — invasive Asian vector",
                           "Palpal banding per Coetzee (2020) invasive-vector key; CONFIRM BY PCR"],
    },
}

# ── Extended profiles: desert/oasis & highland species (genuinely separable),
#    plus additional cryptic-group members that collapse to their group/complex
#    with molecular_id_required=True. Members share a group state template so the
#    scorer treats them as inseparable — exactly the guardrail these encode. ──
_NILI_GROUP_STATES = dict(ANOPHELES_KEY_PROFILES["Anopheles nili"]["character_states"])
_MARSHALLII_GROUP_STATES = {
    "proboscis": "dark_uniform", "palp_pale_bands": "three_bands", "vein6_dark_spots": "two_spots",
    "hind_tarsi": "narrow_pale_bands", "leg_speckling": "unspeckled", "body_size": "medium",
    "presector_pale_spot": "present", "accessory_sector_pale_spot": "present",
}

ANOPHELES_KEY_PROFILES.update({
    # ── genuinely distinguishable additions (species-level, no forced PCR) ──
    "Anopheles pretoriensis": {
        "resolution_level": "species", "complex": "None",
        "character_states": {"proboscis": "pale_tipped", "palp_pale_bands": "three_bands",
            "hind_tarsi": "narrow_pale_bands", "hind_tarsomere5": "dark", "leg_speckling": "speckled",
            "body_size": "medium", "accessory_sector_pale_spot": "present"},
        "discriminators": ["Speckled legs + pale-tipped palps, drier/rocky savanna",
                           "Separable from coustani group by tarsal & wing detail"]},
    "Anopheles sergentii": {
        "resolution_level": "species", "complex": "None",
        "character_states": {"proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "hind_tarsi": "narrow_pale_bands", "hind_tarsomere5": "dark", "leg_speckling": "unspeckled",
            "body_size": "medium", "costa_wing_spots": "few_pale_spots"},
        "discriminators": ["Saharan oasis vector — habitat is a strong contextual cue",
                           "Narrow apical tarsal pale bands"]},
    "Anopheles multicolor": {
        "resolution_level": "species", "complex": "None",
        "character_states": {"proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "hind_tarsi": "broad_white_bands", "hind_tarsomere5": "all_pale", "leg_speckling": "speckled",
            "body_size": "medium", "costa_wing_spots": "many_pale_spots"},
        "discriminators": ["Very pale, broad tarsal banding, saline oasis habitat"]},
    "Anopheles dthali": {
        "resolution_level": "species", "complex": "None",
        "character_states": {"proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "hind_tarsi": "narrow_pale_bands", "leg_speckling": "speckled", "body_size": "medium",
            "presector_pale_spot": "present"},
        "discriminators": ["Speckled legs, rocky desert wadi pools"]},
    "Anopheles cinereus": {
        "resolution_level": "species", "complex": "None",
        "character_states": {"proboscis": "dark_uniform", "palp_pale_bands": "three_bands",
            "costa_wing_spots": "largely_pale", "hind_tarsi": "narrow_pale_bands",
            "leg_speckling": "unspeckled", "body_size": "medium"},
        "discriminators": ["Pale greyish highland species (Ethiopian highlands)"]},
    # ── cryptic-group additions (collapse to group; PCR flagged) ──
    "Anopheles carnevalei": {"resolution_level": "group", "complex": "An. nili group",
        "character_states": _NILI_GROUP_STATES, "discriminators": ["Nili-group — PCR required"]},
    "Anopheles ovengensis": {"resolution_level": "group", "complex": "An. nili group",
        "character_states": _NILI_GROUP_STATES, "discriminators": ["Nili-group — PCR required"]},
    "Anopheles somalicus": {"resolution_level": "group", "complex": "An. nili group",
        "character_states": _NILI_GROUP_STATES, "discriminators": ["Nili-group — PCR required"]},
    "Anopheles vaneedeni": {"resolution_level": "group", "complex": "An. funestus group",
        "character_states": dict(_FUNESTUS_GROUP_STATES), "discriminators": ["Funestus-group — PCR required"]},
    "Anopheles parensis": {"resolution_level": "group", "complex": "An. funestus group",
        "character_states": dict(_FUNESTUS_GROUP_STATES), "discriminators": ["Funestus-group non-vector — PCR required"]},
    "Anopheles rivulorum-like": {"resolution_level": "group", "complex": "An. funestus group",
        "character_states": dict(_FUNESTUS_GROUP_STATES), "discriminators": ["Funestus-group — molecular only"]},
    "Anopheles paludis": {"resolution_level": "group", "complex": "An. coustani group",
        "character_states": dict(_COUSTANI_GROUP_STATES), "discriminators": ["Coustani-group — record as group"]},
    "Anopheles tenebrosus": {"resolution_level": "group", "complex": "An. coustani group",
        "character_states": dict(_COUSTANI_GROUP_STATES), "discriminators": ["Coustani-group — record as group"]},
    "Anopheles marshallii": {"resolution_level": "group", "complex": "An. marshallii group",
        "character_states": _MARSHALLII_GROUP_STATES, "discriminators": ["Marshallii-group — cryptic assemblage"]},
    "Anopheles hancocki": {"resolution_level": "group", "complex": "An. marshallii group",
        "character_states": _MARSHALLII_GROUP_STATES, "discriminators": ["Marshallii-group — molecular advised"]},
    "Anopheles longipalpis": {"resolution_level": "group", "complex": "An. marshallii group",
        "character_states": {**_MARSHALLII_GROUP_STATES, "palp_length": "long"},
        "discriminators": ["Long palps flag the marshallii-group 'type C' form; still group-level"]},
    "Anopheles amharicus": {"resolution_level": "complex", "complex": "An. gambiae complex",
        "character_states": dict(_GAMBIAE_COMPLEX_STATES), "discriminators": ["Gambiae-complex — PCR mandatory"]},
})


def get_anopheles_character_schema() -> list[dict]:
    """
    Ordered, UI-ready description of the Anopheles character vocabulary.
    Each entry: {id, label, weight, states:[{id, label}, ...]}.
    """
    return [
        {
            "id": cid,
            "label": char["label"],
            "weight": char["weight"],
            "states": [{"id": sid, "label": slabel} for sid, slabel in char["states"].items()],
        }
        for cid, char in ANOPHELES_CHARACTERS.items()
    ]


_ANOPHELES_SPECIES_INDEX = None


def _anopheles_species_index() -> dict:
    """Lazy name -> SPECIES_CATALOG entry map for the Anopheles genus."""
    global _ANOPHELES_SPECIES_INDEX
    if _ANOPHELES_SPECIES_INDEX is None:
        _ANOPHELES_SPECIES_INDEX = {
            sp["name"]: sp for sp in SPECIES_CATALOG.get("Anopheles", [])
        }
    return _ANOPHELES_SPECIES_INDEX


def _state_matches(observed_state: str, expected) -> bool:
    if isinstance(expected, (list, tuple, set)):
        return observed_state in expected
    return observed_state == expected


def identify_anopheles_species(observed_characters: dict) -> dict:
    """
    Weighted character-agreement identifier for adult female *Anopheles*.

    `observed_characters` maps character ids (keys of ANOPHELES_CHARACTERS) to
    observed state ids. Only recognised, non-empty pairs are scored.

    Returns a structured verdict carrying:
      resolution_level  species | group | complex | genus | undetermined
      taxon             the honestly-resolvable name (complex/group name when
                        the top hit is a cryptic taxon — never a fake species)
      confidence        weighted % agreement of the leading taxon
      candidates        ranked per-species audit trail (matched/contradicted)
      molecular_id_required, next_step, reason

    The cryptic-complex ceiling is enforced: a gambiae-complex or funestus-group
    winner is collapsed to its complex/group with molecular_id_required=True.
    """
    observed = {
        cid: state
        for cid, state in (observed_characters or {}).items()
        if cid in ANOPHELES_CHARACTERS and state
    }
    if not observed:
        return {
            "resolution_level": "undetermined",
            "taxon": "Anopheles spp.",
            "confidence": 0,
            "candidates": [],
            "molecular_id_required": False,
            "reason": "No diagnostic characters supplied.",
            "next_step": "Record wing, palp and hind-tarsi characters, or walk the couplet key.",
        }

    index = _anopheles_species_index()
    scored = []
    for name, profile in ANOPHELES_KEY_PROFILES.items():
        states = profile["character_states"]
        matched_w = total_w = matched = contradicted = 0
        for cid, obs_state in observed.items():
            if cid not in states:
                continue
            weight = ANOPHELES_CHARACTERS[cid]["weight"]
            total_w += weight
            if _state_matches(obs_state, states[cid]):
                matched_w += weight
                matched += 1
            else:
                contradicted += 1
        if total_w == 0:
            continue
        # Reward agreement, penalise contradictions (0.75 x their weight).
        raw = matched_w - 0.75 * (total_w - matched_w)
        confidence = max(0, min(100, int(round((matched_w / total_w) * 100))))
        sp = index.get(name, {})
        scored.append({
            "species_name": name,
            "complex": profile.get("complex", "None"),
            "resolution_level": profile.get("resolution_level", "species"),
            "raw_score": round(raw, 2),
            "confidence": confidence,
            "characters_matched": matched,
            "characters_contradicted": contradicted,
            "characters_compared": matched + contradicted,
            "vector_status": sp.get("vector_status", "Unknown"),
            "molecular_id_required": sp.get(
                "molecular_id_required",
                profile.get("resolution_level") in ("complex", "group"),
            ),
            "biosecurity_alert": sp.get("biosecurity_alert", profile.get("biosecurity_alert", False)),
            "discriminators": profile.get("discriminators", []),
            "notes": sp.get("notes", ""),
        })

    scored.sort(key=lambda c: (c["raw_score"], c["confidence"], c["characters_matched"]), reverse=True)
    positive = [c for c in scored if c["raw_score"] > 0]
    ranked = positive or scored[:1]
    top = ranked[0]

    # Too little signal to commit beyond genus.
    if top["confidence"] < 40 or top["characters_compared"] < 2:
        return {
            "resolution_level": "genus",
            "taxon": "Anopheles spp.",
            "confidence": top["confidence"],
            "candidates": ranked[:6],
            "molecular_id_required": False,
            "reason": "Character agreement too weak/ambiguous to resolve below genus.",
            "next_step": "Add more diagnostic characters (wing + hind-tarsi carry the most weight) or use the couplet key.",
        }

    ceiling = top["resolution_level"]
    if ceiling in ("complex", "group"):
        complex_name = top["complex"]
        members = [c["species_name"] for c in scored if c["complex"] == complex_name]
        return {
            "resolution_level": ceiling,
            "taxon": complex_name,
            "confidence": top["confidence"],
            "candidates": ranked[:6],
            "complex_members": members,
            "molecular_id_required": True,
            "reason": (
                f"Characters match the {complex_name}; its members are "
                "morphologically inseparable, so identification stops at the "
                f"{ceiling} level."
            ),
            "next_step": "Submit for PCR (species-diagnostic assay) — morphology cannot split this taxon.",
        }

    return {
        "resolution_level": "species",
        "taxon": top["species_name"],
        "confidence": top["confidence"],
        "candidates": ranked[:6],
        "molecular_id_required": top["molecular_id_required"],
        "biosecurity_alert": top["biosecurity_alert"],
        "reason": f"Best structural match: {top['species_name']} ({top['confidence']}% weighted character agreement).",
        "next_step": "Verify the listed discriminating characters against the full dichotomous key before reporting.",
    }


# --------------------------------------------------------------------------
#  Dichotomous couplet key (adult female Anopheles) — simplified from
#  Gillies & Coetzee (1987). Each node poses a couplet; a lead either advances
#  to another node (`goto`) or terminates at a taxon (`taxon`). Terminal leads
#  may carry `complex`/`group` (forces a complex/group-level, PCR-flagged
#  result) or `alert` (biosecurity).
# --------------------------------------------------------------------------
ANOPHELES_COUPLET_KEY = {
    "1": {
        "question": "Hind tarsi with broad conspicuous white bands, and/or femora & tibiae distinctly speckled?",
        "leads": [
            {"text": "Yes — broad white tarsal bands and/or speckled legs", "goto": "2"},
            {"text": "No — hind tarsi dark or only narrowly ringed, legs not speckled", "goto": "3"},
        ],
    },
    "2": {
        "question": "Large, robust body with FOUR palpal pale bands and speckled legs?",
        "leads": [
            {"text": "Yes — large, 4 palpal bands, speckled legs, broad pale tarsal blocks", "taxon": "Anopheles pharoensis"},
            {"text": "No — medium body, other broad-band / speckled savanna & desert forms", "goto": "12"},
        ],
    },
    "3": {
        "question": "Hind tarsi ENTIRELY dark (no pale bands at the joints)?",
        "leads": [
            {"text": "Yes — hind tarsi wholly dark", "goto": "4"},
            {"text": "No — hind tarsi with narrow pale rings at the joints", "goto": "6"},
        ],
    },
    "4": {
        "question": "Wing with a distinct pale spot at the base of vein 6; breeds in fast-flowing, well-oxygenated streams?",
        "leads": [
            {"text": "Yes — pale spot at base of vein 6, patterned fringe", "taxon": "Anopheles nili", "group": "An. nili group"},
            {"text": "No — wing dark and relatively unpatterned", "goto": "5"},
        ],
    },
    "5": {
        "question": "Palp with a long broad apical pale band and a distinct sector pale spot on the costa?",
        "leads": [
            {"text": "Yes — long apical palp band, patterned costa", "taxon": "Anopheles funestus (s.s.)", "group": "An. funestus group"},
            {"text": "No — wing largely dark, slow riverine / floating-vegetation habitat", "taxon": "Anopheles moucheti", "group": "An. moucheti group"},
        ],
    },
    "6": {
        "question": "Palps distinctly speckled / irregularly dark-spotted, legs speckled?",
        "leads": [
            {"text": "Yes — speckled palps", "taxon": "Anopheles maculipalpis"},
            {"text": "No — palps with three clean pale bands, legs not speckled", "goto": "7"},
        ],
    },
    "7": {
        "question": "Proboscis and/or palp tips distinctly pale; grassy swamp-margin savanna habitat?",
        "leads": [
            {"text": "Yes — pale-tipped proboscis/palps", "taxon": "Anopheles coustani", "group": "An. coustani group"},
            {"text": "No — proboscis uniformly dark", "goto": "8"},
        ],
    },
    "8": {
        "question": "Wing costa largely pale / lightly scaled (NOT the contrasting pale-and-dark spotted pattern of the gambiae complex)?",
        "leads": [
            {"text": "Yes — pale, lightly-scaled wings", "goto": "9"},
            {"text": "No — wing with contrasting pale/dark spots, proboscis uniformly dark", "goto": "10"},
        ],
    },
    "9": {
        "question": "Very small-bodied with a Sahelian / arid-zone distribution?",
        "leads": [
            {"text": "Yes — small, pale, Sahelian", "taxon": "Anopheles wellcomei"},
            {"text": "No — medium body, widespread open savanna", "taxon": "Anopheles squamosus"},
        ],
    },
    "10": {
        "question": "Cool highland / montane distribution (East & Central African highlands)?",
        "leads": [
            {"text": "Yes — cool highland / montane species", "goto": "16"},
            {"text": "No — lowland / savanna distribution", "goto": "11"},
        ],
    },
    "11": {
        "question": "Container / urban breeding with palpal banding matching the Coetzee (2020) invasive-vector key?",
        "leads": [
            {"text": "Yes — urban container breeder (invasive profile)", "taxon": "Anopheles stephensi", "alert": True},
            {"text": "No — standard breeder, spotted-wing lowland Anopheles", "goto": "17"},
        ],
    },
    # ── Desert / oasis branch (off couplet 2) ──
    "12": {
        "question": "Hind tarsi reddish-brown ('red-footed'), moist savanna / rice fields?",
        "leads": [
            {"text": "Yes — red-footed, speckled legs", "taxon": "Anopheles rufipes"},
            {"text": "No — pale / speckled, drier or arid habitat", "goto": "13"},
        ],
    },
    "13": {
        "question": "Arid-zone specimen: Saharan oasis, saline pan or rocky desert wadi?",
        "leads": [
            {"text": "Yes — arid / oasis / desert habitat", "goto": "14"},
            {"text": "No — drier savanna, rock pools", "taxon": "Anopheles pretoriensis"},
        ],
    },
    "14": {
        "question": "Very pale body with broad pale tarsal banding, saline oasis water?",
        "leads": [
            {"text": "Yes — very pale, broad bands", "taxon": "Anopheles multicolor"},
            {"text": "No", "goto": "15"},
        ],
    },
    "15": {
        "question": "Conspicuously speckled legs, rocky mountain-desert wadi pools?",
        "leads": [
            {"text": "Yes — speckled legs, wadi pools", "taxon": "Anopheles dthali"},
            {"text": "No — narrow apical tarsal bands, spring-fed oasis", "taxon": "Anopheles sergentii"},
        ],
    },
    # ── Highland split (off couplet 10): marshallii group vs An. cinereus ──
    "16": {
        "question": "Spotted wings + montane-forest profile (marshallii group)?",
        "leads": [
            {"text": "Yes — marshallii-group profile", "taxon": "Anopheles demeilloni", "group": "An. marshallii group"},
            {"text": "No — pale greyish, Ethiopian highland", "taxon": "Anopheles cinereus"},
        ],
    },
    # ── Gambiae-complex montane member (off couplet 11) ──
    "17": {
        "question": "Ethiopian-highland, strictly zoophilic gambiae-complex member?",
        "leads": [
            {"text": "Yes — highland zoophilic", "taxon": "Anopheles amharicus", "complex": "An. gambiae complex"},
            {"text": "No — standard rain-pool / permanent-water breeder", "taxon": "Anopheles gambiae (s.s.)", "complex": "An. gambiae complex"},
        ],
    },
}

ANOPHELES_KEY_ROOT = "1"


def anopheles_key_node(node_id: str) -> dict | None:
    """Return the couplet node for `node_id` (or None if unknown)."""
    return ANOPHELES_COUPLET_KEY.get(node_id)


def _resolve_key_terminal(lead: dict) -> dict:
    """Build a rich, guardrail-respecting result for a terminal key lead."""
    name = lead["taxon"]
    sp = _anopheles_species_index().get(name, {})
    profile = ANOPHELES_KEY_PROFILES.get(name, {})

    if "complex" in lead:
        resolution, taxon = "complex", lead["complex"]
    elif "group" in lead:
        resolution, taxon = "group", lead["group"]
    else:
        resolution = profile.get("resolution_level", "species")
        taxon = profile.get("complex", "None") if resolution in ("complex", "group") else name
        if taxon in (None, "None"):
            taxon = name

    is_cryptic = resolution in ("complex", "group")
    return {
        "taxon": taxon,
        "matched_species": name,
        "resolution_level": resolution,
        "complex": lead.get("complex") or lead.get("group") or profile.get("complex", "None"),
        "vector_status": sp.get("vector_status", "Unknown"),
        # A group/complex terminal is inseparable to species → always require PCR,
        # regardless of any single member's catalog flag.
        "molecular_id_required": bool(is_cryptic or sp.get("molecular_id_required", False)),
        "biosecurity_alert": bool(lead.get("alert") or sp.get("biosecurity_alert", False)),
        "discriminators": profile.get("discriminators", []),
        "notes": sp.get("notes", ""),
        "next_step": (
            "Submit for PCR — this taxon cannot be split to species by morphology."
            if is_cryptic
            else "Confirm against the full dichotomous key and verify the listed discriminators."
        ),
    }


def anopheles_key_step(node_id: str, lead_index: int) -> dict:
    """
    Advance the couplet key one step.

    Returns either:
      {"type": "couplet",  "node_id": <next>, "couplet": <node>}
      {"type": "terminal", "result": {...}}
      {"type": "error",    "message": "..."}
    """
    node = ANOPHELES_COUPLET_KEY.get(node_id)
    if not node:
        return {"type": "error", "message": f"Unknown key node '{node_id}'."}
    try:
        lead = node["leads"][lead_index]
    except (IndexError, TypeError):
        return {"type": "error", "message": "Invalid lead selection for this couplet."}

    if "goto" in lead:
        nxt = lead["goto"]
        return {"type": "couplet", "node_id": nxt, "couplet": ANOPHELES_COUPLET_KEY[nxt]}
    return {"type": "terminal", "result": _resolve_key_terminal(lead)}


# ==========================================================================
#  GENERIC CHARACTER-AGREEMENT SCORER (shared by Culex & Aedes deep keys)
# --------------------------------------------------------------------------
#  A genus-agnostic reduction of the Anopheles engine. It enforces the SAME
#  cryptic-taxon ceiling: any complex/group winner collapses to the group name
#  with molecular_id_required=True, and never manufactures a single-species
#  answer the morphology cannot support.
# ==========================================================================
def _genus_species_index(genus: str) -> dict:
    """name -> SPECIES_CATALOG entry for a genus (vector_status/notes lookup)."""
    return {sp["name"]: sp for sp in SPECIES_CATALOG.get(genus, [])}


def identify_by_characters(observed_characters, *, characters, profiles,
                           species_index, genus_label, contradiction_penalty=0.75,
                           min_confidence=40, min_compared=2):
    """Weighted character-agreement identifier for one genus.

    `characters`    : {char_id: {weight, states, ...}}
    `profiles`      : {species_name: {resolution_level, complex, character_states, discriminators}}
    `species_index` : {species_name: catalog_entry}
    Returns the same verdict shape as identify_anopheles_species().
    """
    observed = {cid: st for cid, st in (observed_characters or {}).items()
                if cid in characters and st}
    if not observed:
        return {"resolution_level": "undetermined", "taxon": f"{genus_label} spp.",
                "confidence": 0, "candidates": [], "molecular_id_required": False,
                "reason": "No diagnostic characters supplied.",
                "next_step": "Record scutal, proboscis, tarsal and wing characters."}

    scored = []
    for name, profile in profiles.items():
        states = profile["character_states"]
        matched_w = total_w = matched = contradicted = 0
        for cid, obs_state in observed.items():
            if cid not in states:
                continue
            weight = characters[cid]["weight"]
            total_w += weight
            if _state_matches(obs_state, states[cid]):
                matched_w += weight
                matched += 1
            else:
                contradicted += 1
        if total_w == 0:
            continue
        raw = matched_w - contradiction_penalty * (total_w - matched_w)
        confidence = max(0, min(100, int(round((matched_w / total_w) * 100))))
        sp = species_index.get(name, {})
        res = profile.get("resolution_level", "species")
        scored.append({"species_name": name, "complex": profile.get("complex", "None"),
                       "resolution_level": res, "raw_score": round(raw, 2), "confidence": confidence,
                       "characters_matched": matched, "characters_contradicted": contradicted,
                       "characters_compared": matched + contradicted,
                       "vector_status": sp.get("vector_status", "Unknown"),
                       "molecular_id_required": sp.get("molecular_id_required", res in ("complex", "group")),
                       "biosecurity_alert": sp.get("biosecurity_alert", profile.get("biosecurity_alert", False)),
                       "biocontrol_indicator": sp.get("biocontrol_indicator", False),
                       "discriminators": profile.get("discriminators", []), "notes": sp.get("notes", "")})

    # Surveillance-safe tie-break: when two taxa match the observed characters
    # *equally*, prefer the cryptic group/complex (flag "needs PCR") rather than
    # commit to one look-alike species. Real score differences always dominate.
    def _is_cryptic(c):
        return 1 if c["resolution_level"] in ("complex", "group") else 0
    scored.sort(key=lambda c: (c["raw_score"], _is_cryptic(c), c["confidence"],
                               c["characters_matched"]), reverse=True)
    positive = [c for c in scored if c["raw_score"] > 0]
    ranked = positive or scored[:1]
    top = ranked[0]

    if top["confidence"] < min_confidence or top["characters_compared"] < min_compared:
        return {"resolution_level": "genus", "taxon": f"{genus_label} spp.",
                "confidence": top["confidence"], "candidates": ranked[:6],
                "molecular_id_required": False,
                "reason": "Character agreement too weak/ambiguous to resolve below genus.",
                "next_step": "Add more diagnostic characters or use a dichotomous key."}

    ceiling = top["resolution_level"]
    if ceiling in ("complex", "group"):
        complex_name = top["complex"]
        members = [c["species_name"] for c in scored if c["complex"] == complex_name]
        return {"resolution_level": ceiling, "taxon": complex_name, "confidence": top["confidence"],
                "candidates": ranked[:6], "complex_members": members, "molecular_id_required": True,
                "reason": (f"Characters match the {complex_name}; its members are morphologically "
                           f"inseparable, so identification stops at the {ceiling} level."),
                "next_step": "Submit for PCR (species-diagnostic assay) — morphology cannot split this taxon."}

    return {"resolution_level": "species", "taxon": top["species_name"], "confidence": top["confidence"],
            "candidates": ranked[:6], "molecular_id_required": top["molecular_id_required"],
            "biosecurity_alert": top["biosecurity_alert"], "biocontrol_indicator": top["biocontrol_indicator"],
            "reason": f"Best structural match: {top['species_name']} ({top['confidence']}% weighted agreement).",
            "next_step": "Verify the listed discriminators against the full key before reporting."}


# ==========================================================================
#  CULEX DEEP-KEY ENGINE
# ==========================================================================
CULEX_CHARACTERS = {
    "proboscis_band": {"label": "Proboscis pale banding", "weight": 4,
        "states": {"none": "No pale bands (dark proboscis)", "one_median": "Single median pale band",
                   "two_bands": "Two pale bands", "three_bands": "Three pale bands"}},
    "tarsi_bands": {"label": "Tarsal pale banding", "weight": 3,
        "states": {"dark": "Entirely dark", "pale_banded": "Pale bands present",
                   "variegated_rings": "Distinct pale rings ('variegated feet')"}},
    "scutal_stripe": {"label": "Scutum pattern", "weight": 3,
        "states": {"none": "Uniform, no stripe", "single_pale_stripe": "Single pale longitudinal stripe",
                   "reddish": "Reddish scutal markings", "metallic": "Metallic sheen"}},
    "body_scaling": {"label": "General body scaling", "weight": 2,
        "states": {"brown": "Ordinary brown", "sandy_pale": "Pale sandy", "ashy_grey": "Ashy grey",
                   "cloudy_wing": "Cloudy-winged"}},
    "leg_stripes": {"label": "Leg striping (predator cue)", "weight": 3,
        "states": {"none": "None", "tiger_striped": "Boldly tiger-striped legs"}},
    "habitat": {"label": "Larval habitat", "weight": 2,
        "states": {"urban_container": "Urban / container", "floodwater": "Floodplain / flooded fields",
                   "coastal_saline": "Coastal / brackish", "forest": "Forest / swamp margin",
                   "highland": "Highland", "open_sunlit": "Open sunlit pools"}},
    "body_size": {"label": "Body size", "weight": 1,
        "states": {"small": "Small", "medium": "Medium", "large": "Large"}},
}

_PIPIENS_STATES = {"proboscis_band": "none", "tarsi_bands": "dark", "scutal_stripe": "none",
                   "body_scaling": "brown", "leg_stripes": "none", "habitat": "urban_container",
                   "body_size": "medium"}
_DECENS_STATES = {"proboscis_band": "none", "tarsi_bands": "dark", "scutal_stripe": "none",
                  "body_scaling": "brown", "habitat": "forest", "body_size": "medium"}

CULEX_KEY_PROFILES = {
    "Culex quinquefasciatus": {"resolution_level": "complex", "complex": "Culex pipiens complex",
        "character_states": _PIPIENS_STATES, "discriminators": ["Pipiens complex — dissection/COI required"]},
    "Culex pipiens": {"resolution_level": "complex", "complex": "Culex pipiens complex",
        "character_states": _PIPIENS_STATES, "discriminators": ["Pipiens complex — hybridizes; molecular needed"]},
    "Culex antennatus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "pale_banded", "scutal_stripe": "none",
            "body_scaling": "brown", "habitat": "floodwater", "body_size": "medium"},
        "discriminators": ["Pale-banded tarsi + irrigated/flooded habitat"]},
    "Culex poicilipes": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "variegated_rings",
            "habitat": "floodwater", "body_size": "medium"},
        "discriminators": ["Variegated 'ringed' feet, savanna floodplain"]},
    "Culex perfuscus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "dark", "body_scaling": "brown",
            "habitat": "forest", "body_size": "medium"},
        "discriminators": ["Forest, dark unbanded legs (vs antennatus/poicilipes)"]},
    "Culex univittatus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "one_median", "scutal_stripe": "single_pale_stripe",
            "habitat": "open_sunlit", "body_size": "medium"},
        "discriminators": ["Single pale scutal stripe, open sunlit water"]},
    "Culex neavei": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "one_median", "scutal_stripe": "single_pale_stripe",
            "habitat": "forest", "body_size": "medium"},
        "discriminators": ["Mirrors univittatus; separate on wing/leg scale detail"]},
    "Culex thalassius": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "one_median", "scutal_stripe": "single_pale_stripe",
            "habitat": "coastal_saline", "body_size": "medium"},
        "discriminators": ["Univittatus-like but coastal/brackish"]},
    "Culex theileri": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "one_median", "tarsi_bands": "pale_banded",
            "body_scaling": "sandy_pale", "body_size": "medium"},
        "discriminators": ["Sandy pale body, arid livestock landscapes"]},
    "Culex tritaeniorhynchus": {"resolution_level": "group", "complex": "Vishnui Subgroup",
        "character_states": {"proboscis_band": "three_bands", "tarsi_bands": "pale_banded",
            "habitat": "floodwater", "body_size": "medium"},
        "discriminators": ["Triple-banded proboscis flags the subgroup; molecular to split"]},
    "Culex bitaeniorhynchus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "two_bands", "habitat": "open_sunlit", "body_size": "medium"},
        "discriminators": ["Two pale proboscis bands (name-diagnostic)"]},
    "Culex sitiens": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "one_median", "tarsi_bands": "pale_banded",
            "habitat": "coastal_saline", "body_size": "medium"},
        "discriminators": ["Coastal/estuarine, pale-banded proboscis & tarsi"]},
    "Culex annulioris": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "pale_banded",
            "habitat": "forest", "body_size": "medium"},
        "discriminators": ["Boldly ringed legs, forest/swamp"]},
    "Culex duttoni": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "dark", "body_scaling": "brown",
            "habitat": "urban_container", "body_size": "small"},
        "discriminators": ["Small, dark, domestic container breeder"]},
    "Culex nebulosus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "body_scaling": "cloudy_wing", "body_size": "medium"},
        "discriminators": ["Cloudy-winged macroscopic appearance"]},
    "Culex cinereus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "body_scaling": "ashy_grey", "body_size": "medium"},
        "discriminators": ["Ashy-grey scaling, generalist breeder"]},
    "Culex rubinotus": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "scutal_stripe": "reddish", "body_size": "medium"},
        "discriminators": ["Reddish scutal tint"]},
    "Culex grahamii": {"resolution_level": "species", "complex": "None",
        "character_states": {"proboscis_band": "none", "tarsi_bands": "dark", "body_scaling": "brown",
            "body_size": "small"}, "discriminators": ["Tiny, unremarkable ground-pool breeder"]},
    "Culex decens": {"resolution_level": "group", "complex": "Cx. decens group",
        "character_states": _DECENS_STATES, "discriminators": ["Decens-group — record as group"]},
    "Culex guiarti": {"resolution_level": "group", "complex": "Cx. decens group",
        "character_states": _DECENS_STATES, "discriminators": ["Decens-group member"]},
    "Culex trifilatus": {"resolution_level": "group", "complex": "Cx. decens group",
        "character_states": _DECENS_STATES, "discriminators": ["Decens-group member"]},
    "Culex invidiosus": {"resolution_level": "group", "complex": "Cx. decens group",
        "character_states": _DECENS_STATES, "discriminators": ["Decens-group member"]},
    "Culex tigripes": {"resolution_level": "species", "complex": "None",
        "character_states": {"leg_stripes": "tiger_striped", "body_size": "large",
            "proboscis_band": "none", "tarsi_bands": "pale_banded"},
        "discriminators": ["BIOCONTROL: tiger-striped predator; harmless adult, larvivorous larva"]},
}


def identify_culex_species(observed_characters: dict) -> dict:
    """Weighted character-agreement identifier for adult *Culex*.

    Same guardrail as the Anopheles engine: the Culex pipiens complex, Vishnui
    subgroup and Cx. decens group collapse to the group name with
    molecular_id_required=True — never a bare member species.
    """
    return identify_by_characters(observed_characters, characters=CULEX_CHARACTERS,
                                  profiles=CULEX_KEY_PROFILES,
                                  species_index=_genus_species_index("Culex"),
                                  genus_label="Culex")


def get_culex_character_schema() -> list[dict]:
    return [{"id": cid, "label": c["label"], "weight": c["weight"],
             "states": [{"id": s, "label": lbl} for s, lbl in c["states"].items()]}
            for cid, c in CULEX_CHARACTERS.items()]


# ==========================================================================
#  AEDES DEEP-KEY ENGINE
# ==========================================================================
AEDES_CHARACTERS = {
    "scutal_pattern": {"label": "Scutal (thoracic) pattern", "weight": 4,
        "states": {"lyre_shape": "Silver lyre-shaped pattern", "single_median_stripe": "Single bold silver median stripe",
                   "narrow_median_stripe": "Narrow pale median stripe", "metallic_plain": "Plain metallic blue-black",
                   "silver_spotted": "Discrete silver spots", "longitudinal_plus_lateral": "Median line + curved lateral lines",
                   "nondescript": "Dull / nondescript"}},
    "tarsi_bands": {"label": "Hind-tarsal pale banding", "weight": 3,
        "states": {"broad_white_basal": "Broad basal white bands", "narrow_pale": "Narrow pale bands",
                   "dark": "Entirely dark", "pale_banded": "Pale-banded (unspecified)"}},
    "head_scales": {"label": "Head / vertex scaling", "weight": 3,
        "states": {"pale_yellowish": "Distinctly pale / yellowish", "normal_dark": "Ordinary dark"}},
    "apical_silver": {"label": "Apical silver scaling (wing/leg tips)", "weight": 2,
        "states": {"present": "Concentrated at apex", "absent": "Not concentrated apically"}},
    "habitat_form": {"label": "Breeding habitat / form", "weight": 2,
        "states": {"container_urban": "Container / urban", "rock_pool": "Rock pool", "plant_axil": "Leaf / plant axil",
                   "forest_canopy": "Forest canopy", "floodwater_dambo": "Floodwater / dambo", "coastal": "Coastal"}},
    "body_size": {"label": "Body size", "weight": 1,
        "states": {"small": "Small", "medium": "Medium", "large": "Large"}},
}

_SIMPSONI_STATES = {"scutal_pattern": "narrow_median_stripe", "tarsi_bands": "broad_white_basal",
                    "head_scales": "normal_dark", "habitat_form": "plant_axil", "body_size": "medium"}
_FURCIFER_STATES = {"scutal_pattern": "nondescript", "tarsi_bands": "broad_white_basal",
                    "head_scales": "normal_dark", "habitat_form": "forest_canopy", "body_size": "medium"}
_CABALLUS_STATES = {"scutal_pattern": "nondescript", "tarsi_bands": "pale_banded",
                    "habitat_form": "floodwater_dambo", "body_size": "medium"}

AEDES_KEY_PROFILES = {
    "Aedes aegypti": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "lyre_shape", "tarsi_bands": "broad_white_basal",
            "head_scales": "normal_dark", "habitat_form": "container_urban", "body_size": "medium"},
        "discriminators": ["Silver lyre on scutum + white-banded tarsi", "domestic vs sylvatic forms via scale density"]},
    "Aedes albopictus": {"resolution_level": "species", "complex": "None", "biosecurity_alert": True,
        "character_states": {"scutal_pattern": "single_median_stripe", "tarsi_bands": "broad_white_basal",
            "head_scales": "normal_dark", "habitat_form": "container_urban", "body_size": "medium"},
        "discriminators": ["Single straight silver median stripe (vs aegypti lyre) — INVASIVE"]},
    "Aedes africanus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "narrow_median_stripe", "tarsi_bands": "broad_white_basal",
            "head_scales": "normal_dark", "habitat_form": "forest_canopy", "body_size": "medium"},
        "discriminators": ["Narrow pale median stripe, broad basal tarsal bands, canopy YF vector"]},
    "Aedes luteocephalus": {"resolution_level": "species", "complex": "None",
        "character_states": {"head_scales": "pale_yellowish", "tarsi_bands": "broad_white_basal",
            "habitat_form": "forest_canopy", "body_size": "medium"},
        "discriminators": ["Pale/yellowish head scaling (name-diagnostic)"]},
    "Aedes metallicus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "metallic_plain", "head_scales": "normal_dark", "body_size": "medium"},
        "discriminators": ["Unbroken metallic blue-black scutum"]},
    "Aedes vittatus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "longitudinal_plus_lateral", "tarsi_bands": "broad_white_basal",
            "habitat_form": "rock_pool", "body_size": "medium"},
        "discriminators": ["Median + curved lateral silver lines, rock-pool breeder"]},
    "Aedes apicoargenteus": {"resolution_level": "species", "complex": "None",
        "character_states": {"apical_silver": "present", "habitat_form": "forest_canopy", "body_size": "medium"},
        "discriminators": ["Silver scaling clustered at wing/leg apex"]},
    "Aedes argenteopunctatus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "silver_spotted", "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Discrete silver thoracic spots, floodwater RVF zones"]},
    "Aedes unilineatus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "narrow_median_stripe", "tarsi_bands": "narrow_pale", "body_size": "small"},
        "discriminators": ["Single fine dull line (weaker than albopictus stripe)"]},
    "Aedes vexans": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "narrow_pale",
            "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Narrow pale tarsal rings, mass floodwater broods"]},
    "Aedes mcintoshi": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "pale_banded",
            "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Dambo floodwater; desiccation-resistant soil eggs — RVF epidemic driver"]},
    "Aedes ochraceus": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "pale_banded",
            "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Co-occurs with mcintoshi in dambos"]},
    "Aedes fowleri": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "pale_banded",
            "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Arid-zone floodwater RVF vector"]},
    "Aedes dalzieli": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "pale_banded",
            "habitat_form": "floodwater_dambo", "body_size": "medium"},
        "discriminators": ["Savanna floodwater arbovirus vector"]},
    "Aedes pembaensis": {"resolution_level": "species", "complex": "None",
        "character_states": {"tarsi_bands": "broad_white_basal", "habitat_form": "coastal", "body_size": "medium"},
        "discriminators": ["Coastal crab-hole breeder, broad tarsal bands"]},
    "Aedes cumminsii": {"resolution_level": "species", "complex": "None",
        "character_states": {"scutal_pattern": "nondescript", "tarsi_bands": "narrow_pale", "body_size": "medium"},
        "discriminators": ["Dull savanna generalist, faint abdominal bands"]},
    "Aedes furcifer": {"resolution_level": "group", "complex": "Ae. furcifer-taylori group",
        "character_states": _FURCIFER_STATES, "discriminators": ["Furcifer-taylori group — separate via genitalia"]},
    "Aedes taylori": {"resolution_level": "group", "complex": "Ae. furcifer-taylori group",
        "character_states": _FURCIFER_STATES, "discriminators": ["Furcifer-taylori group — log as group"]},
    "Aedes simpsoni (s.l.)": {"resolution_level": "complex", "complex": "Aedes simpsoni complex",
        "character_states": _SIMPSONI_STATES, "discriminators": ["Simpsoni complex — PCR required"]},
    "Aedes bromeliae": {"resolution_level": "complex", "complex": "Aedes simpsoni complex",
        "character_states": _SIMPSONI_STATES, "discriminators": ["Anthropophilic YF bridge vector, but morphologically cryptic — PCR"]},
    "Aedes lilii": {"resolution_level": "complex", "complex": "Aedes simpsoni complex",
        "character_states": _SIMPSONI_STATES, "discriminators": ["Simpsoni complex — PCR required"]},
    "Aedes caballus": {"resolution_level": "group", "complex": "Ae. caballus-juppi pair",
        "character_states": _CABALLUS_STATES, "discriminators": ["Caballus/juppi sibling pair — molecular needed"]},
    "Aedes juppi": {"resolution_level": "group", "complex": "Ae. caballus-juppi pair",
        "character_states": _CABALLUS_STATES, "discriminators": ["Caballus/juppi sibling pair — molecular needed"]},
}


def identify_aedes_species(observed_characters: dict) -> dict:
    """Weighted character-agreement identifier for adult *Aedes*.

    Enforces the cryptic ceiling: the Ae. simpsoni complex, furcifer-taylori
    group and caballus-juppi pair collapse to the group name (PCR-flagged);
    genuinely diagnostic species (aegypti, albopictus …) resolve to species.
    """
    return identify_by_characters(observed_characters, characters=AEDES_CHARACTERS,
                                  profiles=AEDES_KEY_PROFILES,
                                  species_index=_genus_species_index("Aedes"),
                                  genus_label="Aedes")


def get_aedes_character_schema() -> list[dict]:
    return [{"id": cid, "label": c["label"], "weight": c["weight"],
             "states": [{"id": s, "label": lbl} for s, lbl in c["states"].items()]}
            for cid, c in AEDES_CHARACTERS.items()]


# ==========================================================================
#  LARVAL 4th-INSTAR DEEP-KEY (resolves to GENUS only, honestly)
# ==========================================================================
LARVAL_CHARACTERS = {
    "siphon": {"label": "Respiratory siphon", "weight": 4,
        "states": {"absent": "Absent (spiracular plate flush with surface)",
                   "short_stout": "Short & stout", "long_slender": "Long & slender"}},
    "float_hairs": {"label": "Abdominal palmate (float) hairs", "weight": 4,
        "states": {"palmate_present": "Palmate float hairs present", "absent": "Absent"}},
    "posture": {"label": "Resting posture", "weight": 3,
        "states": {"parallel": "Parallel/horizontal to surface film", "angled": "Head-down at an angle"}},
    "pecten_subventral_tufts": {"label": "Siphon subventral setal tufts", "weight": 2,
        "states": {"multiple_tufts": "Several tufts along siphon", "single_pair": "One pair only", "none": "None"}},
    "comb_scales": {"label": "Abdominal segment VIII comb", "weight": 2,
        "states": {"single_row": "Single row", "patch": "Patch/triangle", "absent": "Absent"}},
    "predator_habitus": {"label": "Predatory habitus", "weight": 2,
        "states": {"large_striped_predator": "Large, boldly striped, actively predatory", "normal": "Ordinary filter feeder"}},
}


def evaluate_larval_deepkey(observed: dict) -> dict:
    """Resolve a 4th-instar larva to GENUS with a per-character audit, plus a
    Culex tigripes predator flag. Never claims species — wild larval species ID
    needs chaetotaxy slides or molecular assays."""
    o = observed or {}
    siphon = o.get("siphon")
    floats = o.get("float_hairs")
    posture = o.get("posture")
    predator = o.get("predator_habitus")

    # Anopheline signature: no siphon + palmate float hairs + parallel posture
    if siphon == "absent" or floats == "palmate_present" or posture == "parallel":
        return {"resolved_genus": "Anopheles", "resolution_level": "genus",
                "confidence_tier": "High-confidence genus triage",
                "notes": ("Anopheline larva (no siphon, palmate float hairs, lies parallel). "
                          "Cryptic complexes make species-level calls invalid on wild larvae without "
                          "chaetotaxy slide counts or molecular assays."),
                "next_step": "For gambiae/funestus-group localities, rear to adult or PCR for species."}

    predator_flag = (predator == "large_striped_predator")
    if siphon == "long_slender" or o.get("pecten_subventral_tufts") == "multiple_tufts":
        note = "Culicine (Culex) larva: long slender siphon with several subventral setal tufts."
        if predator_flag:
            note = ("Large, boldly striped predatory culicine larva — evaluate for Culex tigripes, "
                    "a larvivorous BIOCONTROL indicator, not a vector.")
        return {"resolved_genus": "Culex", "resolution_level": "genus",
                "confidence_tier": "High-confidence genus triage",
                "biocontrol_candidate": predator_flag, "notes": note,
                "next_step": "Species needs male genitalia or COI; flag tigripes as beneficial if predatory."}

    if siphon == "short_stout":
        return {"resolved_genus": "Aedes", "resolution_level": "genus",
                "confidence_tier": "High-confidence genus triage",
                "notes": ("Aedine larva: short stout siphon, typically one pair of subventral tufts, "
                          "comb scales in a row/patch. Container or floodwater habitats."),
                "next_step": "Species needs reared adults or molecular confirmation."}

    return {"resolved_genus": "Undetermined Culicinae", "resolution_level": "undetermined",
            "confidence_tier": "Inconclusive",
            "notes": "Characters do not line up with standard 4th-instar keys; re-examine under magnification.",
            "next_step": "Record siphon form, palmate hairs and posture."}


def get_larval_character_schema() -> list[dict]:
    return [{"id": cid, "label": c["label"], "weight": c["weight"],
             "states": [{"id": s, "label": lbl} for s, lbl in c["states"].items()]}
            for cid, c in LARVAL_CHARACTERS.items()]

