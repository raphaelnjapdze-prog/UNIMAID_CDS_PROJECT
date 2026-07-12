"""
Mosquito species taxonomy with cryptic-complex constraints.

This module enforces a scientifically grounded class hierarchy that respects
the biological reality of morphologically indistinguishable cryptic species
complexes in African Anopheles and Culex. It prevents downstream code from
attempting to classify individual complex members as distinct species without
paired molecular (PCR) confirmation, which is scientifically unsupported.

CRITICAL BIOLOGICAL NOTES:
- Anopheles gambiae complex: gambiae s.s., coluzzii, arabiensis, merus, melas,
  quadriannulatus are morphologically indistinguishable. PCR is required for
  species-level resolution. Classification must treat them as a single class.
- Anopheles funestus group: funestus s.s., rivulorum, parensis, leesoni,
  vaneedeni are morphologically cryptic. PCR required for species splitting.
  Classification must treat them as a single class.
- Similar constraints exist in Culex (pipiens complex) but are less critical
  for vector surveillance in African contexts.
"""

from typing import Dict, List, Optional, Set


# ========================================================================
# GENUS CLASSES (Stage 1)
# ========================================================================
GENERA = ["Anopheles", "Culex", "Aedes"]
GENUS_CLASSES = {0: "Anopheles", 1: "Culex", 2: "Aedes"}


# ========================================================================
# ANOPHELES SPECIES/COMPLEX CLASSES (Stage 2)
# ========================================================================
# These are the exact output classes for an Anopheles specialist classifier.
# CONSTRAINT: Cryptic complexes are treated as SINGLE CLASSES, not split.
ANOPHELES_CLASSES = [
    "An. gambiae complex",  # Index 0: COMPLEX (not individual spp.)
    "An. funestus group",   # Index 1: GROUP (not individual spp.)
    "An. nili",             # Index 2: Distinguishable species
    "An. moucheti",         # Index 3
    "An. pharoensis",       # Index 4
    "An. squamosus",        # Index 5
    "An. coustani",         # Index 6
    "An. rufipes",          # Index 7
    "An. wellcomei",        # Index 8
    "An. maculipalpis",     # Index 9
    "An. demeilloni",       # Index 10
    "An. stephensi",        # Index 11 (invasive, emerging threat)
]
ANOPHELES_CLASS_DICT = {i: name for i, name in enumerate(ANOPHELES_CLASSES)}

# Cryptic complex members that CANNOT be visually distinguished.
# If someone tries to add these as individual classes, assert and warn.
ANOPHELES_CRYPTIC_COMPLEXES = {
    "An. gambiae complex": [
        "An. gambiae s.s.",
        "An. coluzzii",
        "An. arabiensis",
        "An. merus",
        "An. melas",
        "An. quadriannulatus",
    ],
    "An. funestus group": [
        "An. funestus s.s.",
        "An. rivulorum",
        "An. parensis",
        "An. leesoni",
        "An. vaneedeni",
    ],
}


# ========================================================================
# CULEX SPECIES/COMPLEX CLASSES (Stage 2)
# ========================================================================
CULEX_CLASSES = [
    "Cx. quinquefasciatus",  # Index 0: Primary urban vector
    "Cx. pipiens complex",   # Index 1: Group (pipiens + quinquefasciatus overlap)
    "Cx. antennatus",        # Index 2: RVF vector
    "Cx. poicilipes",        # Index 3: RVF, WNV vector
    "Cx. perfuscus",         # Index 4
    "Cx. univittatus",       # Index 5: WNV vector
    "Cx. neavei",            # Index 6
    "Cx. theileri",          # Index 7
    "Cx. tritaeniorhynchus", # Index 8
    "Cx. duttoni",           # Index 9
    "Cx. tigripes",          # Index 10: Biocontrol indicator (predatory)
]
CULEX_CLASS_DICT = {i: name for i, name in enumerate(CULEX_CLASSES)}

# Culex pipiens complex has overlapping morphologies; less critical for African
# surveillance but included for reference.
CULEX_CRYPTIC_COMPLEXES = {
    "Cx. pipiens complex": [
        "Cx. pipiens",
        "Cx. quinquefasciatus",
        # Note: these overlap extensively in some zones; molecular ID recommended.
    ],
}


# ========================================================================
# AEDES SPECIES/COMPLEX CLASSES (Stage 2)
# ========================================================================
AEDES_CLASSES = [
    "Ae. aegypti",           # Index 0: Dengue, Zika, Yellow Fever vector
    "Ae. albopictus",        # Index 1: Invasive, dengue, chikungunya vector
    "Ae. africanus",         # Index 2: Yellow Fever (sylvatic)
    "Ae. simpsoni",          # Index 3: YF, cryptic complex but less critical
    "Ae. vittatus",          # Index 4: Dengue, Chikungunya (secondary)
    "Ae. furcifer",          # Index 5: YF (sylvatic)
    "Ae. taylori",           # Index 6: YF (sylvatic, morphologically similar to furcifer)
    "Ae. luteocephalus",     # Index 7: YF, dengue
    "Ae. metallicus",        # Index 8
    "Ae. unilineatus",       # Index 9
    "Ae. dentatus",          # Index 10: Savanna species
    "Ae. circumluteolus",    # Index 11: RVF (secondary)
    "Ae. mcintoshi",         # Index 12: RVF PRIMARY floodwater vector
    "Ae. ochraceus",         # Index 13: RVF (secondary)
    "Ae. sudanensis",        # Index 14
    "Ae. cumminsii",         # Index 15
    "Ae. apicoargenteus",    # Index 16
    "Ae. opok",              # Index 17
    "Ae. neoafricanus",      # Index 18
    "Ae. argenteopunctatus", # Index 19: RVF (secondary)
]
AEDES_CLASS_DICT = {i: name for i, name in enumerate(AEDES_CLASSES)}

