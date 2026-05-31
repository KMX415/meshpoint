"""Tests for RSSI and hop display helpers in log_format."""

import unittest

from src.log_format import _format_hop_relay, _rssi_bar
from src.models.packet import Packet, PacketType, Protocol


class TestLogFormatRssi(unittest.TestCase):
    def test_unknown_rssi_renders_empty_bar(self):
        bar = _rssi_bar(None)
        self.assertIn("░", bar)
        self.assertNotIn("▓", bar)

    def test_real_rssi_renders_filled_segments(self):
        bar = _rssi_bar(-87.0)
        self.assertIn("▓", bar)


class TestLogFormatHopRelay(unittest.TestCase):
    def _packet(self, **kwargs) -> Packet:
        defaults = {
            "packet_id": "00000001",
            "source_id": "7d8b98a9",
            "destination_id": "ffffffff",
            "protocol": Protocol.MESHTASTIC,
            "packet_type": PacketType.TEXT,
        }
        defaults.update(kwargs)
        return Packet(**defaults)

    def test_direct_packet_shows_hops_and_relay(self):
        label = _format_hop_relay(
            self._packet(hop_limit=7, hop_start=7, relay_node=0xA9)
        )
        self.assertIn("hl=7/7", label)
        self.assertIn("hops=0", label)
        self.assertIn("relay=0xa9", label)
        self.assertIn("direct", label)

    def test_relayed_packet_shows_hop_count(self):
        label = _format_hop_relay(
            self._packet(hop_limit=5, hop_start=7, relay_node=0x77)
        )
        self.assertIn("hops=2", label)
        self.assertIn("relayed", label)

    def test_non_meshtastic_omits_hop_label(self):
        label = _format_hop_relay(
            self._packet(protocol=Protocol.MESHCORE, hop_limit=3, hop_start=3)
        )
        self.assertEqual(label, "")


if __name__ == "__main__":
    unittest.main()
