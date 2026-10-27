"""TelemetryStore -- the in-memory collector for received telemetry.
Pure, Mac-runnable."""

from __future__ import annotations

import time
import unittest

from apps.reticulum.backend.telemetry_store import TelemetryStore


class TestTelemetryStore(unittest.TestCase):
    def test_records_and_lists_newest_first(self) -> None:
        s = TelemetryStore()
        s.record("aa", {"temperature_c": 40.0, "info": "node A"}, "A")
        time.sleep(0.01)
        s.record("bb", {"info": "node B"}, "B")
        rows = s.all()
        self.assertEqual([r["destination_hash"] for r in rows], ["bb", "aa"])
        self.assertEqual(rows[1]["temperature_c"], 40.0)
        self.assertEqual(rows[1]["name"], "A")

    def test_latest_reading_replaces_previous(self) -> None:
        s = TelemetryStore()
        s.record("aa", {"temperature_c": 40.0}, "A")
        s.record("aa", {"temperature_c": 45.0, "info": "warmer"}, "A")
        self.assertEqual(s.count(), 1)
        self.assertEqual(s.all()[0]["temperature_c"], 45.0)

    def test_name_is_kept_when_a_later_frame_omits_it(self) -> None:
        s = TelemetryStore()
        s.record("aa", {"info": "x"}, "Alice")
        s.record("aa", {"info": "y"}, "")
        self.assertEqual(s.all()[0]["name"], "Alice")

    def test_empty_frame_is_ignored(self) -> None:
        s = TelemetryStore()
        s.record("aa", {"time": 123}, "A")   # time only, nothing useful
        s.record("bb", {}, "B")
        s.record("", {"info": "x"}, "C")     # no hash
        self.assertEqual(s.count(), 0)

    def test_stale_entries_are_pruned(self) -> None:
        s = TelemetryStore()
        s.record("aa", {"info": "old"}, "A")
        s._by_hash["aa"]["received_at"] = time.time() - 48 * 3600
        s.record("bb", {"info": "new"}, "B")
        self.assertEqual([r["destination_hash"] for r in s.all()], ["bb"])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
