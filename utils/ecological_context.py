"""Boundary for the ecological probability estimator in ``models/``.

The estimator (``models/ecological_probability_estimator.py``) is a pure-Python,
interpretable weighted-rules system — no torch, no sklearn, no model files — so
unlike the trained CNN it runs in the deployed app unconditionally.

It refines a **complex-level** verdict (e.g. "Anopheles gambiae complex") into a
probability distribution over member species from geography + habitat + season.
It is an ESTIMATE to guide field sampling and specimen prioritisation, never an
identification: PCR remains the only definitive method, and nothing here ever
changes a result's ``resolution_level`` or the predicted complex. It only ever
applies on top of a complex the estimator actually has rules for.
"""

from __future__ import annotations

from typing import Any, Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)


def _rules() -> dict:
    from models.ecological_probability_estimator import ECOLOGICAL_RULES

    return ECOLOGICAL_RULES


def supported_complexes() -> list[str]:
    """The complex names the estimator has ecological rules for."""
    return list(_rules().keys())


def complex_for_taxon(taxon: Optional[str]) -> Optional[str]:
    """Map a predicted taxon string to a supported estimator complex, or None.

    Matches on the complex trigger word so it works regardless of how the taxon
    was formatted upstream ("An. gambiae complex", "Anopheles gambiae complex",
    "Anopheles gambiae complex (s.l.)", …). Returns None for species/genus-level
    taxa and for complexes the estimator has no rules for — the caller then shows
    no ecological panel, rather than a broken one.
    """
    if not taxon:
        return None
    t = taxon.lower()
    for name in supported_complexes():
        # e.g. "Anopheles gambiae complex" -> trigger "gambiae"
        parts = name.split()
        trigger = parts[1].lower() if len(parts) > 1 else parts[0].lower()
        if trigger in t:
            return name
    return None


def region_options() -> list[str]:
    """Regions the estimator's rules actually score (excludes the 'unknown' key)."""
    regions: set[str] = set()
    for members in _rules().values():
        for sp in members.values():
            regions.update(sp["geographic_scores"].keys())
    regions.discard("unknown")
    return sorted(regions)


def habitat_options() -> list[str]:
    """Breeding-habitat categories the estimator's rules score (excludes 'unknown')."""
    habitats: set[str] = set()
    for members in _rules().values():
        for sp in members.values():
            habitats.update(sp["habitat_scores"].keys())
    habitats.discard("unknown")
    return sorted(habitats)


def estimate(
    complex_name: str,
    *,
    region: Optional[str] = None,
    habitat: str = "unknown",
    month: int = 0,
    coordinates: Optional[tuple[float, float]] = None,
) -> dict[str, Any]:
    """Run the ecological estimate for a complex, or return ``{"error": ...}``.

    Never raises to the caller: an unsupported complex or bad input yields an
    honest error dict rather than a crash or a fabricated distribution.
    """
    try:
        from models.ecological_probability_estimator import (
            EcologicalContext,
            estimate_species_probability,
        )

        context = EcologicalContext(
            complex_name=complex_name,
            region_name=region or None,
            breeding_site_type=habitat or "unknown",
            month=month,
            coordinates=coordinates,
        )
        return estimate_species_probability(context)
    except ValueError as e:
        logger.debug("Ecological estimate unavailable: %s", e, exc_info=True)
        return {"error": str(e)}
    except Exception as e:  # noqa: BLE001 - never let context estimation break a save
        logger.exception("Ecological estimate failed")
        return {"error": f"Ecological estimate failed: {e}"}
