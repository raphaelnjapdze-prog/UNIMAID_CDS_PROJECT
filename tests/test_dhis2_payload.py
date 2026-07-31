"""The DHIS2 export must count every specimen and invent no identifiers.

Three bugs shaped this file, all of the same kind — the export quietly reported less, or
other, than the truth:

1. It grouped on extract_primary_genus and counted rows with .size(). A manual_field_log
   row is a whole batch holding raw counts for several genera, so it resolved to no single
   genus and was filtered out. A batch of 500 with 100 vialed out submitted 100.
2. Its org unit came from breeding_site_type — a habitat category, not a place. DHIS2 org
   units are places, so "Rice Field / Irrigated Field" became the identifier
   SITE_RICE_FIELD_/_IRRIGATED_FIELD, which no instance could match and which embedded a
   slash DHIS2 rejects outright.
3. utils/dhis2_client.py carried hardcoded UIDs ("Hg7824kHGhd") that looked entirely real
   and belonged to no instance anywhere.

The through-line: a name with no mapping must be visible, not dropped.
"""
import json

import pandas as pd
import pytest

import utils.dhis2_client as dhis2
from components.dashboard import _build_dhis2_payload, _unmapped_names

DATE = "2026-07-28"
LGA = "Maiduguri"
SITE = "Rice field / irrigated field"


@pytest.fixture(autouse=True)
def _no_configured_mappings(monkeypatch):
    """Default to an unconfigured instance — the state every new deployment starts in.

    Tests that want real UIDs opt in with _map_org_units/_map_data_elements.
    """
    monkeypatch.setattr(dhis2, "_load_uid_map", lambda key: {})


def _map(monkeypatch, org_units=None, data_elements=None):
    maps = {
        "DHIS2_ORG_UNIT_MAP": org_units or {},
        "DHIS2_DATA_ELEMENT_MAP": data_elements or {},
    }
    monkeypatch.setattr(dhis2, "_load_uid_map", lambda key: maps.get(key, {}))


def _batch(anopheles=0, culex=0, aedes=0, other=0, vialed=None, lga=LGA):
    result = {
        "anopheles_count": anopheles, "culex_count": culex,
        "aedes_count": aedes, "other_genera_count": other,
    }
    if vialed:
        result["vialed_out"] = vialed
    return {
        "collection_date": DATE, "breeding_site_type": SITE, "lga": lga,
        "field_screening_result": {"screening_method": "manual_field_log", "result": result},
    }


def _vialed(genus, lga=LGA):
    return {
        "collection_date": DATE, "breeding_site_type": SITE, "lga": lga,
        "field_screening_result": {"screening_method": "field_subsample", "result": {"genus": genus}},
    }


def _values(rows):
    return json.loads(_build_dhis2_payload(pd.DataFrame(rows)))["dataValues"]


def _by_element(rows):
    return {v["dataElement"]: int(v["value"]) for v in _values(rows)}


# ---------------------------------------------------------------------------
# Counting: a row is not a specimen.
# ---------------------------------------------------------------------------
def test_a_batch_is_counted_by_its_specimens_not_as_one_row():
    values = _by_element([_batch(anopheles=500, culex=50, aedes=20)])

    assert sorted(values.values()) == [20, 50, 500]


def test_a_batch_and_its_vialed_children_are_not_double_counted():
    """100 of 500 vialed out: the batch reports 400, each child 1, DHIS2 must see 500."""
    rows = [_batch(anopheles=500, vialed={"Anopheles": 100})]
    rows += [_vialed("Anopheles") for _ in range(100)]

    assert _by_element(rows) == {dhis2.unmapped_code("genus", "Anopheles"): 500}


def test_batches_and_identifications_aggregate_together():
    rows = [_batch(anopheles=10), _vialed("Anopheles"), _vialed("Culex")]

    values = _by_element(rows)
    assert values[dhis2.unmapped_code("genus", "Anopheles")] == 11
    assert values[dhis2.unmapped_code("genus", "Culex")] == 1


def test_a_screening_result_stored_as_a_json_string_still_counts():
    """field_screening_result is JSONB and does not always arrive parsed."""
    row = _batch(anopheles=42)
    row["field_screening_result"] = json.dumps(row["field_screening_result"])

    assert sum(_by_element([row]).values()) == 42


def test_empty_frame_yields_an_empty_but_valid_payload():
    assert json.loads(_build_dhis2_payload(pd.DataFrame()))["dataValues"] == []


# ---------------------------------------------------------------------------
# Org units are places, and unmapped names stay visible.
# ---------------------------------------------------------------------------
def test_org_unit_comes_from_lga_not_breeding_site_type():
    """The habitat must not leak into the identifier — that was the slash bug."""
    org_units = {v["orgUnit"] for v in _values([_batch(anopheles=1)])}

    assert org_units == {dhis2.unmapped_code("lga", LGA)}
    for code in org_units:
        assert "/" not in code
        assert "RICE" not in code


