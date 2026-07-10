"""
Advisory content for IVM Sentinel — two distinct, non-overlapping features:

1. generate_ai_intervention_response(df, query) — a real Gemini call grounded
   in the currently filtered surveillance DATASET. Used by the Operational
   Advisory tab. Never invents data not present in the dataframe.

2. get_taxon_specific_advisory(triage_result, life_stage) — a deterministic,
   citation-backed reference lookup keyed off a SINGLE specimen's
   identification result. Not AI-generated; a fixed, WHO/literature-grounded
   advisory table. Available for optional display next to identification
   results.
"""

import pandas as pd

from utils.config import GEMINI_API_KEY

# =============================================================================
# 1. DATASET-GROUNDED AI BRIEFING (Operational Advisory tab)
# =============================================================================
_SYSTEM_INSTRUCTION = (
    "You are a senior medical entomologist and integrated vector management "
    "operations advisor. Given a summary of zone-level vector surveillance "
    "data, write a concise, actionable operational briefing. Be specific "
    "about which zones need attention and why, referencing the actual "
    "numbers provided. Do not invent data that wasn't given to you. Where "
    "the evidence is insufficient to support a recommendation, say so "
    "rather than speculating."
)


def generate_ai_intervention_response(df: pd.DataFrame, query: str = "") -> str:
    if not GEMINI_API_KEY:
        return (
            "GEMINI_API_KEY is not configured. Add it via the Secrets "
            "Management console to enable AI-generated operational briefings."
        )
    if df is None or df.empty:
        return "No surveillance data is currently loaded — nothing to brief on."

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    data_summary = (
        f"Records: {len(df)}\n"
        f"Zones: {df['Zone_Name'].nunique() if 'Zone_Name' in df.columns else 'N/A'}\n"
        f"Columns: {list(df.columns)}\n"
        f"Summary statistics:\n{df.describe(include='all').to_string()}\n"
    )
    focus = query.strip() if query else "General situational briefing for the current dataset."

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"{data_summary}\n\nOperational question / focus: {focus}")],
                )
            ],
            config=types.GenerateContentConfig(
                system_instruction=_SYSTEM_INSTRUCTION,
                temperature=0.3,
            ),
        )
        return response.text
    except Exception as e:
        return f"Advisory generation failed: {e}"