AEDES_CRYPTIC_COMPLEXES = {
    # Aedes cryptic complexes are less pronounced in African contexts;
    # simpsoni group exists but is not critical for field surveillance classification.
}


# ========================================================================
# VALIDATION AND CONSTRAINT CHECKING
# ========================================================================


def validate_genus_classes(genus: str, proposed_classes: List[str]) -> None:
    """
    Validate that proposed output classes for a genus respect cryptic complex
    constraints. Raise an AssertionError if individual complex members are
    included as separate classes.

    Parameters
    ----------
    genus : str
        Genus name: "Anopheles", "Culex", or "Aedes"
    proposed_classes : list of str
        Proposed output class names for the specialist classifier

    Raises
    ------
    AssertionError
        If any individual cryptic complex member is found as a separate class
    """
    if genus == "Anopheles":
        cryptic_map = ANOPHELES_CRYPTIC_COMPLEXES
        canonical_classes = set(ANOPHELES_CLASSES)
    elif genus == "Culex":
        cryptic_map = CULEX_CRYPTIC_COMPLEXES
        canonical_classes = set(CULEX_CLASSES)
    elif genus == "Aedes":
        cryptic_map = AEDES_CRYPTIC_COMPLEXES
        canonical_classes = set(AEDES_CLASSES)
    else:
        raise ValueError(f"Unknown genus: {genus}")

    proposed_set = set(proposed_classes)

    for complex_name, members in cryptic_map.items():
        # A cryptic-complex member must never appear as its own output class: it is
        # morphologically indistinguishable from its siblings and can only be resolved
        # by PCR. The parent complex being present does NOT license splitting a member
        # out — having both "An. gambiae complex" and "An. gambiae s.s." is a (partial)
        # split and is still a violation. (The earlier check wrongly permitted this,
        # only failing when the parent complex was entirely absent.)
        #
        # The sole exception: a member the canonical taxonomy explicitly sanctions as a
        # standalone, identifiable class (e.g. Cx. quinquefasciatus, which is both a
        # pipiens-complex member and a recognised class in CULEX_CLASSES). We exclude
        # canonical_classes from the forbidden set so those remain legal.
        forbidden_members = [m for m in members if m not in canonical_classes]
        illegal = [m for m in forbidden_members if m in proposed_set]
        assert not illegal, (
            f"ERROR: Cryptic complex member(s) {illegal} of '{complex_name}' found as "
            f"separate class(es) in {genus}. These are morphologically indistinguishable "
            f"and cannot be resolved to species without molecular (PCR) confirmation. "
            f"SOLUTION: Represent them only via the complex class '{complex_name}'; "
            f"remove the individual member class(es)."
        )


def get_species_resolution_level(
    genus: str, predicted_class: str
) -> str:
    """
    Return the resolution level of a prediction based on whether it is a
    species, group, or complex.

    Parameters
    ----------
    genus : str
        The genus ("Anopheles", "Culex", "Aedes")
    predicted_class : str
        The predicted class name

    Returns
    -------
    str
        "species" if it is an individual species, "group" or "complex" if it is
        a cryptic assembly, or "unknown" if resolution cannot be determined.
    """
    if genus == "Anopheles":
        if predicted_class in ANOPHELES_CRYPTIC_COMPLEXES:
            return "complex"
        if predicted_class in ANOPHELES_CLASSES:
            return "species"
    elif genus == "Culex":
        if predicted_class in CULEX_CRYPTIC_COMPLEXES:
            return "complex"
        if predicted_class in CULEX_CLASSES:
            return "species"
    elif genus == "Aedes":
        if predicted_class in AEDES_CRYPTIC_COMPLEXES:
            return "complex"
        if predicted_class in AEDES_CLASSES:
            return "species"

    return "unknown"


# ========================================================================
# EXPORT: Complete taxonomy for downstream use
# ========================================================================

STAGE1_CLASSES = GENERA
STAGE1_CLASS_DICT = GENUS_CLASSES

STAGE2_TAXONOMY = {
    "Anopheles": {"classes": ANOPHELES_CLASSES, "class_dict": ANOPHELES_CLASS_DICT},
    "Culex": {"classes": CULEX_CLASSES, "class_dict": CULEX_CLASS_DICT},
    "Aedes": {"classes": AEDES_CLASSES, "class_dict": AEDES_CLASS_DICT},
}

if __name__ == "__main__":
    # Self-test: verify constraints are in place
    print("Stage 1 (Genus) classes:", STAGE1_CLASSES)
    print("\nStage 2 (Anopheles):", ANOPHELES_CLASSES)
    print("Anopheles cryptic complexes:", list(ANOPHELES_CRYPTIC_COMPLEXES.keys()))
    print("\nTesting validation...")
    validate_genus_classes("Anopheles", ANOPHELES_CLASSES)
    print("[OK] Anopheles class list is valid.")

    # Try to trigger the assertion (should fail)
    print("\nAttempting to add individual complex member 'An. gambiae s.s.' as a separate class...")
    try:
        bad_classes = ANOPHELES_CLASSES.copy()
        bad_classes.append("An. gambiae s.s.")
        validate_genus_classes("Anopheles", bad_classes)
        print("ERROR: Validation should have failed but did not!")
    except AssertionError as e:
        print("[OK] Validation correctly rejected individual complex member:")
        print(f"  {str(e)[:150]}...")
