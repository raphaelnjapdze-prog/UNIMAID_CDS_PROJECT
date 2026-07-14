"""
Guided multi-angle specimen capture component for adult mosquito identification.

This module is intentionally UI-only. It collects four image angles for a single
specimen, records capture metadata, and produces a structured specimen record
for downstream classification logic.
"""

from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import streamlit as st
from PIL import Image

from utils.auth import get_collector_label
from utils.data_manager import submit_multi_angle_capture_entry
from utils.image_quality_control import assess_image_quality

ANGLE_CONFIG: List[Dict[str, Any]] = [
    {
        "key": "dorsal",
        "title": "Dorsal view",
        "subtitle": "Scutum pattern and thoracic ornamentation",
        "description": "Capture the mosquito from above so the scutum pattern is visible.",
        "what_to_look_for": [
            "The entire thorax and the scutum should be in frame",
            "Aim for even lighting so any pale/dark patterning is visible",
            "Include the head and wing bases if possible",
        ],
        "reference": "Reference: dorsal view should show a clear, centered thorax with visible scutal markings.",
        "diagram": "  /\\\n (  o  )\n  \\_//\n  [thorax]\n",
    },
    {
        "key": "lateral",
        "title": "Lateral view",
        "subtitle": "Leg and tarsi banding",
        "description": "Capture the specimen from the side to show leg and tarsi banding.",
        "what_to_look_for": [
            "The full body profile should be visible",
            "Legs and tarsi should be spread enough to observe pale bands",
            "The abdomen should not obscure the legs",
        ],
        "reference": "Reference: lateral view should show a clean profile with visible leg segmentation and banding.",
        "diagram": "  /|\\\n /_|_\\\n[legs visible]\n",
    },
    {
        "key": "wing",
        "title": "Wing close-up",
        "subtitle": "Wing scales and pattern",
        "description": "Take a close view of one or both wings to show scale patterning.",
        "what_to_look_for": [
            "The wing should fill most of the frame",
            "Focus on the wing veins and any pale/dark scaling",
            "Avoid blur from movement",
        ],
        "reference": "Reference: wing close-up should be sharp and centered, with the wing membrane visible.",
        "diagram": "  /\\\\\\\\\\\\\\n /  \\\\  \\\\n/____\\\\____\\n",
    },
    {
        "key": "palp",
        "title": "Palp close-up",
        "subtitle": "Palps and mouthparts",
        "description": "Capture a close-up of the head and palp region for mouthpart detail.",
        "what_to_look_for": [
            "The head should be centered and sharply focused",
            "Palps should be visible and not hidden by the proboscis",
            "Use a light background if possible",
        ],
        "reference": "Reference: palp close-up should clearly show the head and palpi structure.",
        "diagram": "   [head]\n  /  |  \\\n [palps]\n",
    },
]


def _initialize_state() -> Dict[str, Any]:
    if "multi_angle_capture_state" not in st.session_state:
        st.session_state["multi_angle_capture_state"] = {
            "current_step": 0,
            "images": {},
            "statuses": {angle["key"]: "pending" for angle in ANGLE_CONFIG},
            "submitted": False,
            "last_record": None,
        }
    return st.session_state["multi_angle_capture_state"]


def _get_file_bytes(uploaded_file: Optional[Any]) -> Optional[bytes]:
    if uploaded_file is None:
        return None
    if hasattr(uploaded_file, "getvalue"):
        return uploaded_file.getvalue()
    if hasattr(uploaded_file, "read"):
        data = uploaded_file.read()
        if hasattr(uploaded_file, "seek"):
            uploaded_file.seek(0)
        return data
    return None


