"""Tests for backend/host_stats.py -- best-effort host health for info.mu.

Pure /proc + /sys + shutil reads; on a machine that lacks a field the
value must come back None (never raise), so the whole suite is really a
shape + resilience check.
"""

from __future__ import annotations

import unittest
from unittest import mock

from apps.reticulum.backend import host_stats


class TestReadHost(unittest.TestCase):
    _KEYS = {
        "pi_model", "cpu_temp_c", "load_1m",
        "mem_used_mb", "mem_total_mb", "disk_free_gb", "disk_total_gb",
    }

    def test_read_host_has_exactly_the_expected_keys(self) -> None:
        h = host_stats.read_host()
        self.assertEqual(set(h), self._KEYS)

    def test_every_value_is_none_or_the_right_type(self) -> None:
        h = host_stats.read_host()
        for k in ("pi_model",):
            self.assertTrue(h[k] is None or isinstance(h[k], str))
        for k in ("cpu_temp_c", "load_1m", "disk_free_gb", "disk_total_gb"):
            self.assertTrue(h[k] is None or isinstance(h[k], (int, float)))
        for k in ("mem_used_mb", "mem_total_mb"):
            self.assertTrue(h[k] is None or isinstance(h[k], int))

    def test_disk_is_read_on_this_machine(self) -> None:
        # shutil.disk_usage("/") works everywhere the tests run.
        h = host_stats.read_host()
        self.assertIsNotNone(h["disk_total_gb"])
        self.assertGreater(h["disk_total_gb"], 0)

    def test_helpers_return_none_when_the_source_is_missing(self) -> None:
        # Simulate a non-Linux box: every /proc|/sys read fails.
        with mock.patch(
            "apps.reticulum.backend.host_stats.Path.read_text",
            side_effect=OSError,
        ):
            self.assertIsNone(host_stats._pi_model())
            self.assertIsNone(host_stats._cpu_temp_c())
            self.assertIsNone(host_stats._mem_mb())
        # os.getloadavg raises on Windows -> AttributeError/OSError path.
        with mock.patch("os.getloadavg", side_effect=OSError, create=True):
            self.assertIsNone(host_stats._load_1m())


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
