"""The map and the Excel summary must show specimens, not rows.

Both had the same defect the DHIS2 export did, in different clothing: a row was treated as
a specimen. A manual_field_log row is a whole collection event holding raw genus counts, and
a vialed-out individual inherits its batch's coordinates verbatim.

  * The map drew one marker per row, so a batch of 500 with 100 vialed out put 101 pins on a
    single coordinate — the map got slower and less readable with every specimen processed.
    The batch's own pin read "Undetermined", because the popup asked for one genus and a
    batch has several: the row holding the catch was the one it could not describe.
  * The Excel summary reported len(df) under "Total Specimens Logged", so a catch of 1,570
    across three collection events headlined as 3.
"""
import pandas as pd

from components.dashboard import _collection_points
from components.reports import _compile_specimen_excel, _flatten_specimen_df

LAT, LON = 11.8, 13.15


def _batch(anopheles=0, culex=0, vialed=None, lat=LAT, lon=LON, lga="Maiduguri"):
    result = {"anopheles_count": anopheles, "culex_count": culex,
              "aedes_count": 0, "other_genera_count": 0}
    if vialed:
        result["vialed_out"] = vialed
    return {
        "gps_lat": lat, "gps_lon": lon, "lga": lga, "breeding_site_type": "Rice field",
        "pcr_status": "not_submitted", "photo_urls": [], "collection_date": "2026-07-28",
        "field_screening_result": {"screening_method": "manual_field_log", "result": result},
    }


def _vialed(genus="Anopheles", lat=LAT, lon=LON, lga="Maiduguri", pcr="not_submitted"):
    return {
        "gps_lat": lat, "gps_lon": lon, "lga": lga, "breeding_site_type": "Rice field",
        "pcr_status": pcr, "photo_urls": [], "collection_date": "2026-07-28",
        "field_screening_result": {"screening_method": "field_subsample", "result": {"genus": genus}},
    }


# ---------------------------------------------------------------------------
# Map markers
# ---------------------------------------------------------------------------
def test_one_marker_per_coordinate_not_per_row():
    rows = [_batch(anopheles=500, vialed={"Anopheles": 100})] + [_vialed() for _ in range(100)]

    points = _collection_points(pd.DataFrame(rows))

    assert len(points) == 1, "101 rows at one coordinate must not draw 101 markers"
    assert points[0]["records"] == 101


def test_a_marker_reports_the_catch_and_conserves_it():
    """400 left in the batch + 100 vialed children = the 500 originally caught."""
    rows = [_batch(anopheles=500, culex=50, vialed={"Anopheles": 100})]
    rows += [_vialed() for _ in range(100)]

    counts = _collection_points(pd.DataFrame(rows))[0]["counts"]

    assert counts == {"Anopheles": 500, "Culex": 50}


def test_a_batch_only_site_is_described_not_called_undetermined():
    """The popup used to read "Undetermined" for exactly the rows holding the counts."""
    point = _collection_points(pd.DataFrame([_batch(anopheles=30, culex=4)]))[0]

    assert point["counts"] == {"Anopheles": 30, "Culex": 4}
    assert point["lgas"] == {"Maiduguri"}


def test_distinct_coordinates_stay_distinct():
    rows = [_batch(anopheles=1), _vialed(lat=12.0, lon=13.4, lga="Jere")]

    points = _collection_points(pd.DataFrame(rows))

    assert len(points) == 2
    assert {tuple(sorted(p["lgas"])) for p in points} == {("Maiduguri",), ("Jere",)}


def test_a_confirmed_specimen_is_visible_among_unconfirmed_ones():
    """Marker colour follows the best status at the point — one confirmation is the news."""
    rows = [_batch(anopheles=10), _vialed(pcr="confirmed"), _vialed()]

    assert "confirmed" in _collection_points(pd.DataFrame(rows))[0]["pcr"]


# ---------------------------------------------------------------------------
# Excel summary
# ---------------------------------------------------------------------------
def _summary(rows):
    flat = _flatten_specimen_df(pd.DataFrame(rows))
    book = _compile_specimen_excel(flat)
    sheets = pd.read_excel(book, sheet_name=None)
    summary = sheets["Executive_Summary"].set_index("Metric")["Value"].to_dict()
    return summary, sheets


def test_the_summary_separates_specimens_from_records():
    """Three rows, 1,570 mosquitoes. The headline used to be 3."""
    rows = [_batch(anopheles=1000, culex=500), _batch(anopheles=50), _vialed()]

    summary, _ = _summary(rows)

    assert summary["Total Specimens Caught"] == 1551
    assert summary["Records (collection events + identifications)"] == 3


def test_the_workbook_breaks_counts_down_by_lga():
    rows = [_batch(anopheles=10), _batch(anopheles=4, lga="Jere")]

    _, sheets = _summary(rows)

    assert "LGA_Breakdown" in sheets
    by_lga = sheets["LGA_Breakdown"].set_index("LGA")["Anopheles"].to_dict()
    assert by_lga == {"Maiduguri": 10, "Jere": 4}


def test_a_screening_result_stored_as_a_json_string_keeps_its_method():
    """JSONB does not always arrive parsed; an isinstance check blanked the column."""
    import json

    row = _batch(anopheles=7)
    row["field_screening_result"] = json.dumps(row["field_screening_result"])

    flat = _flatten_specimen_df(pd.DataFrame([row]))

    assert flat["screening_method"].iloc[0] == "manual_field_log"
    assert int(flat["Anopheles"].iloc[0]) == 7
