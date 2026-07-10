"""
Gemini Vision-based screening for adult and larval mosquito specimen photos,
with a deterministic taxonomic guardrail layer.

Design: Gemini analyzes the actual image and returns its raw best guess plus
observed features — it is NEVER trusted to decide on its own whether that
guess crosses into a cryptic species complex, or which citation applies.
A small controlled taxonomy table (mirroring utils/morphology_keys.py and
utils/pcr_and_accuracy.py) intercepts the raw guess and enforces the correct
complex/group-level ceiling, molecular-confirmation flag, and citation.

This is a screening aid, not a validated diagnostic device.
"""

import json

from utils.config import GEMINI_API_KEY

# ── Controlled taxonomy tables — never inferred by the model, always looked up ──
_CRYPTIC_COMPLEXES = {
    "gambiae_complex": {
        "match_terms": ["gambiae", "coluzzii", "arabiensis", "merus", "melas", "quadriannulatus", "bwambae"],
        "resolved_name": "Anopheles gambiae complex (s.l.)",
        "molecular_confirmation_recommended": True,
        "invasive_species_alert": False,
        "citation": "Coetzee, M. (2020). Key to the females of Afrotropical Anopheles mosquitoes. Malaria Journal, 19, 70.",
    },
    "funestus_group": {
        "match_terms": ["funestus", "rivulorum", "leesoni", "parensis", "vaneedeni"],
        "resolved_name": "Anopheles funestus group",
        "molecular_confirmation_recommended": True,
        "invasive_species_alert": False,
        "citation": "Gillies, M.T. & Coetzee, M. (1987). A Supplement to the Anophelinae of Africa South of the Sahara.",
    },
    "pipiens_complex": {
        "match_terms": ["pipiens", "quinquefasciatus"],
        "resolved_name": "Culex pipiens complex",
        "molecular_confirmation_recommended": True,
        "invasive_species_alert": False,
        "citation": "Jupp, P.G. (1996). Mosquitoes of Southern Africa: Culicinae and Toxorhynchitinae.",
    },
}

_FIELD_DIAGNOSTIC_SPECIES = {
    "stephensi": {
        "resolved_name": "Anopheles stephensi (Invasive Strain)",
        "molecular_confirmation_recommended": True,   # field marker is distinctive, but biosecurity stakes still warrant lab confirmation
        "invasive_species_alert": True,
        "citation": "Coetzee, M. (2020). Key to the females of Afrotropical Anopheles mosquitoes. Malaria Journal, 19, 70.",
    },
    "aegypti": {
        "resolved_name": "Aedes aegypti",
        "molecular_confirmation_recommended": False,
        "invasive_species_alert": False,
        "citation": "Service, M.W. (1990). Handbook to the Afrotropical Toxorhynchitine and Culicine Mosquitoes.",
    },
    "albopictus": {
        "resolved_name": "Aedes albopictus (Invasive Asian Tiger)",
        "molecular_confirmation_recommended": False,
        "invasive_species_alert": True,
        "citation": "Jupp, P.G. (1996). Mosquitoes of Southern Africa: Culicinae and Toxorhynchitinae.",
    },
}

_EDWARDS_FALLBACK_CITATION = "Edwards, F.W. (1941). Mosquitoes of the Ethiopian Region III."


# ── Gemini prompts — ask only for raw observation, never for the final ruling ──
_ADULT_RAW_PROMPT = """You are screening a photo of an adult mosquito specimen from
sub-Saharan Africa. Describe only what you can actually observe in THIS image.

Respond ONLY with valid JSON, no markdown fences, no extra text:
{
  "raw_best_guess": "your best-guess genus, species, or complex name based on visible features — be specific if you can, this will be checked against known taxonomy afterward",
  "genus_guess": "Anopheles | Culex | Aedes | Uncertain",
  "image_quality_ok": true or false,
  "key_features_observed": ["string", "string"],
  "raw_caveats": "honest statement of what could not be determined from this image (angle, focus, missing body parts, etc.)"
}
"""

_LARVAL_RAW_PROMPT = """You are screening a photo of a mosquito larva from sub-Saharan
Africa. Larval species identification from a photo is NOT reliable — restrict your
guess to GENUS level only, based on resting posture and respiratory siphon shape.
Anopheles larvae float parallel to the surface (no siphon). Culex larvae hang at an
angle with a long, slender, multi-tufted siphon. Aedes larvae hang at an angle with a
short, stout siphon (usually one tuft pair). If the larva is unusually large and
strikingly striped with raptorial mouthparts, note that — it may be the predatory,
harmless Culex tigripes rather than a vector.

Respond ONLY with valid JSON, no markdown fences, no extra text:
{
  "genus_guess": "Anopheles | Culex | Aedes | Uncertain",
  "possible_tigripes": true or false,
  "image_quality_ok": true or false,
  "key_features_observed": ["string"],
  "raw_caveats": "string"
}
"""


def _parse_json_response(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:]
    return json.loads(cleaned.strip())


