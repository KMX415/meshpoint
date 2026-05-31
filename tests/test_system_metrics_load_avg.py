"""Parsing tests for the /proc/loadavg reader in system metrics."""

import unittest
from unittest.mock import patch

from src.api.routes import system_metrics


class TestReadLoadAvg(unittest.TestCase):
    def test_parses_three_averages(self):
        with patch.object(
            system_metrics.Path,
            "read_text",
            return_value="0.42 0.55 0.61 1/234 5678",
        ):
            self.assertEqual(system_metrics._read_load_avg(), (0.42, 0.55, 0.61))

    def test_returns_none_when_unavailable(self):
        with patch.object(
            system_metrics.Path, "read_text", side_effect=FileNotFoundError
        ):
            self.assertIsNone(system_metrics._read_load_avg())

    def test_returns_none_on_malformed_content(self):
        with patch.object(
            system_metrics.Path, "read_text", return_value="garbage"
        ):
            self.assertIsNone(system_metrics._read_load_avg())


if __name__ == "__main__":
    unittest.main()
