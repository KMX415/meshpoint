"""Tests for RSSI display helpers in log_format."""

import unittest

from src.log_format import _rssi_bar


class TestLogFormatRssi(unittest.TestCase):
    def test_unknown_rssi_renders_empty_bar(self):
        bar = _rssi_bar(None)
        self.assertIn("░", bar)
        self.assertNotIn("▓", bar)

    def test_real_rssi_renders_filled_segments(self):
        bar = _rssi_bar(-87.0)
        self.assertIn("▓", bar)


if __name__ == "__main__":
    unittest.main()
