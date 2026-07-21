"""
AI-Assisted Diagnostics & Identification component.

Adult flow: genus-first triage (GENUS_TRIAGE_MATRIX) → optional species-level
marker narrowing (search_species_reference against the 60-species catalog).
Larval flow: genus screening via evaluate_larval_triage.
Both stages cap results honestly — Undetermined stays Undetermined, complex
members stay complex-level, never a forced single species guess.
"""

import hashlib
import uuid

import pandas as pd
import streamlit as st

from utils.ai_advisory import generate_ai_intervention_response
from utils.classifier_inference import classifier_status, process_adult_image_classification
from utils.data_manager import (
    attach_identification_to_specimen,
    extract_primary_genus,
    load_specimen_records,
    specimens_pending_identification,
    upload_specimen_photo,
)
from utils.ecological_context import (
    complex_for_taxon,
    habitat_options,
    region_options,
)
from utils.ecological_context import (
    estimate as estimate_ecological_probability,
)
from utils.logging_config import get_logger
from utils.morphology_keys import (
    ANOPHELES_KEY_ROOT,
    GENUS_TRIAGE_MATRIX,
    SPECIES_CATALOG,
    anopheles_key_node,
    anopheles_key_step,
    evaluate_genus_triage,
    evaluate_larval_deepkey,
    get_aedes_character_schema,
    get_anopheles_character_schema,
    get_culex_character_schema,
    get_larval_character_schema,
    identify_aedes_species,
    identify_anopheles_species,
    identify_culex_species,
    match_larval_morphology,
    search_species_reference,
)
from utils.specimen_submission import submit_screening_result
from utils.vision_inference import process_adult_image_inference, process_larval_image_inference

logger = get_logger(__name__)

_TIER_COLOR = {
    "Indicative — photo screening only": "#D97706",
    "Group-level match":                 "#0369A1",
    "Genus-level only":                  "#64748B",
    "Insufficient image quality":        "#DC2626",
    "High Confidence Genus Triage":      "#16A34A",
    "Inconclusive":                      "#DC2626",
}

_NEUTRAL_TRAIT_KEYS = [
    "resting_posture", "wing_scales", "scutum_pattern",
    "postspiracular_setae", "body_color",
]

_TRAIT_LABELS = {
    "resting_posture":       "Resting Posture",
    "wing_scales":           "Wing Scale Pattern",
    "scutum_pattern":        "Scutum (Thorax) Pattern",
    "postspiracular_setae":  "Postspiracular Setae",
    "body_color":            "General Body Color",
    "female_palps":          "Female Palp Length",
    "male_palps":            "Male Palp Length / Shape",
    "female_abdomen_tip":    "Female Abdomen Tip",
}

_NOT_OBSERVED = "Not observed / Unsure"


def _badge(text: str, color: str) -> str:
    return (
        f'<span style="background:{color}1A; color:{color}; padding:3px 10px; '
        f'border-radius:20px; font-size:12px; font-weight:700; margin-right:6px; '
        f'display:inline-block; margin-bottom:4px;">{text}</span>'
    )


def _trait_options(key: str) -> list[str]:
    values = sorted({
        GENUS_TRIAGE_MATRIX[g][key]
        for g in GENUS_TRIAGE_MATRIX
        if key in GENUS_TRIAGE_MATRIX[g]
    })
    return values + [_NOT_OBSERVED]


def _all_species_markers() -> list[str]:
    markers = set()
    for species_list in SPECIES_CATALOG.values():
        for sp in species_list:
            markers.update(sp.get("field_markers", []))
    return sorted(markers)


