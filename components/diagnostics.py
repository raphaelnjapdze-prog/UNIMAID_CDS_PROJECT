"""
AI-Assisted Diagnostics & Identification component.

Adult flow: genus-first triage (GENUS_TRIAGE_MATRIX) → optional species-level
marker narrowing (search_species_reference against the 60-species catalog).
Larval flow: genus screening via evaluate_larval_triage.
Both stages cap results honestly — Undetermined stays Undetermined, complex
members stay complex-level, never a forced single species guess.
"""

import pandas as pd
import streamlit as st

from utils.ai_advisory import generate_ai_intervention_response
from utils.morphology_keys import (
    ANOPHELES_KEY_ROOT,
    GENUS_TRIAGE_MATRIX,
    SPECIES_CATALOG,
    anopheles_key_node,
    anopheles_key_step,
    evaluate_genus_triage,
    get_anopheles_character_schema,
    identify_anopheles_species,
    match_larval_morphology,
    search_species_reference,
)
from utils.vision_inference import process_adult_image_inference, process_larval_image_inference

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


def _render_anopheles_identification(res: dict):
    """Render the weighted-character Anopheles verdict + per-candidate audit trail."""
    resolution = res.get("resolution_level", "undetermined")
    color, tier_label = _RESOLUTION_STYLE.get(resolution, ("#64748B", resolution))

    badges = _badge(tier_label, color)
    if res.get("molecular_id_required"):
        badges += _badge("PCR confirmation required", "#D97706")
    if res.get("biosecurity_alert"):
        badges += _badge("⚠️ Biosecurity alert", "#DC2626")

    st.markdown(
        f"""
        <div style="border:1px solid #E2E8F0; border-radius:12px; padding:16px 18px;
                    background:white; margin-bottom:14px;">
            <div style="font-size:13px; color:#64748B; font-weight:600;">Resolved Taxon</div>
            <div style="font-size:24px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{res.get('taxon','Anopheles spp.')}</div>
            {_badge(f"Confidence: {res.get('confidence',0)}%", "#0369A1")}{badges}
            <div style="font-size:13px; color:#475569; margin-top:8px;">{res.get('reason','')}</div>
            <div style="font-size:12px; color:#64748B; margin-top:6px;"><strong>Next step:</strong> {res.get('next_step','')}</div>
        </div>
        """,
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
            disc = "".join(f"<li>{d}</li>" for d in c.get("discriminators", []))
            disc_block = f'<ul style="margin:6px 0 0 18px; padding:0; color:#475569; font-size:12px;">{disc}</ul>' if disc else ""
            st.markdown(
                f"""
                <div style="border:1px solid #E2E8F0; border-radius:10px; padding:12px 14px;
                            margin-bottom:8px; background:white;">
                    <div style="display:flex; justify-content:space-between; gap:10px; align-items:baseline;">
                        <span style="font-size:15px; font-weight:700; color:#0F172A;">{c['species_name']}</span>
                        <span style="font-size:12px; color:#0369A1; font-weight:700; white-space:nowrap;">{c['confidence']}% · {matched}/{compared} chars</span>
                    </div>
                    <div style="font-size:12px; color:#64748B; margin-top:2px;">
                        {c.get('complex','None') if c.get('complex') not in (None,'None') else 'No complex'} ·
                        <em>{c.get('vector_status','Unknown')}</em>
                        {' · ⚠ ' + str(contra) + ' contradicting' if contra else ''}
                    </div>
                    {disc_block}
                </div>
                """,
                unsafe_allow_html=True,
            )

    st.caption(
        "🔬 Weighted character engine (Gillies & Coetzee 1987; Coetzee 2020). "
        "Cryptic complexes (*An. gambiae* complex, *An. funestus* group) are "
        "capped at complex/group level by design — only PCR splits them."
    )


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
    disc = "".join(f"<li>{d}</li>" for d in result.get("discriminators", []))
    disc_block = f'<ul style="margin:8px 0 0 18px; padding:0; color:#475569; font-size:13px;">{disc}</ul>' if disc else ""

    st.markdown(
        f"""
        <div style="border:1px solid {color}; border-radius:12px; padding:16px 18px;
                    background:white; margin-bottom:12px;">
            <div style="font-size:13px; color:#64748B; font-weight:600;">Key Result</div>
            <div style="font-size:22px; font-weight:800; color:#0F172A; margin:4px 0 8px;">{result.get('taxon')}</div>
            {badges}
            {matched_line}
            {disc_block}
            <div style="font-size:13px; color:#475569; margin-top:8px;">{result.get('notes','')}</div>
            <div style="font-size:12px; color:#64748B; margin-top:6px;"><strong>Next step:</strong> {result.get('next_step','')}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.caption(f"Vector status: {result.get('vector_status','Unknown')}")


def _render_anopheles_deep_key():
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
            run_id = st.button("Identify Anopheles", type="primary", use_container_width=True, key="anoph_identify")
        with col2:
            st.markdown("##### Result")
            if run_id:
                if not observed:
                    st.info("Set at least one character on the left, then click **Identify Anopheles**.")
                else:
                    with st.spinner("Scoring diagnostic characters…"):
                        res = identify_anopheles_species(observed)
                    _render_anopheles_identification(res)

                    if res.get("resolution_level") not in ("undetermined", "genus"):
                        st.markdown("---")
                        if st.button("💾 Save this Anopheles result", key="save_anoph_char"):
                            from utils.specimen_submission import submit_screening_result
                            saved = submit_screening_result(
                                screening_method="manual_checklist",
                                result={
                                    "genus_triage": {"genus": "Anopheles", "confidence": res.get("confidence", 0)},
                                    "anopheles_deep_key": res,
                                },
                            )
                            if saved:
                                st.success(f"Saved as specimen {saved['specimen_id']}")
                            else:
                                st.error("Could not save — check database connection.")
            else:
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
        if st.button("↺ Restart key", use_container_width=True, key="anoph_key_reset"):
            st.session_state["anoph_key_node"] = ANOPHELES_KEY_ROOT
            st.session_state["anoph_key_terminal"] = None
            st.session_state["anoph_key_trail"] = []

    trail = st.session_state["anoph_key_trail"]
    if trail:
        st.caption("Path: " + "  →  ".join(trail))

    terminal = st.session_state["anoph_key_terminal"]
    if terminal:
        _render_key_terminal(terminal)
        if st.button("💾 Save this key result", key="save_anoph_key"):
            from utils.specimen_submission import submit_screening_result
            saved = submit_screening_result(
                screening_method="manual_checklist",
                result={
                    "genus_triage": {"genus": "Anopheles"},
                    "anopheles_couplet_key": terminal,
                },
            )
            if saved:
                st.success(f"Saved as specimen {saved['specimen_id']}")
            else:
                st.error("Could not save — check database connection.")
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
        if st.button(lead["text"], key=f"anoph_lead_{node_id}_{i}", use_container_width=True):
            step = anopheles_key_step(node_id, i)
            st.session_state["anoph_key_trail"] = trail + [f"{node_id}{chr(97 + i)}"]
            if step["type"] == "couplet":
                st.session_state["anoph_key_node"] = step["node_id"]
            elif step["type"] == "terminal":
                st.session_state["anoph_key_terminal"] = step["result"]
            else:
                st.error(step.get("message", "Key error."))
            st.rerun()


def render_diagnostics_page(active_df: pd.DataFrame = None):
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
            ["Manual Character Checklist", "Anopheles Deep Key", "AI Photo Screening"],
            horizontal=True,
            key="adult_method",
        )
        st.markdown("---")

        if method == "Anopheles Deep Key":
            _render_anopheles_deep_key()

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

                run = st.button("Resolve", type="primary", use_container_width=True)

            with col2:
                st.markdown("#### Results")
                if run:
                    if sex == "Male":
                        st.warning(
                            "Male specimen — genitalia dissection is the standard "
                            "confirmatory method for males. Results below are indicative only."
                        )
                    with st.spinner("Scoring genus traits…"):
                        triage = evaluate_genus_triage(payload)
                    genus = _render_genus_result(triage)

                    if genus:
                        markers_for_search = list(payload.values()) + selected_markers
                        candidates = search_species_reference(genus, markers_for_search)
                        _render_species_candidates(candidates, markers_ticked=bool(selected_markers))

                        # ── Save this checklist result ──────────────────
                        st.markdown("---")
                        if st.button("💾 Save this checklist result", key="save_checklist"):
                            from utils.specimen_submission import submit_screening_result
                            saved = submit_screening_result(
                                screening_method="manual_checklist",
                                result={
                                    "genus_triage": triage,
                                    "species_candidates": candidates,
                                },
                            )
                            if saved:
                                st.success(f"Saved as specimen {saved['specimen_id']}")
                            else:
                                st.error("Could not save — check database connection.")
                else:
                    st.info("Set traits on the left and click **Resolve**.")

        else:
            col1, col2 = st.columns([4, 5])

            with col1:
                st.markdown("#### Upload Adult Specimen Photo")
                st.caption("Best results: lateral view, good lighting, in-focus palps/legs/wings.")
                uploaded_adult = st.file_uploader(
                    "Adult image (JPG/PNG)", type=["jpg", "jpeg", "png"], key="adult_img_uploader"
                )
                if uploaded_adult:
                    st.image(uploaded_adult, caption="Uploaded specimen", use_container_width=True)

            with col2:
                st.markdown("#### AI Screening Result")
                if uploaded_adult:
                    with st.spinner("Running AI-assisted visual screening…"):
                        result = process_adult_image_inference(uploaded_adult)
                    _render_vision_result(result, is_larval=False)

                    # ── Save this AI screening result ──────────────────
                    if "error" not in result:
                        st.markdown("---")
                        if st.button("💾 Save this AI screening result", key="save_vision_adult"):
                            from utils.specimen_submission import submit_screening_result
                            saved = submit_screening_result(
                                screening_method="ai_vision",
                                result=result,
                            )
                            if saved:
                                st.success(f"Saved as specimen {saved['specimen_id']}")
                            else:
                                st.error("Could not save — check database connection.")
                else:
                    st.info("Upload a photo to run AI-assisted screening.")

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
            ["Manual Character Checklist", "AI Photo Screening"],
            horizontal=True,
            key="larval_method",
        )
        st.markdown("---")

        if l_method == "Manual Character Checklist":
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
                    "Resolve Genus", type="primary", use_container_width=True, key="larval_resolve"
                )

            with col2:
                st.markdown("#### Result")
                if run_larval:
                    result = match_larval_morphology({
                        "posture":       posture,
                        "siphon_length": siphon_length,
                    })
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
                    if st.button("💾 Save this larval checklist result", key="save_checklist_larval"):
                        from utils.specimen_submission import submit_screening_result
                        saved = submit_screening_result(
                            screening_method="manual_checklist",
                            result=result,
                        )
                        if saved:
                            st.success(f"Saved as specimen {saved['specimen_id']}")
                        else:
                            st.error("Could not save — check database connection.")
                else:
                    st.info("Set the characters and click **Resolve Genus**.")

        else:
            col1, col2 = st.columns([4, 5])

            with col1:
                uploaded_larva = st.file_uploader(
                    "Larval image (JPG/PNG)", type=["jpg", "jpeg", "png"], key="larval_img_uploader"
                )
                if uploaded_larva:
                    st.image(uploaded_larva, caption="Uploaded specimen", use_container_width=True)

            with col2:
                st.markdown("#### AI Screening Result")
                if uploaded_larva:
                    with st.spinner("Running AI-assisted visual screening…"):
                        result = process_larval_image_inference(uploaded_larva)
                    _render_vision_result(result, is_larval=True)

                    # ── Save this AI screening result ──────────────────
                    if "error" not in result:
                        st.markdown("---")
                        if st.button("💾 Save this AI screening result", key="save_vision_larval"):
                            from utils.specimen_submission import submit_screening_result
                            saved = submit_screening_result(
                                screening_method="ai_vision",
                                result=result,
                            )
                            if saved:
                                st.success(f"Saved as specimen {saved['specimen_id']}")
                            else:
                                st.error("Could not save — check database connection.")
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