def _call_gemini_vision(image_bytes: bytes, mime_type: str, prompt: str) -> dict:
    if not GEMINI_API_KEY:
        return {
            "error": (
                "GEMINI_API_KEY is not configured. Add it via the Secrets "
                "Management console to enable AI-assisted photo screening."
            )
        }

    from google import genai
    from google.genai import types

    client = genai.Client(api_key=GEMINI_API_KEY)

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
                        types.Part.from_text(text=prompt),
                    ],
                )
            ],
            config=types.GenerateContentConfig(temperature=0.1),
        )
        return _parse_json_response(response.text)
    except json.JSONDecodeError:
        return {"error": "AI response could not be parsed. Try a clearer, well-lit, lateral-view photo."}
    except Exception as e:
        return {"error": f"Vision inference failed: {e}"}


# ── Guardrail layer — the only thing allowed to decide taxonomic ruling ──
def _apply_adult_guardrails(raw: dict) -> dict:
    if not raw.get("image_quality_ok", True):
        return {
            "best_match": "Uncertain",
            "confidence_tier": "Insufficient image quality",
            "molecular_confirmation_recommended": True,
            "invasive_species_alert": False,
            "key_features_observed": raw.get("key_features_observed", []),
            "caveats": raw.get("raw_caveats", "Image quality was insufficient for reliable screening."),
        }

    guess = str(raw.get("raw_best_guess", "")).lower()

    for entry in _FIELD_DIAGNOSTIC_SPECIES.values():
        # checked before complexes: these are genuinely diagnostic single species
        pass
    for key, entry in _FIELD_DIAGNOSTIC_SPECIES.items():
        if key in guess:
            return {
                "best_match": entry["resolved_name"],
                "confidence_tier": "Indicative — photo screening only",
                "molecular_confirmation_recommended": entry["molecular_confirmation_recommended"],
                "invasive_species_alert": entry["invasive_species_alert"],
                "key_features_observed": raw.get("key_features_observed", []),
                "caveats": raw.get("raw_caveats", ""),
                "citation": entry["citation"],
            }

    for entry in _CRYPTIC_COMPLEXES.values():
        if any(term in guess for term in entry["match_terms"]):
            return {
                "best_match": entry["resolved_name"],
                "confidence_tier": "Group-level match",
                "molecular_confirmation_recommended": entry["molecular_confirmation_recommended"],
                "invasive_species_alert": entry["invasive_species_alert"],
                "key_features_observed": raw.get("key_features_observed", []),
                "caveats": (
                    (raw.get("raw_caveats", "") + " ") if raw.get("raw_caveats") else ""
                ) + (
                    f"Model's raw guess ('{raw.get('raw_best_guess')}') belongs to a "
                    "morphologically indistinguishable complex — reported at complex "
                    "level per standard protocol. PCR required for species-level ID."
                ),
                "citation": entry["citation"],
            }

    # No known complex/species match — stay honestly at genus level.
    genus_guess = raw.get("genus_guess", "Uncertain")
    return {
        "best_match": f"{genus_guess} (genus-level only)" if genus_guess != "Uncertain" else "Uncertain",
        "confidence_tier": "Genus-level only",
        "molecular_confirmation_recommended": True,
        "invasive_species_alert": False,
        "key_features_observed": raw.get("key_features_observed", []),
        "caveats": raw.get("raw_caveats", "Could not resolve past genus level from this image."),
        "citation": _EDWARDS_FALLBACK_CITATION,
    }


def _apply_larval_guardrails(raw: dict) -> dict:
    if not raw.get("image_quality_ok", True):
        return {
            "genus": "Uncertain",
            "confidence_tier": "Insufficient image quality",
            "key_features_observed": raw.get("key_features_observed", []),
            "caveats": raw.get("raw_caveats", "Image quality was insufficient for reliable screening."),
        }

    genus_guess = raw.get("genus_guess", "Uncertain")
    if genus_guess not in {"Anopheles", "Culex", "Aedes"}:
        genus_guess = "Uncertain"

    caveats = raw.get("raw_caveats", "")
    if raw.get("possible_tigripes") and genus_guess == "Culex":
        caveats = (
            (caveats + " ") if caveats else ""
        ) + (
            "Possible Culex tigripes — a large, striped, predatory larva that is "
            "harmless to humans and preys on vector larvae. Confirm before treating "
            "this site as a pest population."
        )

    return {
        "genus": genus_guess,
        "confidence_tier": "Genus-level only" if genus_guess != "Uncertain" else "Insufficient image quality",
        "key_features_observed": raw.get("key_features_observed", []),
        "caveats": caveats,
    }


# ── Public entry points — same names/signatures diagnostics.py already calls ──
def process_adult_image_inference(image_file) -> dict:
    if not image_file:
        return {"error": "No image was uploaded."}
    raw = _call_gemini_vision(image_file.getvalue(), image_file.type or "image/jpeg", _ADULT_RAW_PROMPT)
    if "error" in raw:
        return raw
    return _apply_adult_guardrails(raw)


def process_larval_image_inference(image_file) -> dict:
    if not image_file:
        return {"error": "No image was uploaded."}
    raw = _call_gemini_vision(image_file.getvalue(), image_file.type or "image/jpeg", _LARVAL_RAW_PROMPT)
    if "error" in raw:
        return raw
    return _apply_larval_guardrails(raw)
