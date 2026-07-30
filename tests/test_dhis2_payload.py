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


# ---------------------------------------------------------------------------
# Batches must reach DHIS2. A row is not a specimen.
# ---------------------------------------------------------------------------
SITE = "Rice Field / Irrigated Field"
DATE = "2026-07-28"


def _batch(anopheles=0, culex=0, aedes=0, other=0, vialed=None):
    result = {
        "anopheles_count": anopheles, "culex_count": culex,
        "aedes_count": aedes, "other_genera_count": other,
    }
    if vialed:
        result["vialed_out"] = vialed
    return {
        "collection_date": DATE, "breeding_site_type": SITE,
        "field_screening_result": {"screening_method": "manual_field_log", "result": result},
    }


def _values_by_element(df):
    return {
        v["dataElement"]: int(v["value"])
        for v in json.loads(_build_dhis2_payload(pd.DataFrame(df)))["dataValues"]
    }


def test_a_batch_is_counted_by_its_specimens_not_as_one_row():
    """The reported bug: grouping on the single-genus extractor dropped batches entirely.

    A manual_field_log row holds raw counts for several genera at once, so it resolves to
    no single genus and was filtered out before aggregation — the export silently reported
    nothing for the collection events that hold most of the catch.
    """
    values = _values_by_element([_batch(anopheles=500, culex=50, aedes=20)])

    assert values == {"ZVD_LDI_001": 500, "ZVD_LDI_002": 50, "ZVD_LDI_003": 20}


def test_a_batch_and_its_vialed_children_are_not_double_counted():
    """The conservation invariant, carried into the export.

    100 of 500 Anopheles vialed out: the batch reports 400, each child contributes 1, and
    DHIS2 must see 500 — not 400, and not 600.
    """
    rows = [_batch(anopheles=500, vialed={"Anopheles": 100})]
    rows += [_vialed("Anopheles") for _ in range(100)]

    assert _values_by_element(rows)["ZVD_LDI_001"] == 500


def test_other_genera_get_their_own_code():
    """Not the unmapped fallback: "not broken out" and "not recognised" are different."""
    values = _values_by_element([_batch(other=7)])

    assert values == {"ZVD_LDI_004": 7}
    assert "ZVD_LDI_999" not in values


def test_batches_and_identifications_aggregate_together():
    """Same date and site, different row types — one data value per genus, summed."""
    rows = [_batch(anopheles=10), _vialed("Anopheles"), _vialed("Culex")]

    values = _values_by_element(rows)
    assert values["ZVD_LDI_001"] == 11
    assert values["ZVD_LDI_002"] == 1


def test_a_screening_result_stored_as_a_json_string_still_counts():
    """field_screening_result is JSONB and does not always arrive parsed.

    The counter returned {} for a string, which read as an empty collection rather than an
    error — an undercount with nothing to notice.
    """
    row = _batch(anopheles=42)
    row["field_screening_result"] = json.dumps(row["field_screening_result"])

    assert _values_by_element([row]) == {"ZVD_LDI_001": 42}