# =============================================================================
# 2. STATIC, CITATION-BACKED TAXON ADVISORY (per-specimen reference content)
# =============================================================================
def generate_epidemiological_advisory(triage_result: dict, life_stage: str = "adult") -> dict:
    advisory = {
        "threat_level": "LOW",
        "action_required": "Routine Surveillance",
        "molecular_triage_protocol": None,
        "vector_control_intervention": "Standard monitoring and community source reduction.",
        "epidemiological_context": "",
        "ecological_notes": "",
    }

    if not triage_result:
        advisory["epidemiological_context"] = "No diagnostic criteria provided. Awaiting triage input."
        return advisory

    resolved_name = triage_result.get("resolved_taxonomic_name", triage_result.get("name", triage_result.get("best_match", ""))).lower()
    genus_name = triage_result.get("genus", "").lower()
    is_invasive = triage_result.get("biosecurity_alert", triage_result.get("invasive_alert", triage_result.get("invasive_species_alert", False)))
    requires_pcr = triage_result.get("molecular_confirmation_recommended", triage_result.get("molecular_id_required", False))

    if life_stage == "adult":
        if "gambiae" in resolved_name:
            advisory.update({
                "threat_level": "CRITICAL",
                "action_required": "MANDATORY PCR TRIAGE & RESISTANCE SCREENING",
                "molecular_triage_protocol": "Execute Scott et al. (1993) PCR assay to differentiate sibling species (gambiae s.s., coluzzii, arabiensis).",
                "vector_control_intervention": "Deploy LLINs and evaluate for pyrethroid/PBO resistance phenotypes. Assess IRS feasibility.",
                "epidemiological_context": (
                    "The Anopheles gambiae complex contains the most highly anthropophilic and efficient "
                    "malaria vectors in sub-Saharan Africa. Sibling species differ in biting behavior — "
                    "resolving the complex via molecular tools is necessary to target control correctly."
                ),
                "ecological_notes": (
                    "An. gambiae s.s. favors temporary rain pools; An. coluzzii favors permanent, man-made "
                    "water; An. arabiensis is arid-adapted with zoophilic tendency."
                ),
            })
        elif "funestus" in resolved_name:
            advisory.update({
                "threat_level": "CRITICAL",
                "action_required": "MANDATORY MOLECULAR CHARACTERIZATION",
                "molecular_triage_protocol": "Run group-specific PCR assays to separate primary vectors from non-vector group members.",
                "vector_control_intervention": "Maintain high LLIN coverage; prioritize perennial IRS where endophilic biting is confirmed.",
                "epidemiological_context": (
                    "An. funestus s.s. sustains intense, long-lived transmission cycles, but morphological "
                    "mimics (An. leesoni, An. rivulorum) are often non-vectors — molecular segregation "
                    "prevents artificial inflation of vector indices."
                ),
                "ecological_notes": (
                    "Breeds in large, permanent, clean, vegetated water bodies. Often peaks in the dry season."
                ),
            })
        elif "stephensi" in resolved_name or (is_invasive and "anopheles" in resolved_name):
            advisory.update({
                "threat_level": "HIGH-ALERT BIOSECURITY EMERGENCY",
                "action_required": "IMMEDIATE VECTOR ISOLATION & NATIONAL NOTIFICATION",
                "molecular_triage_protocol": "Urgent COI barcoding and rapid multiplex PCR to confirm invasive strain lineage.",
                "vector_control_intervention": "Aggressive urban source reduction, larvicide domestic water tanks, container-covering campaigns.",
                "epidemiological_context": (
                    "An. stephensi is an Asian invasive malaria vector expanding through the Horn of Africa "
                    "and Nigeria, thriving in urban container habitats atypical for native Anopheles."
                ),
                "ecological_notes": (
                    "Breeds in man-made overhead tanks, cisterns, wells, and containers — mirroring Aedes "
                    "aegypti's urban niche."
                ),
            })
        elif "aegypti" in resolved_name:
            advisory.update({
                "threat_level": "HIGH",
                "action_required": "Arboviral Risk Mapping & Source Reduction",
                "molecular_triage_protocol": "Routine surveillance; monitor for kdr resistance mutations if insecticide use is planned.",
                "vector_control_intervention": "Eliminate domestic breeding sites; targeted larvicides and community source reduction.",
                "epidemiological_context": (
                    "Primary urban vector of Dengue, Zika, Chikungunya, and urban Yellow Fever. Daytime "
                    "biting renders bed nets ineffective for this vector."
                ),
                "ecological_notes": (
                    "Domestic form (aegypti aegypti) breeds indoors; sylvatic form (aegypti formosus) uses "
                    "forest canopies and tree holes."
                ),
            })
        elif "albopictus" in resolved_name:
            advisory.update({
                "threat_level": "HIGH-ALERT BIOSECURITY SURVEILLANCE",
                "action_required": "Range Expansion Tracking & Inter-Sectoral Response",
                "molecular_triage_protocol": "Confirm via scutum stripe pattern; COI barcoding if geographic anomalies occur.",
                "vector_control_intervention": "Tire-depot cleanups, targeted space spraying, ULV insecticidal fogging.",
                "epidemiological_context": (
                    "Invasive Asian Tiger mosquito expanding into West/Central African forest fringes and "
                    "urban ecotones; a potent bridge vector for Dengue and Chikungunya."
                ),
                "ecological_notes": "Uses natural and artificial containers; strong affinity for tire dumps and peri-urban vegetation.",
            })
        elif "pipiens" in resolved_name or "culex" in resolved_name:
            advisory.update({
                "threat_level": "MEDIUM",
                "action_required": "Nuisance Index Mitigation & Arbovirus Screening",
                "molecular_triage_protocol": "Male terminalia dissection or molecular markers to separate quinquefasciatus from pipiens s.s. in sympatric zones.",
                "vector_control_intervention": "Improve sanitation, clear drainage, apply larvicidal oils or Bti/Bs, fix septic defects.",
                "epidemiological_context": (
                    "Principal urban nuisance biter; primary vector for Lymphatic Filariasis, and a vector "
                    "for West Nile Virus and Rift Valley Fever."
                ),
                "ecological_notes": "Hyper-adapted to organically polluted water — pit latrines, broken sewers, greywater.",
            })

    elif life_stage == "larva":
        if "anopheles" in genus_name:
            advisory.update({
                "threat_level": "HIGH",
                "action_required": "Larval Source Surveying (LSM)",
                "vector_control_intervention": "Map breeding sites via GIS; environmental management or Bti application.",
                "epidemiological_context": "Indicates active anopheline breeding; proximity to dwellings raises local malaria risk.",
                "ecological_notes": "No respiratory siphon; feeds horizontally at the surface in clean, unpolluted water.",
            })
        elif triage_result.get("biocontrol_indicator") or "tigripes" in resolved_name:
            advisory.update({
                "threat_level": "BENIGN (ECO-FRIENDLY INDICATOR)",
                "action_required": "Conservation of Natural Biocontrol Agents",
                "vector_control_intervention": "Suspend broad-spectrum larvicide in this water body to protect this predator.",
                "epidemiological_context": "Culex tigripes does not bite humans; its larvae prey on vector larvae.",
                "ecological_notes": "Large, striped larvae with raptorial mouthparts adapted for predation.",
            })
        elif "culex" in genus_name:
            advisory.update({
                "threat_level": "MEDIUM",
                "action_required": "Sanitation & Drainage Remediation",
                "vector_control_intervention": "Desilt drains, treat septic tanks, community sanitation.",
                "epidemiological_context": "High density indicates organic pollution and elevated Filariasis/WNV risk.",
                "ecological_notes": "Long, multi-tufted siphon at an angle; tolerant of high organic loads.",
            })
        elif "aedes" in genus_name:
            advisory.update({
                "threat_level": "HIGH",
                "action_required": "Ecology-Targeted Larval Control",
                "vector_control_intervention": "Source reduction for containers; pre-flood larvicides for floodwater zones.",
                "epidemiological_context": "Mass hatches (e.g. Ae. mcintoshi) after rainfall can trigger Rift Valley Fever outbreaks.",
                "ecological_notes": "Short, stout siphon, near-vertical hang. Eggs desiccation-resistant for years.",
            })

    if requires_pcr and not advisory["molecular_triage_protocol"]:
        advisory["molecular_triage_protocol"] = "Specimen resides within a cryptic complex. Forward to reference laboratory for PCR or COI sequencing."

    return advisory


def format_advisory_to_markdown(advisory_dict: dict) -> str:
    threat = advisory_dict["threat_level"]
    badge_color = "🔴" if ("CRITICAL" in threat or "HIGH-ALERT" in threat) else "🟡" if "HIGH" in threat else "🟢"

    return f"""
## {badge_color} Epidemiological Advisory Status: {threat}
---
### Required Action Protocol
> **{advisory_dict['action_required']}**

### Molecular Triage Protocol
* {advisory_dict['molecular_triage_protocol'] or 'No specialized molecular validation required for macro field triage.'}

### Integrated Vector Management (IVM) Intervention
* {advisory_dict['vector_control_intervention']}

---
### Epidemiological Context
{advisory_dict['epidemiological_context']}

### Vector Bionomics & Ecological Notes
{advisory_dict['ecological_notes']}
""".strip()


def get_taxon_specific_advisory(triage_result: dict, life_stage: str = "adult") -> str:
    """Convenience one-shot: run the lookup and return ready-to-render markdown."""
    advisory = generate_epidemiological_advisory(triage_result, life_stage=life_stage)
    return format_advisory_to_markdown(advisory)