def test_mapped_lgas_use_the_real_uid(monkeypatch):
    _map(monkeypatch, org_units={LGA: "at6UHUQatSo"}, data_elements={"Anopheles": "s46m5MS0hxu"})

    value = _values([_batch(anopheles=3)])[0]
    assert value["orgUnit"] == "at6UHUQatSo"
    assert value["dataElement"] == "s46m5MS0hxu"
    assert not dhis2.is_unmapped(value["orgUnit"])


def test_an_unmapped_lga_is_flagged_not_dropped():
    """The old code did `if not org_unit_uid: continue` — a silently shorter export."""
    values = _values([_batch(anopheles=7, lga="Konduga")])

    assert len(values) == 1, "the value was dropped instead of flagged"
    assert values[0]["orgUnit"] == "UNMAPPED_LGA_KONDUGA"
    assert int(values[0]["value"]) == 7


def test_a_row_with_no_lga_still_exports():
    """Rows logged before the lga column existed have none, and must not vanish."""
    values = _values([_batch(anopheles=5, lga=None)])

    assert len(values) == 1
    assert values[0]["orgUnit"] == "UNMAPPED_LGA_UNSPECIFIED"


def test_lga_names_containing_slashes_survive_as_identifiers():
    """Askira/Uba and Kala/Balge are the real names; the code must still be legal."""
    code = _values([_batch(anopheles=1, lga="Askira/Uba")])[0]["orgUnit"]

    assert code == "UNMAPPED_LGA_ASKIRA_UBA"
    assert all(c.isalnum() or c == "_" for c in code)


def test_period_is_an_eight_digit_day():
    assert _values([_batch(anopheles=1)])[0]["period"] == "20260728"


def test_unmapped_names_are_reported_to_the_operator():
    """What the dashboard warning reads, scanned back out of the built payload."""
    payload = _build_dhis2_payload(pd.DataFrame([_batch(anopheles=1, lga="Jere")]))

    assert _unmapped_names(payload) == {"UNMAPPED_LGA_JERE", "UNMAPPED_GENUS_ANOPHELES"}


def test_nothing_is_reported_unmapped_once_everything_is_mapped(monkeypatch):
    _map(monkeypatch, org_units={LGA: "at6UHUQatSo"}, data_elements={"Anopheles": "s46m5MS0hxu"})

    assert _unmapped_names(_build_dhis2_payload(pd.DataFrame([_batch(anopheles=1)]))) == set()


# ---------------------------------------------------------------------------
# The submit path refuses what DHIS2 would reject wholesale.
# ---------------------------------------------------------------------------
UNMAPPED_VALUE = [
    {"dataElement": "s46m5MS0hxu", "period": "20260728",
     "orgUnit": "UNMAPPED_LGA_JERE", "value": "7"},
]


@pytest.fixture
def _no_dhis2_server(monkeypatch):
    """An instance with no DHIS2_ENV configured — CI, and any fresh checkout."""
    monkeypatch.setattr(dhis2.st, "secrets", {})


def test_push_refuses_a_payload_with_unmapped_codes(_no_dhis2_server):
    """DHIS2 rejects the whole set, not the offending value, so failing here is kinder.

    Asserted with no server configured, because that is the state CI runs in and the state
    every fresh checkout starts in — the check must not depend on having credentials.
    """
    result = dhis2.push_data_values(UNMAPPED_VALUE)

    assert result["status"] == "ERROR"
    assert "1 of 1" in result["message"]


def test_an_unsendable_payload_is_reported_before_missing_credentials(_no_dhis2_server):
    """Ordering, pinned: whether a payload is submittable does not depend on credentials.

    The auth check used to run first, so an unconfigured instance blamed the credentials for
    a payload that was itself unsendable — the wrong problem — and the guard against
    submitting garbage sat behind having somewhere to submit it to.
    """
    message = dhis2.push_data_values(UNMAPPED_VALUE)["message"]

    assert "org unit or data element UID" in message
    assert "DHIS2_ENV" not in message, "reported the missing server, not the broken payload"


def test_push_reports_a_missing_server_when_the_payload_is_fine(_no_dhis2_server):
    result = dhis2.push_data_values([
        {"dataElement": "s46m5MS0hxu", "period": "20260728",
         "orgUnit": "at6UHUQatSo", "value": "7"},
    ])

    assert result["status"] == "ERROR"
    assert "DHIS2_ENV" in result["message"]


def test_push_refuses_an_empty_payload(_no_dhis2_server):
    assert dhis2.push_data_values([])["status"] in {"ERROR", "WARNING"}
