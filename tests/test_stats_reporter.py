"""Tests for src/analytics/stats_reporter.py."""

import unittest
from unittest.mock import patch

from src.analytics.stats_reporter import StatsReporter


class TestRecordPacket(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_basic_count(self):
        self.reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 2)
        self.reporter.record_packet("meshcore", "position", -110.0, -2.0, 0, 0)
        self.assertEqual(self.reporter.total_packets, 2)

    def test_protocol_distribution(self):
        self.reporter.record_packet("meshtastic", "text", -80.0, 5.0, 3, 3)
        self.reporter.record_packet("meshtastic", "position", -85.0, 4.0, 3, 2)
        self.reporter.record_packet("meshcore", "text", -90.0, 3.0, 0, 0)
        report = self.reporter.build_report()
        self.assertEqual(report["protocols"]["meshtastic"], 2)
        self.assertEqual(report["protocols"]["meshcore"], 1)

    def test_packet_type_distribution(self):
        self.reporter.record_packet("meshtastic", "text", -80.0, 5.0, 3, 3)
        self.reporter.record_packet("meshtastic", "position", -85.0, 4.0, 3, 2)
        self.reporter.record_packet("meshtastic", "text", -90.0, 3.0, 0, 0)
        report = self.reporter.build_report()
        self.assertEqual(report["packet_types"]["text"], 2)
        self.assertEqual(report["packet_types"]["position"], 1)


class TestRssiBuckets(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_excellent(self):
        self.reporter.record_packet("meshtastic", "text", -70.0, 5.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_histogram"]["excellent"], 1)
        self.assertEqual(report["rssi_histogram"]["good"], 0)

    def test_good(self):
        self.reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_histogram"]["good"], 1)

    def test_fair(self):
        self.reporter.record_packet("meshtastic", "text", -105.0, 5.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_histogram"]["fair"], 1)

    def test_weak(self):
        self.reporter.record_packet("meshtastic", "text", -120.0, 5.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_histogram"]["weak"], 1)

    def test_positive_rssi_ignored(self):
        self.reporter.record_packet("meshtastic", "text", 5.0, 3.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_count"], 0)

    def test_none_rssi_ignored(self):
        self.reporter.record_packet("meshtastic", "text", None, None, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_count"], 0)
        self.assertEqual(report["snr_count"], 0)


class TestHopClassification(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_direct_when_no_hops_consumed(self):
        self.reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["direct_count"], 1)
        self.assertEqual(report["relayed_count"], 0)

    def test_relayed_when_hops_consumed(self):
        self.reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 1)
        report = self.reporter.build_report()
        self.assertEqual(report["direct_count"], 0)
        self.assertEqual(report["relayed_count"], 1)

    def test_direct_when_hop_start_zero(self):
        self.reporter.record_packet("meshtastic", "text", -90.0, 5.0, 0, 0)
        report = self.reporter.build_report()
        self.assertEqual(report["direct_count"], 1)


class TestSignalAverages(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_rssi_sum_and_count(self):
        self.reporter.record_packet("meshtastic", "text", -80.0, 5.0, 3, 3)
        self.reporter.record_packet("meshtastic", "text", -100.0, -3.0, 3, 3)
        report = self.reporter.build_report()
        self.assertEqual(report["rssi_sum"], -180.0)
        self.assertEqual(report["rssi_count"], 2)
        self.assertEqual(report["snr_sum"], 2.0)
        self.assertEqual(report["snr_count"], 2)


class TestFarthestDirect(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_records_farthest(self):
        self.reporter.record_farthest_direct(
            source_id="abc123",
            rssi=-90.0,
            device_lat=40.0, device_lon=-74.0,
            node_lat=40.1, node_lon=-74.1,
            hop_start=3, hop_limit=3,
        )
        report = self.reporter.build_report()
        self.assertIn("farthest_direct", report)
        self.assertGreater(report["farthest_direct"]["miles"], 0)
        self.assertEqual(report["farthest_direct"]["node_id"], "abc123")

    def test_ignores_relayed(self):
        self.reporter.record_farthest_direct(
            source_id="abc123",
            rssi=-90.0,
            device_lat=40.0, device_lon=-74.0,
            node_lat=40.1, node_lon=-74.1,
            hop_start=3, hop_limit=1,
        )
        report = self.reporter.build_report()
        self.assertNotIn("farthest_direct", report)

    def test_ignores_close_nodes(self):
        self.reporter.record_farthest_direct(
            source_id="abc123",
            rssi=-90.0,
            device_lat=40.0, device_lon=-74.0,
            node_lat=40.0, node_lon=-74.0,
            hop_start=3, hop_limit=3,
        )
        report = self.reporter.build_report()
        self.assertNotIn("farthest_direct", report)

    def test_keeps_longest(self):
        self.reporter.record_farthest_direct(
            source_id="near",
            rssi=-80.0,
            device_lat=40.0, device_lon=-74.0,
            node_lat=40.05, node_lon=-74.05,
            hop_start=3, hop_limit=3,
        )
        self.reporter.record_farthest_direct(
            source_id="far",
            rssi=-100.0,
            device_lat=40.0, device_lon=-74.0,
            node_lat=41.0, node_lon=-75.0,
            hop_start=3, hop_limit=3,
        )
        report = self.reporter.build_report()
        self.assertEqual(report["farthest_direct"]["node_id"], "far")


class TestNodeRoster(unittest.TestCase):
    def setUp(self):
        self.reporter = StatsReporter()

    def test_records_changed_nodes(self):
        self.reporter.record_node({"node_id": "abc", "long_name": "Test"})
        self.reporter.record_node({"node_id": "def", "long_name": "Test2"})
        roster = self.reporter.build_node_roster()
        self.assertEqual(len(roster), 2)

    def test_deduplicates_same_node(self):
        self.reporter.record_node({"node_id": "abc", "long_name": "v1"})
        self.reporter.record_node({"node_id": "abc", "long_name": "v2"})
        roster = self.reporter.build_node_roster()
        self.assertEqual(len(roster), 1)
        self.assertEqual(roster[0]["long_name"], "v2")


class TestReset(unittest.TestCase):
    def test_clears_all(self):
        reporter = StatsReporter()
        reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 3)
        reporter.record_node({"node_id": "abc", "long_name": "Test"})
        reporter.reset()

        report = reporter.build_report()
        self.assertEqual(report["total_packets"], 0)
        self.assertEqual(report["protocols"], {})
        self.assertEqual(report["packet_types"], {})
        self.assertEqual(report["direct_count"], 0)
        self.assertEqual(report["rssi_count"], 0)
        self.assertEqual(reporter.build_node_roster(), [])


class TestPacketsPerMinute(unittest.TestCase):
    def test_returns_zero_when_empty(self):
        reporter = StatsReporter()
        self.assertEqual(reporter.packets_per_minute, 0.0)

    def test_positive_after_packets(self):
        # Fast Windows runs can record every packet within one clock tick.
        with patch('src.analytics.stats_reporter.time.monotonic', return_value=100.0) as clock:
            reporter = StatsReporter()
            for _ in range(10):
                reporter.record_packet("meshtastic", "text", -90.0, 5.0, 3, 3)
            clock.return_value = 110.0
            self.assertEqual(reporter.packets_per_minute, 60.0)


if __name__ == "__main__":
    unittest.main()
