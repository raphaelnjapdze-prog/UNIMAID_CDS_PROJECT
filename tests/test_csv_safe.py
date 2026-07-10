"""Tests for the CSV formula-injection guard used in the subscriber fallback."""

import pytest

from components.dashboard import _csv_safe


@pytest.mark.parametrize("trigger", ["=", "+", "-", "@", "\t", "\r"])
def test_formula_triggers_are_neutralized(trigger):
    out = _csv_safe(trigger + "cmd(1)")
    assert out.startswith("'")


def test_normal_values_unchanged():
    assert _csv_safe("user@example.com") == "user@example.com"
    assert _csv_safe("Anopheles gambiae") == "Anopheles gambiae"


def test_empty_string_is_safe():
    assert _csv_safe("") == ""
