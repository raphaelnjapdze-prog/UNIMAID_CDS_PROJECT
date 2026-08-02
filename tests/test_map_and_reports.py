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
from components.reports import (
    _compile_specimen_excel,
    _entries_with_photos,
    _entry_label,
    _flatten_specimen_df,
    _genus_counts_text,
    _lga_summary,
    _plain_summary,
    _totals,
)
from utils.data_manager import add_collector_column

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


# ---------------------------------------------------------------------------
# The plain-language summary
# ---------------------------------------------------------------------------
def test_the_summary_counts_mosquitoes_not_entries():
    """"171 records" read as 171 mosquitoes; two entries here hold 1,550."""
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=1000, culex=500), _batch(anopheles=50)]))

    summary = _plain_summary(flat)

    assert "1,550 mosquitoes" in summary
    assert "2** recorded entries" in summary


def test_the_summary_names_anopheles_as_the_malaria_vector():
    """A reader who does not know the genus names still has to understand the finding."""
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=75, culex=25)]))

    summary = _plain_summary(flat)

    assert "75 (75%)" in summary
    assert "transmits malaria" in summary


def test_the_summary_says_so_when_nothing_is_confirmed():
    """Silence would read as 'confirmed', which is the opposite of the truth."""
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=10)]))

    assert "No specimens have been PCR-confirmed" in _plain_summary(flat)


def test_the_summary_handles_an_empty_selection_without_inventing_a_finding():
    flat = _flatten_specimen_df(pd.DataFrame([_batch()]))

    assert "No mosquitoes were counted" in _plain_summary(flat)


# ---------------------------------------------------------------------------
# The photo-evidence picker
# ---------------------------------------------------------------------------
def test_an_entry_with_no_date_does_not_read_as_nat():
    """pd.NaT has a .date() (returning NaT) and is truthy, so an attribute check and an
    `or` fallback both sailed past it and the entry read "NaT · Maiduguri · ..."."""
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=4)]))
    flat.loc[0, "collection_date"] = pd.NaT

    label = _entry_label(flat.iloc[0])

    assert "NaT" not in label
    assert "date n/a" in label


def test_an_entry_label_carries_the_date_place_and_catch():
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=1000, culex=550)]))

    label = _entry_label(flat.iloc[0])

    assert "2026-07-28" in label
    assert "Maiduguri" in label
    assert "1,550 collected" in label


def test_an_entry_label_falls_back_to_the_site_then_to_nothing_known():
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=1, lga=None)]))
    assert "Rice field" in _entry_label(flat.iloc[0])

    bare = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=1, lga=None)]))
    bare.loc[0, "breeding_site_type"] = None
    assert "location n/a" in _entry_label(bare.iloc[0])


def test_a_fully_vialed_batch_reports_its_catch_not_its_remainder():
    """The bug this fixes: a batch nets to zero once every specimen is vialed out, so the
    photo of a collection event that yielded 170 mosquitoes was captioned "0 specimen(s)"."""
    flat = _flatten_specimen_df(pd.DataFrame([
        _batch(anopheles=100, culex=70, vialed={"Anopheles": 100, "Culex": 70}),
    ]))

    label = _entry_label(flat.iloc[0])

    assert "170 collected (all vialed out)" in label
    assert "0 specimen" not in label


def test_a_partly_vialed_batch_says_how_much_left():
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=500, vialed={"Anopheles": 30})]))

    assert "500 collected (30 vialed out)" in _entry_label(flat.iloc[0])


def test_an_untouched_batch_just_says_what_it_caught():
    flat = _flatten_specimen_df(pd.DataFrame([_batch(anopheles=500)]))

    assert "500 collected" in _entry_label(flat.iloc[0])
    assert "vialed out" not in _entry_label(flat.iloc[0])


def test_the_detail_counts_agree_with_the_label():
    """The entry must not contradict itself: a batch labelled "170 collected" had its own
    detail pane read "Anopheles 0, Culex 0, Aedes 0" two lines beneath."""
    flat = _flatten_specimen_df(pd.DataFrame([
        _batch(anopheles=100, culex=70, vialed={"Anopheles": 100, "Culex": 70}),
    ]))

    assert _genus_counts_text(flat.iloc[0]) == "Anopheles 100, Culex 70, Aedes 0"


def test_the_detail_counts_of_an_individual_are_its_own():
    flat = _flatten_specimen_df(pd.DataFrame([_vialed(genus="Culex")]))

    assert _genus_counts_text(flat.iloc[0]) == "Anopheles 0, Culex 1, Aedes 0"


def test_a_vialed_individual_is_still_described_as_a_specimen():
    """A child is one mosquito, not a collection event — it has no catch to report."""
    flat = _flatten_specimen_df(pd.DataFrame([_vialed()]))

    label = _entry_label(flat.iloc[0])

    assert "1 specimen" in label
    assert "collected" not in label, "a child has no catch of its own to describe"


