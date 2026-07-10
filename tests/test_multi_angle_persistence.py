"""Tests for the multi-angle capture -> specimen_records persistence bridge."""

import components.multi_angle_capture as mac
import utils.data_manager as dm


class TestParseGps:
    def test_comma_separated(self):
        assert mac._parse_gps("12.5, 3.25") == (12.5, 3.25)

    def test_semicolon_separated(self):
        assert mac._parse_gps("12.5; 3.25") == (12.5, 3.25)

    def test_empty_and_malformed(self):
        assert mac._parse_gps("") == (None, None)
        assert mac._parse_gps(None) == (None, None)
        assert mac._parse_gps("not gps") == (None, None)
        assert mac._parse_gps("1, 2, 3") == (None, None)


def test_submit_returns_none_without_supabase(monkeypatch):
    # No Supabase client -> honest None, no insert attempted, no crash.
    monkeypatch.setattr(dm, "get_supabase_client", lambda: None)
    assert dm.submit_multi_angle_capture_entry(angle_images={}, statuses={}) is None


def test_capture_method_stays_out_of_genus_reporting():
    # A multi_angle_capture record must not be read as a species/genus claim.
    result = {"screening_method": "multi_angle_capture", "result": {"angles": {}}}
    assert dm.extract_primary_genus(result) is None
    assert dm.extract_genus_counts_from_screening(result) == {}
