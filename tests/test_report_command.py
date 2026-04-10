"""Tests for the meshpoint report CLI formatting helpers."""

from __future__ import annotations

import unittest

from src.cli.report_command import (
    _bar,
    _fmt_rssi,
    _fmt_temp,
    _fmt_uptime,
)


class TestFmtUptime(unittest.TestCase):

    def test_minutes_only(self):
        self.assertEqual(_fmt_uptime(300), "5m")

    def test_hours_and_minutes(self):
        self.assertEqual(_fmt_uptime(3720), "1h 2m")

    def test_days_hours(self):
        self.assertEqual(_fmt_uptime(90000), "1d 1h 0m")

    def test_zero(self):
        self.assertEqual(_fmt_uptime(0), "0m")

    def test_float_input(self):
        result = _fmt_uptime(3661.5)
        self.assertEqual(result, "1h 1m")


class TestFmtRssi(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(_fmt_rssi(-85.3), "-85.3 dBm")

    def test_none(self):
        self.assertEqual(_fmt_rssi(None), "--")

    def test_zero(self):
        self.assertEqual(_fmt_rssi(0), "0.0 dBm")


class TestFmtTemp(unittest.TestCase):

    def test_valid(self):
        self.assertIn("42", _fmt_temp(42))
        self.assertIn("C", _fmt_temp(42))

    def test_none(self):
        self.assertEqual(_fmt_temp(None), "N/A")


class TestBar(unittest.TestCase):

    def test_empty_bar(self):
        result = _bar(0, 100, width=10)
        self.assertIn("░" * 10, result)

    def test_full_bar(self):
        result = _bar(100, 100, width=10)
        self.assertIn("█" * 10, result)

    def test_half_bar(self):
        result = _bar(50, 100, width=10)
        self.assertIn("█" * 5, result)

    def test_over_max_clamps(self):
        result = _bar(200, 100, width=10)
        self.assertIn("█" * 10, result)

    def test_zero_max(self):
        result = _bar(50, 0, width=10)
        self.assertIn("░" * 10, result)


if __name__ == "__main__":
    unittest.main()