def test_the_picker_offers_only_entries_that_have_a_photo():
    """The section shows one photo at a time; an entry without one opened onto
    "No photo for this entry", which is not evidence."""
    with_photo = _batch(anopheles=1)
    with_photo["photo_urls"] = ["https://example.test/a.jpg"]
    rows = [with_photo, _batch(anopheles=2), _batch(anopheles=3)]

    evidence = _entries_with_photos(pd.DataFrame(rows))

    assert len(evidence) == 1
    assert evidence.iloc[0]["_first_photo"] == "https://example.test/a.jpg"


def test_the_picker_is_empty_when_nothing_has_a_photo():
    evidence = _entries_with_photos(pd.DataFrame([_batch(anopheles=1)]))

    assert evidence.empty, "an empty picker is what drives the 'no photos' message"


def test_the_picker_survives_a_frame_with_no_photo_column_at_all():
    """Filters can produce a frame that never had the column; it must not raise."""
    df = pd.DataFrame([{"lga": "Jere", "collection_date": "2026-07-28"}])

    evidence = _entries_with_photos(df)

    assert evidence.empty
    assert "_first_photo" in evidence.columns


def test_a_blank_lga_is_one_absence_not_two():
    """A missing LGA arrives as NULL from some write paths and "" from others. Grouped as
    they come, one absence became a "Not recorded" row and a nameless one beside it."""
    rows = [_batch(anopheles=1, lga=None), _batch(anopheles=2, lga=""), _batch(anopheles=4, lga="  ")]

    table = _lga_summary(_flatten_specimen_df(pd.DataFrame(rows)))

    assert list(table["LGA"]) == ["Not recorded"]
    assert list(table["Total"]) == [7]


def test_a_blank_lga_is_not_counted_as_a_covered_lga():
    """"LGAs covered" is a count of places visited; a blank is the absence of one."""
    rows = [_batch(anopheles=1, lga="Jere"), _batch(anopheles=1, lga=None), _batch(anopheles=1, lga="")]

    flat = _flatten_specimen_df(pd.DataFrame(rows))

    assert _totals(flat)["lgas"] == ["Jere"], "a blank must not be counted beside a real LGA"
    assert "Not recorded" not in _plain_summary(flat)


def test_the_lga_table_is_one_row_per_lga_sorted_by_size():
    rows = [_batch(anopheles=10), _batch(anopheles=400, lga="Jere"), _batch(culex=5)]

    table = _lga_summary(_flatten_specimen_df(pd.DataFrame(rows)))

    assert list(table["LGA"]) == ["Jere", "Maiduguri"], "largest catch should lead"
    assert list(table["Total"]) == [400, 15]


# ---------------------------------------------------------------------------
# Collector identity
# ---------------------------------------------------------------------------
COLLECTOR_ID = "4f3a9c21-0e5b-4a7d-9c11-77aa8899bbcc"


def _row_with_collector(label=None):
    screening = {"screening_method": "field_subsample", "result": {"genus": "Anopheles"}}
    if label:
        screening["collector_label"] = label
    return {"collector_id": COLLECTOR_ID, "field_screening_result": screening}


def test_one_collector_reads_as_one_name():
    """A batch carried the label and its vialed children did not, so a single person's work
    showed as "Raphael Njapdze" on one row and "ID 4f3a9c21…" on the hundred beneath it."""
    rows = [_row_with_collector("Raphael Njapdze")] + [_row_with_collector() for _ in range(5)]

    out = add_collector_column(pd.DataFrame(rows))

    assert set(out["Collector"]) == {"Raphael Njapdze"}


def test_an_unknown_collector_still_falls_back_to_an_id():
    """Nothing is invented: with no label anywhere, the id remains the honest answer."""
    out = add_collector_column(pd.DataFrame([_row_with_collector()]))

    assert out["Collector"].iloc[0].startswith("ID ")


def test_two_collectors_are_not_merged():
    other = _row_with_collector()
    other["collector_id"] = "99999999-0000-0000-0000-000000000000"
    rows = [_row_with_collector("Raphael Njapdze"), other]

    labels = set(add_collector_column(pd.DataFrame(rows))["Collector"])

    assert "Raphael Njapdze" in labels
    assert any(v.startswith("ID 99999999") for v in labels)


def test_a_screening_result_stored_as_a_json_string_keeps_its_method():
    """JSONB does not always arrive parsed; an isinstance check blanked the column."""
    import json

    row = _batch(anopheles=7)
    row["field_screening_result"] = json.dumps(row["field_screening_result"])

    flat = _flatten_specimen_df(pd.DataFrame([row]))

    assert flat["screening_method"].iloc[0] == "manual_field_log"
    assert int(flat["Anopheles"].iloc[0]) == 7