def _save_image(angle_key: str, uploaded_file: Optional[Any]) -> None:
    state = _initialize_state()
    image_bytes = _get_file_bytes(uploaded_file)
    if not image_bytes:
        return

    state["images"][angle_key] = {
        "filename": getattr(uploaded_file, "name", f"{angle_key}.jpg"),
        "mime_type": getattr(uploaded_file, "type", "image/jpeg"),
        "bytes": image_bytes,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    state["statuses"][angle_key] = "captured"
    state["submitted"] = False


def _mark_not_captured(angle_key: str) -> None:
    state = _initialize_state()
    state["images"].pop(angle_key, None)
    state["statuses"][angle_key] = "not_captured"
    state["submitted"] = False


def _move_step(delta: int) -> None:
    state = _initialize_state()
    next_step = state["current_step"] + delta
    total_steps = len(ANGLE_CONFIG)
    state["current_step"] = max(0, min(next_step, total_steps))


def _reset_flow() -> None:
    st.session_state.pop("multi_angle_capture_state", None)
    st.session_state.pop("capture_collector_id", None)
    st.session_state.pop("capture_gps_coordinates", None)
    _initialize_state()


def _parse_gps(text: Optional[str]) -> tuple[Optional[float], Optional[float]]:
    """Parse a "lat, lon" string into floats; returns (None, None) if unparseable."""
    parts = (text or "").replace(";", ",").split(",")
    if len(parts) == 2:
        try:
            return float(parts[0].strip()), float(parts[1].strip())
        except ValueError:
            return None, None
    return None, None


def _persist_capture(state: Dict[str, Any]) -> None:
    """
    Upload the captured angle images and insert a specimen_records row via the
    data layer, then report honestly. On failure the data layer already
    surfaces the specific error, so this just stops.
    """
    gps_lat, gps_lon = _parse_gps(st.session_state.get("capture_gps_coordinates", ""))
    row = submit_multi_angle_capture_entry(
        angle_images=state["images"],
        statuses=state["statuses"],
        gps_lat=gps_lat,
        gps_lon=gps_lon,
        field_collector_label=st.session_state.get("capture_collector_id", "").strip(),
    )
    if row is None:
        return

    state["last_record"] = row
    state["submitted"] = True
    st.session_state["last_submitted_record"] = row
    st.success("Specimen record saved to the surveillance ledger.")
    st.json(row, expanded=False)
    st.download_button(
        label="Download specimen JSON",
        data=json.dumps(row, indent=2, default=str),
        file_name=f"specimen_{row.get('specimen_id')}.json",
        mime="application/json",
    )


def _render_angle_step(angle: Dict[str, Any]) -> None:
    state = _initialize_state()
    angle_key = angle["key"]
    st.subheader(f"Step {state['current_step'] + 1} of {len(ANGLE_CONFIG)}: {angle['title']}")
    st.caption(angle["subtitle"])
    st.info(angle["description"])

    with st.container(border=True):
        st.markdown("**Reference guide**")
        st.write(angle["reference"])
        st.write("What to look for:")
        for bullet in angle["what_to_look_for"]:
            st.write(f"- {bullet}")
        st.code(angle["diagram"], language="text")

    st.markdown("---")
    st.markdown("**Capture input**")
    camera_file = st.camera_input(f"Capture {angle['title']}", key=f"camera_{angle_key}")
    uploaded_file = st.file_uploader(
        f"Or upload a photo for {angle['title']}",
        type=["png", "jpg", "jpeg"],
        key=f"upload_{angle_key}",
    )

    source_file = camera_file if camera_file is not None else uploaded_file
    if source_file is not None:
        _save_image(angle_key, source_file)

    if state["statuses"].get(angle_key) == "captured":
        image_payload = state["images"].get(angle_key)
        if image_payload and image_payload.get("bytes"):
            st.success("Image captured for this angle.")
            st.image(io.BytesIO(image_payload["bytes"]), width="stretch")
        if st.button("Remove this image", key=f"clear_{angle_key}"):
            _mark_not_captured(angle_key)
            st.rerun()

    col_a, col_b = st.columns([1, 1])
    with col_a:
        if st.button("Skip this angle", key=f"skip_{angle_key}"):
            _mark_not_captured(angle_key)
            st.rerun()
    with col_b:
        if st.button("Next angle", key=f"next_{angle_key}"):
            _move_step(1)
            st.rerun()

    if state["current_step"] > 0:
        if st.button("Previous angle", key=f"prev_{angle_key}"):
            _move_step(-1)
            st.rerun()


def _render_summary() -> None:
    state = _initialize_state()

    st.subheader("Completion summary")
    st.caption("Review which angles were captured before submitting the specimen record.")

    for angle in ANGLE_CONFIG:
        angle_key = angle["key"]
        status = state["statuses"].get(angle_key, "pending")
        if status == "captured":
            st.success(f"{angle['title']}: captured")
        elif status == "not_captured":
            st.warning(f"{angle['title']}: not captured")
        else:
            st.info(f"{angle['title']}: pending")

    st.markdown("---")

    # Prefill with the signed-in user rather than leaving it blank, but keep it editable:
    # one account is often used to record a capture made by a field assistant, and this
    # box is that person's name. It is a label, not identity — the account's own id and
    # name are stamped onto the record separately, and cannot be typed over here.
    signed_in_as = get_collector_label()
    if signed_in_as and not st.session_state.get("capture_collector_id"):
        st.session_state["capture_collector_id"] = signed_in_as

    st.text_input(
        "Collector",
        key="capture_collector_id",
        help="Who physically collected this specimen. Defaults to you; change it if you "
             "are recording on someone else's behalf.",
    )
    if signed_in_as:
        st.caption(f"Recording under the account of **{signed_in_as}**.")
    else:
        st.warning("You are not signed in — this capture cannot be attributed to a collector.")

    st.text_input("GPS coordinates (optional)", key="capture_gps_coordinates")

    if st.button("Submit specimen record", type="primary"):
        state = _initialize_state()

        captured = [a["key"] for a in ANGLE_CONFIG if state["statuses"].get(a["key"]) == "captured"]
        if not captured:
            st.warning("Capture at least one angle before submitting.")
            return

        # Run image quality checks for each captured angle before finalizing submission
        failures: List[Dict[str, str]] = []
        for angle in ANGLE_CONFIG:
            angle_key = angle["key"]
            if state["statuses"].get(angle_key) == "captured":
                payload = state["images"].get(angle_key)
                if payload and payload.get("bytes"):
                    try:
                        img = Image.open(io.BytesIO(payload["bytes"]))
                        qc = assess_image_quality(img)
                        if not qc.get("passed"):
                            failures.append({"angle_key": angle_key, "title": angle["title"], "reason": qc.get("reason", "QC failed")})
                    except Exception as e:
                        failures.append({"angle_key": angle_key, "title": angle["title"], "reason": f"QC error: {e}"})

        if failures:
            st.warning("Image quality checks failed for one or more angles. Please retake the indicated views.")
            for f in failures:
                st.write(f"- {f['title']}: {f['reason']}")
                if st.button(f"Retake {f['title']}", key=f"retake_{f['angle_key']}"):
                    # jump to the angle's step for recapture
                    state["current_step"] = next((i for i, a in enumerate(ANGLE_CONFIG) if a["key"] == f["angle_key"]), 0)
                    st.rerun()
            if st.button("Force submit anyway (not recommended)", key="force_submit"):
                _persist_capture(state)
        else:
            _persist_capture(state)

    if st.button("Start over"):
        _reset_flow()
        st.rerun()


def render_multi_angle_capture_component() -> Optional[Dict[str, Any]]:
    """Render the guided multi-angle capture workflow and return the last submitted record."""

    st.title("Multi-angle mosquito specimen capture")
    st.caption("Capture the four required angles in sequence. Skip any angle that cannot be obtained.")

    _initialize_state()

    st.markdown("---")
    state = _initialize_state()
    total_steps = len(ANGLE_CONFIG)
    progress_value = (state["current_step"] + 1) / total_steps if total_steps else 1.0
    st.progress(progress_value, text="Capture progress")

    if state["current_step"] < total_steps:
        angle = ANGLE_CONFIG[state["current_step"]]
        _render_angle_step(angle)
    else:
        _render_summary()

    if state.get("last_record") and state.get("submitted"):
        st.info("The last submitted record is available in session state for downstream use.")

    return state.get("last_record")


def render_multi_angle_capture_page() -> None:
    """Page entry point used by the app router (see app.py PAGE_MODULES)."""
    render_multi_angle_capture_component()


if __name__ == "__main__":
    render_multi_angle_capture_component()
