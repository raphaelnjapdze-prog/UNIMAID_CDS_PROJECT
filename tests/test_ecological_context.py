"""Tests for the ecological-estimate boundary (utils.ecological_context).

The estimator refines a complex-level verdict into a probability distribution
over member species — an ESTIMATE, never an identification. These lock: it only
applies to complexes it has rules for (returning None otherwise so no broken
panel renders), it degrades honestly on an unsupported complex (error dict, no
fabricated distribution), and its output is a normalised distribution carrying
the PCR disclaimer.
"""

from utils.ecological_context import (
    complex_for_taxon,
    estimate,
    habitat_options,
    region_options,
    supported_complexes,
)


class TestComplexMapping:
    def test_supported_complexes(self):
        cs = supported_complexes()
        assert "Anopheles gambiae complex" in cs
        assert "Anopheles funestus group" in cs

    def test_maps_various_taxon_formats(self):
        assert complex_for_taxon("Anopheles gambiae complex") == "Anopheles gambiae complex"
        assert complex_for_taxon("An. gambiae complex") == "Anopheles gambiae complex"
        assert complex_for_taxon("Anopheles gambiae complex (s.l.)") == "Anopheles gambiae complex"
        assert complex_for_taxon("Anopheles funestus group") == "Anopheles funestus group"

    def test_returns_none_for_non_estimable(self):
        assert complex_for_taxon("Aedes aegypti") is None
        assert complex_for_taxon("Anopheles") is None
        assert complex_for_taxon("Culex pipiens complex") is None  # no rules for it
        assert complex_for_taxon(None) is None
        assert complex_for_taxon("") is None


class TestOptions:
    def test_region_options_nonempty_without_unknown(self):
        r = region_options()
        assert r
        assert "unknown" not in r
        assert "Kenya" in r

    def test_habitat_options_nonempty_without_unknown(self):
        h = habitat_options()
        assert h
        assert "unknown" not in h


class TestEstimate:
    def test_valid_complex_returns_normalised_distribution(self):
        est = estimate("Anopheles gambiae complex", region="Kenya",
                       habitat="saline_coastal_pool", month=8)
        assert "error" not in est
        dist = est["probability_distribution"]
        assert abs(sum(dist.values()) - 1.0) < 0.01
        # East African saline coastal context should favour the saline specialist merus.
        assert max(dist, key=dist.get) == "merus"
        assert est["estimate_type"] == "ecological_probability_estimate"
        assert "PCR" in est["disclaimer"]

    def test_unsupported_complex_returns_error_not_fabrication(self):
        est = estimate("Culex pipiens complex")
        assert "error" in est
        assert "probability_distribution" not in est  # no invented numbers

    def test_all_unknown_inputs_still_estimate(self):
        est = estimate("Anopheles gambiae complex")
        assert "error" not in est
        assert abs(sum(est["probability_distribution"].values()) - 1.0) < 0.01
