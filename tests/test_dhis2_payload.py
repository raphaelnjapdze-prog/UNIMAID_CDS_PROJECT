"""The DHIS2 export payload must be well-formed, even while its codes are placeholders.

Org unit codes are derived from breeding_site_type as a stand-in for real DHIS2 UIDs. That
is a documented placeholder — but a placeholder still has to be a legal identifier. The
original derivation replaced spaces only, so the breeding site type
"Rice Field / Irrigated Field" produced `SITE_RICE_FIELD_/_IRRIGATED_FIELD`, embedding a
slash in an identifier DHIS2 rejects on import. The payload looked plausible and would have
failed at the point of submission.
"""
import json

import pandas as pd
import pytest

from components.dashboard import _build_dhis2_payload, _org_unit_code

# Every real option from the Site Log's breeding-site picker that is not a bare word, plus
# the shapes that broke: separators, punctuation, empties.
UNSAFE_SITES = [
    "Rice Field / Irrigated Field",
    "Drain / Gutter",
    "Puddle (temporary)",
    "Well - covered",
    "Tyre  &  container",
]


@pytest.mark.parametrize("site", UNSAFE_SITES)
def test_org_unit_code_is_alphanumeric_and_underscores(site):
    code = _org_unit_code(site)
    assert code.startswith("SITE_")
    body = code.removeprefix("SITE_")
    assert body, f"{site!r} produced an empty org unit code"
    assert all(c.isalnum() or c == "_" for c in code), (
        f"{site!r} produced {code!r}, which DHIS2 will reject as an org unit identifier"
    )


def test_the_slash_case_that_was_reported():
    """Pins the exact value seen in the broken export."""
    assert _org_unit_code("Rice Field / Irrigated Field") == "SITE_RICE_FIELD_IRRIGATED_FIELD"
    assert "/" not in _org_unit_code("Rice Field / Irrigated Field")


@pytest.mark.parametrize("site", [None, "", "   ", "///", "!!!"])
def test_degenerate_sites_still_yield_a_usable_code(site):
    """No site, or a site made entirely of punctuation, must not collapse to a bare 'SITE_'."""
    assert _org_unit_code(site) == "SITE_UNSPECIFIED"


def _vialed(genus):
    """One individual vialed out of a batch — the row shape the export actually counts."""
    return {
        "collection_date": "2026-07-28",
        "breeding_site_type": "Rice Field / Irrigated Field",
        "field_screening_result": {
            "screening_method": "field_subsample",
            "result": {"genus": genus},
        },
    }


def _records():
    return pd.DataFrame([_vialed("Anopheles"), _vialed("Anopheles"), _vialed("Culex")])


def test_payload_is_valid_json_with_clean_org_units():
    payload = json.loads(_build_dhis2_payload(_records()))
    values = payload["dataValues"]
    assert values, "a record with a resolvable genus produced no data values"
    for value in values:
        assert "/" not in value["orgUnit"]
        assert value["period"].isdigit() and len(value["period"]) == 8
        assert value["value"].isdigit()


def test_empty_frame_yields_an_empty_but_valid_payload():
    """An empty ledger must still produce importable JSON, not a crash or a null."""
    assert json.loads(_build_dhis2_payload(pd.DataFrame()))["dataValues"] == []