def _render_genus_result(triage: dict):
    genus = triage.get("genus", "Undetermined")
    confidence = triage.get("confidence", 0)

    if genus == "Undetermined":
        st.warning(
            f"**Genus: Undetermined** (confidence {confidence}%). "
            f"{triage.get('reason', '')} This can genuinely happen with partial "
            "field observations — fill in more traits, or consult the full "
            "dichotomous key / submit for PCR."
        )
        return None

    st.markdown(
        f"""
        <div style="border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px;
                    background:white; margin-bottom:14px;">
            <div style="font-size:13px; color:#64748B; font-weight:600;">Resolved Genus</div>
            <div style="font-size:24px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{genus}</div>
            {_badge(f"Confidence: {confidence}%", "#0369A1")}
            <div style="font-size:13px; color:#475569; margin-top:8px;">{triage.get('reason','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    return genus


def _render_species_candidates(candidates: list[dict], markers_ticked: bool):
    if not candidates:
        if markers_ticked:
            st.info(
                "Genus resolved, but none of the ticked markers matched a "
                "specific species/complex in the catalog. Try different markers, "
                "or this specimen may need the full couplet key."
            )
        else:
            st.info(
                "Genus resolved. Tick specific field markers above to narrow "
                "this down to species/complex candidates."
            )
        return

    for c in candidates[:6]:
        border = "#DC2626" if c.get("biosecurity_alert") else "#E2E8F0"
        badges = ""
        if c.get("biosecurity_alert"):
            badges += _badge("⚠️ Biosecurity alert", "#DC2626")
        if c.get("biocontrol_indicator"):
            badges += _badge("🎉 Biocontrol indicator — not a vector", "#16A34A")
        badges += (
            _badge("Group/complex — PCR required", "#D97706")
            if c.get("molecular_id_required")
            else _badge("Field-indicative", "#16A34A")
        )

        group = c.get("group_complex", "None")
        group_line = f'<div style="font-size:12px; color:#64748B;">Complex/Group: {group}</div>' if group and group != "None" else ""

        st.markdown(
            f"""
            <div style="border:1px solid {border}; border-radius:12px; padding:16px 18px;
                        margin-bottom:12px; background:white;">
                <div style="display:flex; justify-content:space-between; align-items:start; gap:12px;">
                    <span style="font-size:16px; font-weight:700; color:#0F172A;">{c['species_name']}</span>
                    <span style="font-size:12px; color:#64748B; white-space:nowrap;">match score: {c['match_score']}</span>
                </div>
                {group_line}
                <div style="margin:8px 0;">{badges}</div>
                <div style="font-size:13px; color:#475569; line-height:1.5;">{c['field_diagnostic_notes']}</div>
                <div style="font-size:12px; color:#64748B; margin-top:6px;"><em>{c['vector_status']}</em></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if len(candidates) > 6:
        st.caption(f"+{len(candidates) - 6} more species in this genus with lower or no marker matches.")

    st.caption(
        "🔬 Species/complex narrowing is based on marker overlap with the 60-species "
        "reference catalog (Coetzee 2020; Gillies & Coetzee 1987; Service 1990; Jupp 1996) "
        "— not a substitute for the full dichotomous key. Any group/complex result "
        "requires PCR for species-level confirmation."
    )


def _render_vision_result(result: dict, is_larval: bool = False):
    if "error" in result:
        st.error(result["error"])
        return

    tier  = result.get("confidence_tier", "Insufficient image quality")
    color = _TIER_COLOR.get(tier, "#64748B")

    if result.get("invasive_species_alert"):
        st.error(
            f"⚠️ Possible invasive species flagged: **{result.get('best_match', 'Unknown')}** "
            "— preserve specimen and report immediately."
        )

    label = "Genus" if is_larval else "Best Match"
    value = result.get("genus") if is_larval else result.get("best_match", "Uncertain")
    mol_badge = (
        _badge("PCR confirmation recommended", "#D97706")
        if result.get("molecular_confirmation_recommended") else ""
    )

    st.markdown(
        f"""
        <div style="border:1px solid #E2E8F0; border-radius:12px; padding:18px;
                    background:white; margin-bottom:16px;">
            <div style="font-size:13px; color:#64748B; font-weight:600;">{label}</div>
            <div style="font-size:22px; font-weight:800; color:#0F172A; margin:4px 0 10px;">{value}</div>
            {_badge(tier, color)}{mol_badge}
        </div>
        """,
        unsafe_allow_html=True,
    )

    features = result.get("key_features_observed", [])
    if features:
        st.markdown("**Features the AI used:**")
        for f in features:
            st.markdown(f"- {f}")

    if result.get("caveats"):
        st.info(f"**Caveats:** {result['caveats']}")

    st.caption(
        "🤖 AI vision model — field screening aid only, not a validated "
        "diagnostic device. Confirm operationally important results with a "
        "trained entomologist and PCR where applicable."
    )


_RESOLUTION_STYLE = {
    "species":      ("#16A34A", "Species-level structural match"),
    "group":        ("#D97706", "Group-level — PCR required for species"),
    "complex":      ("#D97706", "Cryptic complex — PCR required for species"),
    "genus":        ("#64748B", "Genus-level only — add more characters"),
    "undetermined": ("#DC2626", "Undetermined"),
}


_ANOPHELES_ENGINE_CAPTION = (
    "🔬 Weighted character engine (Gillies & Coetzee 1987; Coetzee 2020). "
    "Cryptic complexes (*An. gambiae* complex, *An. funestus* group) are "
    "capped at complex/group level by design — only PCR splits them."
)


def _render_anopheles_identification(res: dict):
    """Render the weighted-character Anopheles verdict + per-candidate audit trail."""
    _render_character_identification(res, default_taxon="Anopheles spp.", caption=_ANOPHELES_ENGINE_CAPTION)


def _render_character_identification(res: dict, *, default_taxon: str, caption: str):
    """Render a weighted-character verdict + ranked candidate audit trail.

    Shared by the Anopheles, Culex and Aedes deep keys — they all return the
    same verdict shape from the character-agreement scorer, so the presentation
    (resolved taxon, badges, ranked candidates) is identical; only the fallback
    taxon label and the engine citation caption differ per genus.
    """
    resolution = res.get("resolution_level", "undetermined")
    color, tier_label = _RESOLUTION_STYLE.get(resolution, ("#64748B", resolution))

    badges = _badge(f"Confidence: {res.get('confidence',0)}%", "#0369A1") + _badge(tier_label, color)
    if res.get("molecular_id_required"):
        badges += _badge("PCR confirmation required", "#D97706")
    if res.get("biosecurity_alert"):
        badges += _badge("⚠️ Biosecurity alert", "#DC2626")

    # Assemble as flat, single-line HTML: a blank line (from an empty fragment)
    # would terminate Streamlit's raw-HTML block and make the rest render as an
    # escaped code block, so we join only non-empty parts with no newlines.
    inner = "".join(p for p in [
        '<div style="font-size:13px; color:#64748B; font-weight:600;">Resolved Taxon</div>',
        f'<div style="font-size:24px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{res.get("taxon", default_taxon)}</div>',
        f'<div style="margin:2px 0 6px;">{badges}</div>',
        f'<div style="font-size:13px; color:#475569; margin-top:8px;">{res.get("reason","")}</div>',
        f'<div style="font-size:12px; color:#64748B; margin-top:6px;"><strong>Next step:</strong> {res.get("next_step","")}</div>',
    ] if p)
    st.markdown(
        f'<div style="border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px; '
        f'background:white; margin-bottom:14px;">{inner}</div>',
        unsafe_allow_html=True,
    )

    members = res.get("complex_members")
    if members and len(members) > 1:
        st.caption("Members of this taxon (all morphologically inseparable): " + ", ".join(members))

    candidates = res.get("candidates", [])
    if candidates:
        st.markdown("**Ranked candidates (weighted character agreement):**")
        for c in candidates:
            compared = c.get("characters_compared", 0)
            matched = c.get("characters_matched", 0)
            contra = c.get("characters_contradicted", 0)
            disc = "".join(f'<div style="margin-top:3px;">• {d}</div>' for d in c.get("discriminators", []))
            disc_block = f'<div style="color:#475569; font-size:12px; margin-top:6px;">{disc}</div>' if disc else ""
            complex_txt = c.get("complex", "None") if c.get("complex") not in (None, "None") else "No complex"
            contra_txt = f" · ⚠ {contra} contradicting" if contra else ""
            inner = "".join([
                '<div style="display:flex; justify-content:space-between; gap:10px; align-items:baseline;">'
                f'<span style="font-size:15px; font-weight:700; color:#0F172A;">{c["species_name"]}</span>'
                f'<span style="font-size:12px; color:#0369A1; font-weight:700; white-space:nowrap;">{c["confidence"]}% · {matched}/{compared} chars</span>'
                "</div>",
                f'<div style="font-size:12px; color:#64748B; margin-top:2px;">{complex_txt} · '
                f'<em>{c.get("vector_status","Unknown")}</em>{contra_txt}</div>',
                disc_block,
            ])
            st.markdown(
                f'<div style="border:1px solid #E2E8F0; border-radius:10px; padding:12px 14px; '
                f'margin-bottom:8px; background:white;">{inner}</div>',
                unsafe_allow_html=True,
            )

    st.caption(caption)


def _render_key_terminal(result: dict):
    """Render a terminal outcome from the dichotomous couplet key."""
    resolution = result.get("resolution_level", "species")
    color, tier_label = _RESOLUTION_STYLE.get(resolution, ("#16A34A", resolution))

    badges = _badge(tier_label, color)
    if result.get("molecular_id_required"):
        badges += _badge("PCR required", "#D97706")
    if result.get("biosecurity_alert"):
        badges += _badge("⚠️ Biosecurity alert", "#DC2626")

    matched = result.get("matched_species")
    matched_line = (
        f'<div style="font-size:12px; color:#64748B; margin-top:4px;">Key terminated at: {matched}</div>'
        if matched and matched != result.get("taxon") else ""
    )
    disc = "".join(f'<div style="margin-top:4px;">• {d}</div>' for d in result.get("discriminators", []))
    disc_block = f'<div style="color:#475569; font-size:13px; margin-top:8px;">{disc}</div>' if disc else ""

    # Flat single-line HTML — omit empty parts so no blank line breaks the block.
    inner = "".join(p for p in [
        '<div style="font-size:13px; color:#64748B; font-weight:600;">Key Result</div>',
        f'<div style="font-size:22px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{result.get("taxon")}</div>',
        f'<div style="margin:2px 0 6px;">{badges}</div>',
        matched_line,
        disc_block,
        f'<div style="font-size:13px; color:#475569; margin-top:8px;">{result.get("notes","")}</div>',
        f'<div style="font-size:12px; color:#64748B; margin-top:6px;"><strong>Next step:</strong> {result.get("next_step","")}</div>',
    ] if p)
    st.markdown(
        f'<div style="border:1px solid {color}; border-radius:12px; padding:16px 18px; '
        f'background:white; margin-bottom:12px;">{inner}</div>',
        unsafe_allow_html=True,
    )
    st.caption(f"Vector status: {result.get('vector_status','Unknown')}")


def _render_anopheles_deep_key(target: str | None = None):
    """The two-tool Anopheles Deep Key section: character scoring + couplet walker."""
    st.markdown("#### Anopheles Deep Key")
    st.caption(
        "A dedicated adult-female *Anopheles* engine. Score any combination of "
        "diagnostic characters, or walk the dichotomous couplet key step by step. "
        "Both honour the cryptic-complex ceiling — gambiae-complex / funestus-group "
        "results stop at complex/group and are flagged for PCR."
    )

    tool = st.radio(
        "Tool",
        ["Character Scoring", "Interactive Couplet Key"],
        horizontal=True,
        key="anoph_tool",
    )
    st.markdown("---")

    if tool == "Character Scoring":
        col1, col2 = st.columns([5, 4])
        with col1:
            st.markdown("##### Observed characters")
            st.caption("Leave any character as *Not observed*. Wing (vein 6) and hind-tarsi characters carry the most weight.")
            schema = get_anopheles_character_schema()
            observed = {}
            for ch in schema:
                label_to_id = {s["label"]: s["id"] for s in ch["states"]}
                pick = st.selectbox(
                    f"{ch['label']}",
                    [_NOT_OBSERVED] + list(label_to_id.keys()),
                    key=f"anoph_char_{ch['id']}",
                )
                if pick != _NOT_OBSERVED:
                    observed[ch["id"]] = label_to_id[pick]
            run_id = st.button("Identify Anopheles", type="primary", width="stretch", key="anoph_identify")
        with col2:
            st.markdown("##### Result")
            # Compute on click but hold the result in session_state, so the Save button
            # below is still rendered on the rerun that its own click triggers. Rendered
            # only inside `if run_id:`, it would never see that click at all.
            if run_id and not observed:
                st.session_state.pop("anoph_char_result", None)
                st.info("Set at least one character on the left, then click **Identify Anopheles**.")
            elif run_id:
                with st.spinner("Scoring diagnostic characters…"):
                    st.session_state["anoph_char_result"] = identify_anopheles_species(observed)

            res = st.session_state.get("anoph_char_result")
            if res:
                _render_anopheles_identification(res)

                if res.get("resolution_level") not in ("undetermined", "genus"):
                    st.markdown("---")
                    _save_identification(
                        "💾 Save this Anopheles result",
                        "save_anoph_char",
                        "manual_checklist",
                        {
                            "genus_triage": {"genus": "Anopheles", "confidence": res.get("confidence", 0)},
                            "anopheles_deep_key": res,
                        },
                        target,
                        result_key="anoph_char_result",
                    )
            elif not run_id:
                st.info("Set characters on the left and click **Identify Anopheles**.")
        return

    # ── Interactive couplet key (stateful walker) ──────────────────────
    if "anoph_key_node" not in st.session_state:
        st.session_state["anoph_key_node"] = ANOPHELES_KEY_ROOT
    if "anoph_key_terminal" not in st.session_state:
        st.session_state["anoph_key_terminal"] = None
    if "anoph_key_trail" not in st.session_state:
        st.session_state["anoph_key_trail"] = []

    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown("##### Dichotomous couplet key — adult female *Anopheles*")
    with col2:
        if st.button("↺ Restart key", width="stretch", key="anoph_key_reset"):
            st.session_state["anoph_key_node"] = ANOPHELES_KEY_ROOT
            st.session_state["anoph_key_terminal"] = None
            st.session_state["anoph_key_trail"] = []

    trail = st.session_state["anoph_key_trail"]
    if trail:
        st.caption("Path: " + "  →  ".join(trail))

    terminal = st.session_state["anoph_key_terminal"]
    if terminal:
        _render_key_terminal(terminal)
        _save_identification(
            "💾 Save this key result",
            "save_anoph_key",
            "manual_checklist",
            {
                "genus_triage": {"genus": "Anopheles"},
                "anopheles_couplet_key": terminal,
            },
            target,
        )
        st.info("Click **↺ Restart key** to identify another specimen.")
        return

    node_id = st.session_state["anoph_key_node"]
    node = anopheles_key_node(node_id)
    if not node:
        st.error("Key state lost — click **↺ Restart key**.")
        return

    st.markdown(
        f'<div style="border-left:4px solid #0369A1; padding:8px 14px; margin:6px 0 12px; '
        f'background:#F8FAFC; border-radius:6px;"><span style="font-size:12px; color:#64748B; '
        f'font-weight:700;">COUPLET {node_id}</span><br><span style="font-size:15px; color:#0F172A; '
        f'font-weight:600;">{node["question"]}</span></div>',
        unsafe_allow_html=True,
    )

    for i, lead in enumerate(node["leads"]):
        if st.button(lead["text"], key=f"anoph_lead_{node_id}_{i}", width="stretch"):
            step = anopheles_key_step(node_id, i)
            st.session_state["anoph_key_trail"] = trail + [f"{node_id}{chr(97 + i)}"]
            if step["type"] == "couplet":
                st.session_state["anoph_key_node"] = step["node_id"]
            elif step["type"] == "terminal":
                st.session_state["anoph_key_terminal"] = step["result"]
            else:
                st.error(step.get("message", "Key error."))
            st.rerun()


_CULICINE_ENGINE_CAPTION = (
    "🔬 Weighted character engine (Service 1990; Jupp 1996; Edwards 1941). "
    "Cryptic taxa (*Culex pipiens* complex, Vishnui subgroup, *Cx. decens* group, "
    "*Ae. simpsoni* complex, furcifer–taylori & caballus–juppi) are capped at "
    "complex/group level — only PCR / genitalia split them."
)


def _render_culicine_deep_key(target: str | None = None):
    """Character-scoring deep key for adult *Culex* & *Aedes*, mirroring the
    Anopheles engine — same cryptic-complex ceiling and PCR flagging."""
    st.markdown("#### Culex / Aedes Deep Key")
    st.caption(
        "Score diagnostic characters for adult *Culex* or *Aedes*. Cryptic complexes / "
        "groups stop at complex/group level and are flagged for PCR — the engine never "
        "manufactures a single-species answer the morphology cannot support."
    )

    genus = st.radio("Genus", ["Culex", "Aedes"], horizontal=True, key="culicine_genus")
    st.markdown("---")

    if genus == "Culex":
        schema = get_culex_character_schema()
        identify = identify_culex_species
        default_taxon = "Culex spp."
    else:
        schema = get_aedes_character_schema()
        identify = identify_aedes_species
        default_taxon = "Aedes spp."

    result_key = f"culicine_result_{genus.lower()}"

    col1, col2 = st.columns([5, 4])
    with col1:
        st.markdown("##### Observed characters")
        st.caption("Leave any character as *Not observed*. Scutal pattern and proboscis banding carry the most weight.")
        observed = {}
        for ch in schema:
            label_to_id = {s["label"]: s["id"] for s in ch["states"]}
            pick = st.selectbox(
                ch["label"],
                [_NOT_OBSERVED] + list(label_to_id.keys()),
                key=f"culicine_{genus}_{ch['id']}",
            )
            if pick != _NOT_OBSERVED:
                observed[ch["id"]] = label_to_id[pick]
        run_id = st.button(f"Identify {genus}", type="primary", width="stretch", key=f"culicine_identify_{genus}")

    with col2:
        st.markdown("##### Result")
        # Compute on click, hold in session_state so the Save button survives the
        # rerun its own click triggers — same pattern as the Anopheles deep key.
        if run_id and not observed:
            st.session_state.pop(result_key, None)
            st.info(f"Set at least one character on the left, then click **Identify {genus}**.")
        elif run_id:
            with st.spinner("Scoring diagnostic characters…"):
                st.session_state[result_key] = identify(observed)

        res = st.session_state.get(result_key)
        if res:
            _render_character_identification(res, default_taxon=default_taxon, caption=_CULICINE_ENGINE_CAPTION)
            if res.get("resolution_level") not in ("undetermined", "genus"):
                st.markdown("---")
                _save_identification(
                    f"💾 Save this {genus} result",
                    f"save_culicine_{genus}",
                    "manual_checklist",
                    {
                        "genus_triage": {"genus": genus, "confidence": res.get("confidence", 0)},
                        "deep_key": res,
                    },
                    target,
                    result_key=result_key,
                )
        elif not run_id:
            st.info(f"Set characters on the left and click **Identify {genus}**.")


def _render_larval_deep_key(target: str | None = None):
    """Character deep key for 4th-instar larvae — resolves to GENUS only, with a
    Culex tigripes predator/biocontrol flag. Never claims larval species."""
    st.markdown("#### Larval Deep Key (4th instar)")
    st.caption(
        "Score larval characters to triage to GENUS. Wild larval species ID needs "
        "chaetotaxy slides or molecular assays, so this engine never claims species."
    )
    schema = get_larval_character_schema()

    col1, col2 = st.columns([5, 4])
    with col1:
        st.markdown("##### Observed characters")
        observed = {}
        for ch in schema:
            label_to_id = {s["label"]: s["id"] for s in ch["states"]}
            pick = st.selectbox(
                ch["label"],
                [_NOT_OBSERVED] + list(label_to_id.keys()),
                key=f"larval_deep_{ch['id']}",
            )
            if pick != _NOT_OBSERVED:
                observed[ch["id"]] = label_to_id[pick]
        run_id = st.button("Resolve larval genus", type="primary", width="stretch", key="larval_deep_resolve")

    with col2:
        st.markdown("##### Result")
        if run_id and not observed:
            st.session_state.pop("larval_deep_result", None)
            st.info("Set at least one character on the left, then click **Resolve larval genus**.")
        elif run_id:
            st.session_state["larval_deep_result"] = evaluate_larval_deepkey(observed)

        res = st.session_state.get("larval_deep_result")
        if res:
            genus = res.get("resolved_genus", "Undetermined")
            tier = res.get("confidence_tier", "")
            st.markdown(f"### {genus}")
            if tier:
                st.markdown(_badge(tier, _TIER_COLOR.get(tier, "#64748B")), unsafe_allow_html=True)
            if res.get("biocontrol_candidate"):
                st.markdown(_badge("🎉 Biocontrol candidate (Culex tigripes)", "#16A34A"), unsafe_allow_html=True)
            st.write(res.get("notes", ""))
            if res.get("next_step"):
                st.caption(f"Next step: {res['next_step']}")
            if res.get("resolution_level") != "undetermined":
                st.markdown("---")
                _save_identification(
                    "💾 Save this larval deep-key result",
                    "save_larval_deep",
                    "manual_checklist",
                    res,
                    target,
                    result_key="larval_deep_result",
                )
        elif not run_id:
            st.info("Set characters on the left and click **Resolve larval genus**.")


_NEW_SPECIMEN = "— New specimen (create a new record) —"


def _warn_if_poor_quality(uploaded) -> None:
    """Flag a photo the model will struggle with, before it produces a confident wrong answer.

    A blurry or badly exposed image does not make the vision model refuse — it makes it
    guess, and the guess reads exactly like a good one. The checks are local and cheap
    (blur, exposure, resolution), so run them and say so; the user may still screen the
    image, because a poor photo of an unmistakable specimen can still be worth screening.
    """
    try:
        from PIL import Image

        from utils.image_quality_control import assess_image_quality

        uploaded.seek(0)
        report = assess_image_quality(Image.open(uploaded))
    except Exception:
        logger.debug("Image quality assessment failed; screening anyway", exc_info=True)
        return
    finally:
        uploaded.seek(0)  # inference reads the stream from the start

    if not report.get("passed"):
        st.warning(
            f"**Image quality:** {report.get('reason', 'below the usual threshold')} "
            "The screening below may be unreliable — retake the photo if you can."
        )


def _screen_image_once(uploaded, cache_key: str, infer) -> dict:
    """Run vision inference once per uploaded image, reusing the result across reruns.

    st.file_uploader keeps its value across reruns, so calling `infer` unconditionally
    re-invokes the model on every interaction — including the rerun that a Save click
    triggers. The model is non-deterministic, so the result saved could differ from the
    one the user actually reviewed and approved. Key the result to the image's bytes:
    the same photo always yields the identification already on screen, and a new upload
    invalidates it.
    """
    digest = hashlib.sha256(uploaded.getvalue()).hexdigest()
    cached = st.session_state.get(cache_key)
    if cached and cached["digest"] == digest:
        return cached["result"]

    uploaded.seek(0)  # inference reads the stream; getvalue() above left it at the end
    with st.spinner("Running AI-assisted visual screening…"):
        result = infer(uploaded)
    st.session_state[cache_key] = {"digest": digest, "result": result}
    return result


def _pending_specimen_options() -> dict:
    """Map a human label -> specimen_id for every vialed-out individual still awaiting
    identification. These are the tubes a user physically has in hand."""
    pending = specimens_pending_identification(load_specimen_records())
    options = {}
    for row in pending.to_dict("records"):
        specimen_id = row.get("specimen_id")
        if not specimen_id:
            continue
        genus = extract_primary_genus(row.get("field_screening_result")) or "?"
        tube = row.get("tube_label") or str(specimen_id)[:8]
        options[f"{tube} · {genus} · {str(specimen_id)[:8]}"] = specimen_id
    return options


def _clear_specimen_link() -> None:
    """Drop the linked specimen. Safe only as a button callback or before the widgets
    are instantiated — Streamlit rejects writes to a widget's session_state entry once
    that widget exists on the current run."""
    st.session_state.pop("diag_specimen_scan", None)
    st.session_state.pop("diag_specimen_pick", None)


def _render_specimen_link() -> str | None:
    """Let the user attach this identification to an existing vialed-out specimen
    (scanned by QR / picked by tube label) instead of creating a new record.

    This is what keeps a subsampled specimen counted once: identifying a tube that
    already has a row must UPDATE that row, not insert a second one. Returns the
    target specimen_id, or None to create a new record.
    """
    # A successful save asks for the link to be dropped, but it can only be honoured
    # here — before the widgets are instantiated on this run.
    if st.session_state.pop("diag_clear_link_pending", False):
        _clear_specimen_link()

    options = _pending_specimen_options()
    choices = [_NEW_SPECIMEN] + list(options.keys())

    # A specimen stops being "pending" the moment it is identified, so its label leaves
    # `choices` while session_state still holds it — Streamlit raises on a stored value
    # that is no longer an option. Drop the stale pick before the widget is built.
    if st.session_state.get("diag_specimen_pick") not in choices:
        st.session_state.pop("diag_specimen_pick", None)

    linked = st.session_state.get("diag_linked_specimen")
    with st.expander(
        "🔗 Identifying a vialed specimen from a batch? (optional)",
        expanded=bool(linked),
    ):
        st.caption(
            "Specimens vialed out of a field-count batch already have a record and a QR "
            "label. Link one here and your result will be saved onto that specimen "
            "instead of creating a duplicate record. The link stays active until you "
            "clear it — check it matches the tube in your hand before saving."
        )
        scanned = st.text_input(
            "Scan or paste the specimen QR ID",
            key="diag_specimen_scan",
            placeholder="UUID from the tube's QR label",
        ).strip()

        picked_id = None
        if options:
            choice = st.selectbox(
                "…or pick a tube awaiting identification",
                choices,
                key="diag_specimen_pick",
            )
            picked_id = options.get(choice)
        else:
            st.caption("No vialed specimens are currently awaiting identification.")

        target = scanned or picked_id
        if target:
            st.button("✕ Clear link", key="diag_clear_link", on_click=_clear_specimen_link)
        return target


def _render_link_banner(target: str | None) -> None:
    """Show, on every run and outside the collapsed expander, which specimen the next
    save will overwrite. Saving onto the wrong tube silently replaces that specimen's
    identification, so this must not be hidden behind a closed expander."""
    if target:
        st.warning(
            f"🔗 Linked — saving any result below will overwrite the identification on "
            f"specimen **{str(target)[:8]}…**, not create a new record."
        )


def _save_identification(
    label: str,
    key: str,
    screening_method: str,
    result: dict,
    target: str | None,
    result_key: str | None = None,
    photos: list | None = None,
) -> None:
    """Render the save button for an identification result and route the write.

    Routes to attach_identification_to_specimen when `target` is a linked vialed-out
    specimen (so it is updated, not duplicated), otherwise creates a new record. Never
    reports success it didn't get — a failed write shows an error.

    `photos` are the images the identification was made from. They are uploaded to the
    specimen-photos bucket and stored on the row: an identification whose evidence was
    thrown away cannot be reviewed, and cannot be used to retrain anything.

    On success the scored result at `result_key` is dropped and the page reruns, so the
    panel resets. Without that, the (now working) button stays live on a result already
    written, and clicking it again inserts a second record for the same mosquito.
    """
    if not st.button(label, key=key):
        return

    photos = [p for p in (photos or []) if p is not None]

    if target:
        # Photos are filed under the specimen they belong to, which already exists here.
        photo_urls = [url for p in photos if (url := upload_specimen_photo(p, str(target)))]
        saved = attach_identification_to_specimen(
            specimen_id=target,
            screening_method=screening_method,
            result=result,
            photo_urls=photo_urls,
        )
        # attach_identification_to_specimen surfaces its own error on every failure path.
        if not saved:
            return
        # Drop the link too, so the next identification cannot silently overwrite the
        # specimen just saved.
        st.session_state["diag_clear_link_pending"] = True
        st.session_state["diag_save_message"] = (
            f"Identification saved onto specimen {str(target)[:8]}… — the link has been "
            f"cleared, so the next result will not overwrite it."
        )
    else:
        # The row does not exist yet, so fix its ID up front: the images are filed under
        # that ID in storage and must land on the row that ends up carrying them.
        new_specimen_id = str(uuid.uuid4()) if photos else None
        photo_urls = (
            [url for p in photos if (url := upload_specimen_photo(p, new_specimen_id))]
            if new_specimen_id
            else []
        )
        saved = submit_screening_result(
            screening_method=screening_method,
            result=result,
            photo_urls=photo_urls,
            specimen_id=new_specimen_id,
        )
        # submit_screening_result surfaces its own error on every failure path (not
        # configured, not signed in, insert rejected) — a generic message here would
        # paper over the specific reason it just showed the user.
        if not saved:
            return
        st.session_state["diag_save_message"] = f"Saved as specimen {saved['specimen_id']}"

    if result_key:
        st.session_state.pop(result_key, None)
    st.rerun()


# The views a mosquito's diagnostic features are actually visible from. Each is optional:
# a specimen photographed only dorsally still gets screened on what that view shows.
_ADULT_ANGLES = [
    ("dorsal", "Dorsal", "From above — scutum pattern and thoracic ornamentation"),
    ("lateral", "Lateral", "Side profile — palps, proboscis, abdomen"),
    ("wings", "Wings", "Wing scales and vein pattern"),
    ("legs", "Legs / tarsi", "Banding on the hind tarsi"),
]


def _render_single_photo_screening(target: str | None) -> None:
    col1, col2 = st.columns([4, 5])

    with col1:
        st.markdown("#### Upload Adult Specimen Photo")
        st.caption("Best results: lateral view, good lighting, in-focus palps/legs/wings.")
        uploaded_adult = st.file_uploader(
            "Adult image (JPG/PNG)", type=["jpg", "jpeg", "png"], key="adult_img_uploader"
        )
        if uploaded_adult:
            st.image(uploaded_adult, caption="Uploaded specimen", width="stretch")

    with col2:
        st.markdown("#### AI Screening Result")
        if uploaded_adult:
            _warn_if_poor_quality(uploaded_adult)
            result = _screen_image_once(
                uploaded_adult, "vision_adult_cache", process_adult_image_inference
            )
            _render_vision_result(result, is_larval=False)

            if "error" not in result:
                st.markdown("---")
                _save_identification(
                    "💾 Save this AI screening result",
                    "save_vision_adult",
                    "ai_vision",
                    result,
                    target,
                    photos=[uploaded_adult],
                )
        else:
            st.info("Upload a photo to run AI-assisted screening.")


def _render_classifier_result(result: dict) -> None:
    """Render a trained-classifier verdict: resolved taxon, confidence, and the
    resolution-level badge that keeps a cryptic complex from reading as a species."""
    if "error" in result:
        st.error(result["error"])
        return

    resolution = result.get("resolution_level", "genus")
    color, tier_label = _RESOLUTION_STYLE.get(resolution, ("#64748B", resolution))

    conf = result.get("confidence")
    badges = ""
    if conf is not None:
        badges += _badge(f"Confidence: {conf * 100:.0f}%", "#0369A1")
    badges += _badge(tier_label, color)
    if result.get("molecular_id_required"):
        badges += _badge("PCR confirmation required", "#D97706")
    if result.get("stage2_uncertain"):
        badges += _badge("Stage-2 uncertain → genus", "#64748B")

    taxon = result.get("predicted_species") or result.get("genus") or "Undetermined"
    inner = "".join(p for p in [
        '<div style="font-size:13px; color:#64748B; font-weight:600;">Predicted Taxon</div>',
        f'<div style="font-size:24px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{taxon}</div>',
        f'<div style="margin:2px 0 6px;">{badges}</div>',
    ] if p)
    st.markdown(
        f'<div style="border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px; '
        f'background:white; margin-bottom:14px;">{inner}</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "🤖 Two-stage EfficientNet-B0 classifier (models/). Stage-2 output classes are "
        "constrained so cryptic complexes (*An. gambiae* complex, *An. funestus* group) "
        "resolve only to the complex/group — never a bare member. PCR still splits them."
    )


_MONTHS = {
    "Unknown": 0, "January": 1, "February": 2, "March": 3, "April": 4, "May": 5,
    "June": 6, "July": 7, "August": 8, "September": 9, "October": 10,
    "November": 11, "December": 12,
}


def _pretty_member(name: str) -> str:
    """Prettify an estimator member epithet for display (gambiae_ss -> gambiae s.s.)."""
    return name.replace("_ss", " s.s.").replace("_", " ")


def _render_ecological_estimate(result: dict, key_prefix: str) -> dict | None:
    """Optional ecological-context panel for a COMPLEX-level result.

    Returns the computed estimate dict (so a caller can fold it into a saved
    record), or None when it doesn't apply or hasn't been run. Purely advisory:
    it estimates the likely complex *member* from where/when the specimen was
    collected and NEVER changes the complex verdict — PCR is still the only
    definitive split. Renders nothing for species/genus results or complexes the
    estimator has no rules for.
    """
    complex_name = complex_for_taxon(result.get("predicted_species"))
    if not complex_name:
        return None

    state_key = f"{key_prefix}_eco_estimate"
    with st.expander("🌍 Ecological context estimate (optional — not an identification)"):
        st.caption(
            "Estimate which complex member is most likely from where/when the specimen was "
            "collected. Guides field sampling and specimen prioritisation; PCR is still the "
            "only way to confirm the species."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            region = st.selectbox(
                "Region / country", ["Unknown"] + region_options(), key=f"{key_prefix}_eco_region"
            )
        with c2:
            habitat_labels = [h.replace("_", " ") for h in habitat_options()]
            habitat = st.selectbox(
                "Breeding site", ["Unknown"] + habitat_labels, key=f"{key_prefix}_eco_habitat"
            )
        with c3:
            month_name = st.selectbox("Collection month", list(_MONTHS), key=f"{key_prefix}_eco_month")

        if st.button("Estimate likely species", key=f"{key_prefix}_eco_run"):
            est = estimate_ecological_probability(
                complex_name,
                region=None if region == "Unknown" else region,
                habitat="unknown" if habitat == "Unknown" else habitat.replace(" ", "_"),
                month=_MONTHS[month_name],
            )
            st.session_state[state_key] = {"complex": complex_name, "estimate": est}

        stored = st.session_state.get(state_key)
        if not stored or stored["complex"] != complex_name:
            return None

        est = stored["estimate"]
        if "error" in est:
            st.info(est["error"])
            return None

        dist = est.get("probability_distribution", {})
        if dist:
            top = _pretty_member(next(iter(dist)))
            st.markdown(f"**Most likely member of {complex_name}:** {top}")
            for sp, prob in dist.items():
                st.markdown(
                    f'<div style="font-size:13px; color:#0F172A; margin-bottom:2px;">'
                    f'{_pretty_member(sp)} — <strong>{prob * 100:.0f}%</strong></div>',
                    unsafe_allow_html=True,
                )
                st.progress(min(1.0, max(0.0, float(prob))))
            with st.expander("Why these numbers?"):
                for sp, why in est.get("reasoning", {}).items():
                    st.caption(f"**{_pretty_member(sp)}** — {why}")
        st.warning(est.get("disclaimer", ""))
        return est


def _render_classifier_screening(target: str | None) -> None:
    """Trained-classifier screening: honest about availability, never fabricates.

    When torch or the .pth checkpoints are missing, this shows setup guidance
    instead of a dead button — the classifier is optional and separate from the
    deployed app (see models/README_CLASSIFIER_SETUP.md)."""
    st.markdown("#### Trained Classifier (two-stage CNN)")
    st.caption(
        "EfficientNet-B0 genus → species/complex pipeline. Optional and separate from "
        "the deployed app; enable it by installing the ML extras and training the model."
    )

    status = classifier_status()
    if not status["available"]:
        st.warning(status["reason"])
        st.caption("See **models/README_CLASSIFIER_SETUP.md** to train and place the checkpoints.")
        return

    missing = status.get("stage2_missing") or []
    if missing:
        st.info(
            "Species-stage checkpoints are missing for: " + ", ".join(missing) +
            " — specimens of those genera resolve to genus level only."
        )

    col1, col2 = st.columns([4, 5])
    with col1:
        st.markdown("#### Upload Adult Specimen Photo")
        st.caption("Best results: lateral view, good lighting, in-focus palps/legs/wings.")
        uploaded = st.file_uploader(
            "Adult image (JPG/PNG)", type=["jpg", "jpeg", "png"], key="clf_img_uploader"
        )
        if uploaded:
            st.image(uploaded, caption="Uploaded specimen", width="stretch")

    with col2:
        st.markdown("#### Classifier Result")
        if uploaded:
            _warn_if_poor_quality(uploaded)
            result = _screen_image_once(
                uploaded, "clf_adult_cache", process_adult_image_classification
            )
            _render_classifier_result(result)

            if "error" not in result:
                # Complex-level results can carry an optional ecological estimate of
                # the likely member; it's stored as provenance and never alters the
                # complex verdict (predicted_species / resolution_level are untouched).
                eco = _render_ecological_estimate(result, "clf")
                save_result = dict(result)
                if eco:
                    save_result["ecological_estimate"] = eco

                st.markdown("---")
                _save_identification(
                    "💾 Save this classifier result",
                    "save_clf_adult",
                    "trained_classifier",
                    save_result,
                    target,
                    photos=[uploaded],
                )
        else:
            st.info("Upload a photo to run the trained classifier.")


def _render_multi_angle_screening(target: str | None) -> None:
    """Screen several views of one specimen, one AI call per angle.

    The angles are screened SEPARATELY and every result is shown. They are not blended
    into a single verdict: the model reads one image at a time, and inventing a consensus
    across four independent guesses would be a claim the model never made. Where the
    angles disagree, that disagreement is itself the finding — it usually means the
    features are not clearly visible — and the user decides which view they trust.
    """
    st.caption(
        "Upload the views you have of **one specimen**. Each is screened on its own; "
        "you choose which result to record, and every image is stored with the record."
    )

    upload_col, result_col = st.columns([4, 5])

    uploads: dict[str, object] = {}
    with upload_col:
        st.markdown("#### Upload Angles")
        for angle_key, title, hint in _ADULT_ANGLES:
            uploaded = st.file_uploader(
                title, type=["jpg", "jpeg", "png"], key=f"adult_angle_{angle_key}", help=hint
            )
            if uploaded:
                uploads[angle_key] = uploaded
                st.image(uploaded, caption=title, width=180)

    with result_col:
        st.markdown("#### AI Screening Results")
        if not uploads:
            st.info("Upload at least one angle to run AI-assisted screening.")
            return

        results: dict[str, dict] = {}
        for angle_key, title, _ in _ADULT_ANGLES:
            uploaded = uploads.get(angle_key)
            if uploaded is None:
                continue
            _warn_if_poor_quality(uploaded)
            result = _screen_image_once(
                uploaded, f"vision_adult_{angle_key}_cache", process_adult_image_inference
            )
            with st.expander(f"{title} — {result.get('resolved_name') or 'no result'}", expanded=True):
                _render_vision_result(result, is_larval=False)
            if "error" not in result:
                results[angle_key] = result

        if not results:
            st.warning("No angle produced a usable screening result.")
            return

        st.markdown("---")
        titles = {key: title for key, title, _ in _ADULT_ANGLES}
        chosen_angle = st.selectbox(
            "Which view's result do you want to record?",
            options=list(results.keys()),
            format_func=lambda k: f"{titles[k]} — {results[k].get('resolved_name') or 'undetermined'}",
            key="adult_angle_choice",
            help=(
                "One identification is saved for this specimen. Pick the view whose "
                "diagnostic features you actually trust; all uploaded images are stored "
                "with it either way."
            ),
        )

        distinct = {r.get("resolved_name") for r in results.values()}
        if len(distinct) > 1:
            st.warning(
                "The angles disagree on this specimen. That usually means the diagnostic "
                "features are not clearly visible — treat the identification with caution, "
                "and prefer PCR confirmation."
            )

        _save_identification(
            "💾 Save this AI screening result",
            "save_vision_adult_multi",
            "ai_vision",
            results[chosen_angle],
            target,
            photos=list(uploads.values()),
        )


def render_diagnostics_page(active_df: pd.DataFrame | None = None):
    # Survives the rerun that resets the panel after a successful save.
    save_message = st.session_state.pop("diag_save_message", None)
    if save_message:
        st.success(save_message)

    target = _render_specimen_link()
    st.session_state["diag_linked_specimen"] = target
    _render_link_banner(target)

    tab1, tab2, tab3 = st.tabs([
        "Adult Identification",
        "Larval Identification",
        "Operational Advisory",
    ])

    # ── TAB 1: ADULT ──────────────────────────────────────────────────────
    with tab1:
        st.subheader("Adult Mosquito — Genus Triage & Species Narrowing")
        st.caption(
            "Step 1 resolves genus from macro-characters. Step 2 (optional) "
            "narrows to species/complex using specific field markers from the "
            "60-species Afrotropical reference catalog."
        )

        method = st.radio(
            "Identification method",
            ["Manual Character Checklist", "Anopheles Deep Key", "Culex / Aedes Deep Key",
             "AI Photo Screening", "Trained Classifier"],
            horizontal=True,
            key="adult_method",
        )
        st.markdown("---")

        if method == "Anopheles Deep Key":
            _render_anopheles_deep_key(target)

        elif method == "Culex / Aedes Deep Key":
            _render_culicine_deep_key(target)

        elif method == "Manual Character Checklist":
            col1, col2 = st.columns([5, 4])

            with col1:
                st.markdown("#### Step 1 — Genus Triage")
                sex = st.radio(
                    "Specimen Sex",
                    ["Female", "Male", "Unsure"],
                    horizontal=True,
                    key="adult_sex",
                )

                active_keys = list(_NEUTRAL_TRAIT_KEYS)
                if sex == "Female":
                    active_keys += ["female_palps", "female_abdomen_tip"]
                elif sex == "Male":
                    active_keys += ["male_palps"]

                payload = {}
                for key in active_keys:
                    choice = st.selectbox(
                        _TRAIT_LABELS[key], _trait_options(key), key=f"trait_{key}"
                    )
                    if choice != _NOT_OBSERVED:
                        payload[key] = choice

                st.markdown("#### Step 2 — Species/Complex Markers (optional)")
                selected_markers = st.multiselect(
                    "Tick any specific field markers you observe",
                    _all_species_markers(),
                    key="species_markers",
                )

                run = st.button("Resolve", type="primary", width="stretch")

            with col2:
                st.markdown("#### Results")
                # Snapshot the inputs alongside the triage, so the result stays rendered
                # across the rerun that a Save click causes — and so what gets saved is
                # exactly what produced what is on screen, not whatever the widgets read
                # at save time.
                if run:
                    with st.spinner("Scoring genus traits…"):
                        st.session_state["adult_checklist_result"] = {
                            "triage": evaluate_genus_triage(payload),
                            "sex": sex,
                            "traits": payload,
                            "markers": selected_markers,
                        }

                scored = st.session_state.get("adult_checklist_result")
                if scored:
                    if scored["sex"] == "Male":
                        st.warning(
                            "Male specimen — genitalia dissection is the standard "
                            "confirmatory method for males. Results below are indicative only."
                        )
                    triage = scored["triage"]
                    genus = _render_genus_result(triage)

                    if genus:
                        markers_for_search = list(scored["traits"].values()) + scored["markers"]
                        candidates = search_species_reference(genus, markers_for_search)
                        _render_species_candidates(candidates, markers_ticked=bool(scored["markers"]))

                        # ── Save this checklist result ──────────────────
                        st.markdown("---")
                        _save_identification(
                            "💾 Save this checklist result",
                            "save_checklist",
                            "manual_checklist",
                            {
                                "genus_triage": triage,
                                "species_candidates": candidates,
                            },
                            target,
                            result_key="adult_checklist_result",
                        )
                else:
                    st.info("Set traits on the left and click **Resolve**.")

        elif method == "Trained Classifier":
            _render_classifier_screening(target)

        else:
            photo_mode = st.radio(
                "Photos to screen",
                options=["Single photo", "Multiple angles"],
                horizontal=True,
                key="adult_photo_mode",
                help=(
                    "One image is often enough for genus. Multiple angles help when the "
                    "diagnostic feature — scutum pattern, wing scales, tarsal banding — "
                    "isn't visible from a single view."
                ),
            )

            if photo_mode == "Single photo":
                _render_single_photo_screening(target)
            else:
                _render_multi_angle_screening(target)

    # ── TAB 2: LARVAL ─────────────────────────────────────────────────────
    with tab2:
        st.subheader("Larval Genus Screening")
        st.caption(
            "Larval identification is reliably possible at GENUS level from field "
            "characters; species-level larval keys require lab dissection "
            "(Service 1990 / Jupp 1996)."
        )

        l_method = st.radio(
            "Identification method",
            ["Manual Character Checklist", "Larval Deep Key", "AI Photo Screening"],
            horizontal=True,
            key="larval_method",
        )
        st.markdown("---")

        if l_method == "Larval Deep Key":
            _render_larval_deep_key(target)

        elif l_method == "Manual Character Checklist":
            col1, col2 = st.columns([5, 4])

            with col1:
                posture = st.radio(
                    "Resting Posture at Surface",
                    [
                        "Parallel to surface, no visible siphon",
                        "Hangs at an angle from the surface",
                    ],
                )
                siphon_length = st.selectbox(
                    "Respiratory Siphon Length (if present)",
                    [
                        "N/A — no siphon observed",
                        "Short & Stout (≤3x width)",
                        "Long & Slender (>5x width)",
                    ],
                )

                run_larval = st.button(
                    "Resolve Genus", type="primary", width="stretch", key="larval_resolve"
                )

            with col2:
                st.markdown("#### Result")
                # Held in session_state so the Save button survives the rerun its own
                # click triggers — see the adult checklist above.
                if run_larval:
                    st.session_state["larval_checklist_result"] = match_larval_morphology({
                        "posture":       posture,
                        "siphon_length": siphon_length,
                    })

                result = st.session_state.get("larval_checklist_result")
                if result:
                    st.markdown(f"### {result['genus']}")
                    tier = result.get("confidence_tier")
                    if tier:
                        st.markdown(_badge(tier, _TIER_COLOR.get(tier, "#64748B")), unsafe_allow_html=True)
                    if result.get("siphon_status"):
                        st.markdown(f"**Siphon:** {result['siphon_status']}")
                    if result.get("posture_status"):
                        st.markdown(f"**Posture:** {result['posture_status']}")
                    st.write(result.get("notes", ""))

                    # ── Save this checklist result ──────────────────
                    st.markdown("---")
                    _save_identification(
                        "💾 Save this larval checklist result",
                        "save_checklist_larval",
                        "manual_checklist",
                        result,
                        target,
                        result_key="larval_checklist_result",
                    )
                else:
                    st.info("Set the characters and click **Resolve Genus**.")

        else:
            col1, col2 = st.columns([4, 5])

            with col1:
                uploaded_larva = st.file_uploader(
                    "Larval image (JPG/PNG)", type=["jpg", "jpeg", "png"], key="larval_img_uploader"
                )
                if uploaded_larva:
                    st.image(uploaded_larva, caption="Uploaded specimen", width="stretch")

            with col2:
                st.markdown("#### AI Screening Result")
                if uploaded_larva:
                    result = _screen_image_once(
                        uploaded_larva, "vision_larval_cache", process_larval_image_inference
                    )
                    _render_vision_result(result, is_larval=True)

                    # ── Save this AI screening result ──────────────────
                    if "error" not in result:
                        st.markdown("---")
                        _save_identification(
                            "💾 Save this AI screening result",
                            "save_vision_larval",
                            "ai_vision",
                            result,
                            target,
                        )
                else:
                    st.info("Upload a photo to run AI-assisted screening.")

    # ── TAB 3: OPERATIONAL ADVISORY ───────────────────────────────────────
    with tab3:
        st.subheader("Epidemiological Threat Advisory")
        st.caption("Generates a briefing grounded in your currently filtered surveillance data.")

        if active_df is None or active_df.empty:
            st.warning("No surveillance data loaded — nothing to brief on.")
        else:
            query = st.text_area(
                "Operational question or focus (optional)",
                placeholder="e.g. Which zones should receive priority larviciding this week?",
            )
            if st.button("Generate Advisory Briefing", type="primary"):
                with st.spinner("Synthesizing briefing…"):
                    briefing = generate_ai_intervention_response(active_df, query)
                st.markdown(briefing)
