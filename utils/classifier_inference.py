"""Boundary between the Streamlit app and the optional two-stage PyTorch
classifier in ``models/``.

Everything heavy — ``torch`` and the trained CNN checkpoints — is lazy-loaded,
so importing this module (and running the app) never requires the ML extras.
The module degrades **honestly**: when torch or the checkpoints are absent it
says so plainly and returns no prediction. It never fabricates a species the
model did not produce — the same hard rule the rest of the data layer follows.

The trained classifier ships as *code and training scripts only*; the ``.pth``
weights are produced by the operator (see ``models/README_CLASSIFIER_SETUP.md``)
and dropped under the model directory. Until they exist, this reports
"not available" and the Diagnostics UI shows setup guidance rather than a button
that silently does nothing.

Result shape (screening_method ``trained_classifier``), consumed by
``utils/pcr_and_accuracy.py`` and ``utils/data_manager.py``::

    {"genus": "Anopheles", "predicted_species": "Anopheles gambiae complex",
     "resolution_level": "complex", "confidence": 0.92, ...}

The pipeline already enforces the cryptic-complex ceiling: its Stage-2 output
classes are constrained so a complex/group can only ever be predicted as the
complex/group (never a bare member), and ``resolution_level`` is derived from a
deterministic taxonomy table, not from the model's raw guess.
"""

from __future__ import annotations

import importlib.util
import os
from typing import Any, Optional

import streamlit as st

from utils.config import get_secret
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Checkpoint filenames are fixed by models/README_CLASSIFIER_SETUP.md; only the
# directory is configurable (so an operator can point at a mounted volume).
_STAGE1_FILENAME = "stage1_genus_classifier.pth"
_STAGE2_FILENAMES = {
    "Anopheles": "stage2_anopheles.pth",
    "Culex": "stage2_culex.pth",
    "Aedes": "stage2_aedes.pth",
}
_GENERA = ("Anopheles", "Culex", "Aedes")

# The Stage-2 classes use abbreviated genera ("An. gambiae complex",
# "Cx. quinquefasciatus", "Ae. aegypti"). Expand to the full genus so the label
# matches the rest of the app (catalog names, PCR accuracy matching).
_GENUS_ABBREV = {"An.": "Anopheles", "Cx.": "Culex", "Ae.": "Aedes"}


def _model_dir() -> str:
    return get_secret("CLASSIFIER_MODEL_DIR") or "models"


def _checkpoint_paths() -> dict[str, str]:
    d = _model_dir()
    paths = {"stage1": os.path.join(d, _STAGE1_FILENAME)}
    for genus, fname in _STAGE2_FILENAMES.items():
        paths[genus] = os.path.join(d, fname)
    return paths


def _torch_available() -> bool:
    return importlib.util.find_spec("torch") is not None


def classifier_status() -> dict[str, Any]:
    """Whether the trained classifier can run right now, and why not if it can't.

    Returns ``{"available": bool, "reason": str, ...}``. When available, also
    carries the resolved ``stage1`` path, the ``stage2`` map of genus->path for
    the checkpoints that exist, and ``stage2_missing`` for those that don't
    (those genera resolve to genus level only — still honest, just coarser).
    """
    if not _torch_available():
        return {
            "available": False,
            "reason": "PyTorch is not installed. Install the ML extras with "
                      "`pip install -r requirements-ml.txt` to enable the trained classifier.",
            "missing": ["torch"],
        }

    paths = _checkpoint_paths()
    if not os.path.exists(paths["stage1"]):
        return {
            "available": False,
            "reason": f"Stage-1 genus checkpoint not found at `{paths['stage1']}`. "
                      f"Train the model and place the .pth files under `{_model_dir()}/` "
                      "(see models/README_CLASSIFIER_SETUP.md).",
            "missing": [paths["stage1"]],
        }

    stage2 = {g: paths[g] for g in _GENERA if os.path.exists(paths[g])}
    return {
        "available": True,
        "reason": "",
        "stage1": paths["stage1"],
        "stage2": stage2,
        "stage2_missing": [g for g in _GENERA if g not in stage2],
    }


@st.cache_resource(show_spinner=False)
def _load_pipeline(stage1_path: str, stage2_items: tuple):
    """Build (once) the two-stage pipeline. Cached as a Streamlit resource so the
    weights are loaded a single time per server, not on every rerun.

    ``stage2_items`` is a tuple of (genus, path) pairs rather than a dict so the
    cache key is hashable.
    """
    from models.inference_pipeline import MosquitoIdentificationPipeline

    stage2 = dict(stage2_items) or None
    return MosquitoIdentificationPipeline(
        stage1_checkpoint=stage1_path,
        stage2_checkpoints=stage2,
    )


def _expand_taxon(name: str) -> str:
    for abbrev, full in _GENUS_ABBREV.items():
        if name.startswith(abbrev + " "):
            return full + name[len(abbrev):]
    return name


def _round(value: Optional[float]) -> Optional[float]:
    return round(float(value), 4) if value is not None else None


def process_adult_image_classification(image_file) -> dict[str, Any]:
    """Run the trained classifier on one adult specimen image.

    Returns a ``trained_classifier`` result dict on success, or ``{"error": ...}``
    when the model is unavailable or inference fails — never a fabricated
    identification. The caller shows the error and offers no Save button.
    """
    status = classifier_status()
    if not status["available"]:
        return {"error": status["reason"], "available": False}

    try:
        from PIL import Image

        pipeline = _load_pipeline(status["stage1"], tuple(sorted(status["stage2"].items())))
        image = Image.open(image_file).convert("RGB")
        raw = pipeline.identify(image)
    except Exception as e:  # noqa: BLE001 - surface any inference failure, don't guess
        logger.exception("Trained-classifier inference failed")
        return {"error": f"Classifier inference failed: {e}"}

    return _build_result(raw)


def _build_result(raw: dict) -> dict[str, Any]:
    """Map the pipeline's raw output to the stored ``trained_classifier`` result.

    Kept separate from I/O so the mapping — genus-abbreviation expansion, the
    stage-2→stage-1 confidence fallback, and the complex/group PCR flag — is unit
    testable without torch or trained weights.
    """
    genus = raw.get("genus")
    species = raw.get("species") or genus
    resolution = raw.get("resolution_level", "genus")
    stage1_conf = raw.get("stage1_confidence")
    stage2_conf = raw.get("stage2_confidence")
    confidence = stage2_conf if stage2_conf is not None else stage1_conf

    return {
        "genus": genus,
        "predicted_species": _expand_taxon(species) if species else genus,
        "resolution_level": resolution,
        "confidence": _round(confidence),
        "stage1_confidence": _round(stage1_conf),
        "stage2_confidence": _round(stage2_conf),
        "stage1_uncertain": bool(raw.get("stage1_uncertain")),
        "stage2_uncertain": raw.get("stage2_uncertain"),
        # A complex/group prediction is inseparable to species by image alone.
        "molecular_id_required": resolution in ("complex", "group"),
        "engine": "two_stage_efficientnet_b0",
    }
