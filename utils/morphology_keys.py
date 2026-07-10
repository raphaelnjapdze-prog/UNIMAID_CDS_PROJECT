"""
Taxonomic Reference & Morphological Screening Engine for Afrotropical Vectors.
Implements genus-level triage arrays, larval separation mechanics, and comprehensive
species reference catalogs for 60 distinct African mosquito profiles.

Grounded completely in standard reference criteria: Coetzee (2020), Gillies &
Coetzee (1987), Service (1990), and Jupp (1996).
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
        }
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
        }
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
        }
    ]
}

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

