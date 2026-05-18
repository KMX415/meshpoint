"""Tests for the SpectralScanResult histogram parser.

These tests do not touch the SX1302 HAL; they exercise the
percentile / median / floor derivations directly with synthetic
histograms shaped to match the ``lgw_spectral_scan_get_results``
output format.
"""
from __future__ import annotations

import unittest

from src.hal.sx1302_spectral_scan import SpectralScanResult


def _make_result(levels, counts, freq_hz=906_875_000, nb_scan=1024):
    return SpectralScanResult(
        levels_dbm=tuple(levels),
        counts=tuple(counts),
        frequency_hz=freq_hz,
        nb_scan=nb_scan,
        timestamp=0.0,
    )


class TestPercentileDerivation(unittest.TestCase):

    def test_median_picks_middle_bin_for_uniform_histogram(self) -> None:
        levels = list(range(-130, -60, 2))   # 35 levels
        counts = [10] * 35                   # uniform
        result = _make_result(levels, counts)
        # Cumulative reaches 50% (175) exactly at index 17 (level -96).
        self.assertEqual(result.median_dbm, -96.0)

    def test_floor_returns_10th_percentile(self) -> None:
        levels = list(range(-130, -60, 2))
        counts = [10] * 35
        result = _make_result(levels, counts)
        # Cumulative >= 35 (10% of 350) at index 3 (level -124).
        self.assertEqual(result.floor_dbm, -124.0)

    def test_quiet_environment_clusters_at_low_dbm_bins(self) -> None:
        levels = list(range(-130, -60, 2))
        counts = [0] * 35
        for i in range(4):
            counts[i] = 250
        result = _make_result(levels, counts)
        # 50% target = 500. Cumulative reaches 500 at level -128
        # (second bin, where 250+250=500 >= 500).
        self.assertEqual(result.median_dbm, -128.0)
        # 10% target = 100. Cumulative reaches 100 at level -130
        # (first bin, count 250 >= 100).
        self.assertEqual(result.floor_dbm, -130.0)

    def test_busy_environment_pushes_median_higher(self) -> None:
        levels = list(range(-130, -60, 2))
        counts = [0] * 35
        # Heavy traffic pushes most samples up around -90 dBm.
        for i in range(18, 25):
            counts[i] = 100
        result = _make_result(levels, counts)
        # 50% target = 350. Cumulative passes 350 at index 21
        # (cumulative=400 >= 350), level -130 + 21*2 = -88.
        self.assertEqual(result.median_dbm, -88.0)
        self.assertGreater(result.median_dbm, -100.0)

    def test_empty_histogram_returns_none(self) -> None:
        levels = list(range(-130, -60, 2))
        counts = [0] * 35
        result = _make_result(levels, counts)
        self.assertIsNone(result.median_dbm)
        self.assertIsNone(result.floor_dbm)
        self.assertEqual(result.total_samples, 0)


class TestRealWorldShapes(unittest.TestCase):
    """Histograms shaped like what we expect to see on hardware."""

    def test_rural_quiet_floor_sits_around_minus_120(self) -> None:
        # Most samples cluster between -125 and -115 dBm.
        levels = list(range(-130, -60, 2))
        counts = [0] * 35
        counts[2] = 50
        counts[3] = 200
        counts[4] = 400
        counts[5] = 250
        counts[6] = 100
        counts[7] = 24
        result = _make_result(levels, counts)
        self.assertAlmostEqual(result.floor_dbm, -124.0, delta=2.0)
        self.assertAlmostEqual(result.median_dbm, -122.0, delta=2.0)

    def test_urban_with_interferers_widens_distribution(self) -> None:
        # A more spread-out histogram with sporadic interferer bins.
        levels = list(range(-130, -60, 2))
        counts = [0] * 35
        # Quiet baseline.
        for i in range(2, 8):
            counts[i] = 100
        # Plus an interferer bursting at -90 dBm.
        counts[20] = 80
        counts[21] = 40
        result = _make_result(levels, counts)
        self.assertLess(result.median_dbm, -100.0)
        # Floor should still anchor to the quiet baseline.
        self.assertLess(result.floor_dbm, -120.0)


if __name__ == "__main__":
    unittest.main()
