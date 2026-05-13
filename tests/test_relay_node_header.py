"""Lock the Meshtastic header byte-15 read into Packet.relay_node.

The relay_node byte (the lowest byte of the last relay node's ID, or 0
for direct packets) is published in every Meshtastic header but was
silently discarded prior to PR #45. These tests prevent that regression
and document the byte layout for future maintainers.

Layout of the 16-byte unencrypted header is mirrored from
``MeshtasticDecoder._parse_header`` in ``src/decode/meshtastic_decoder.py``.
"""

from __future__ import annotations

import struct
import unittest

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder
from src.models.packet import Protocol


def _build_header(
    *,
    dest_id: int = 0xFFFFFFFF,
    source_id: int = 0xDEADBEEF,
    packet_id: int = 0x12345678,
    flags: int = 0x03,
    channel_hash: int = 0x08,
    next_hop: int = 0x00,
    relay_node: int = 0x00,
) -> bytes:
    """Synthesize the 16-byte Meshtastic radio header used in tests.

    Mirrors the on-air byte order documented in
    ``MeshtasticDecoder._parse_header``.
    """
    return (
        struct.pack("<III", dest_id, source_id, packet_id)
        + bytes([flags, channel_hash, next_hop, relay_node])
    )


class TestParseHeaderRelayNode(unittest.TestCase):
    """Exercise the static header parser in isolation."""

    def test_extracts_nonzero_relay_byte(self):
        """A relay node byte at index 15 must surface as ``relay_node``."""
        header = _build_header(relay_node=0x8E)
        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["relay_node"], 0x8E)

    def test_zero_byte_means_direct(self):
        """``relay_node == 0`` is the direct-packet sentinel."""
        header = _build_header(relay_node=0x00)
        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["relay_node"], 0)

    def test_full_byte_range_round_trips(self):
        """Every value 0..255 round-trips through the parser unchanged."""
        for value in (0, 1, 0x7F, 0x80, 0xC0, 0xFE, 0xFF):
            with self.subTest(relay_node=value):
                parsed = MeshtasticDecoder._parse_header(
                    _build_header(relay_node=value)
                )
                self.assertEqual(parsed["relay_node"], value)

    def test_relay_byte_is_independent_of_next_hop(self):
        """Bytes 14 (next_hop) and 15 (relay_node) must not bleed into each
        other. Byte 14 is intentionally not surfaced today."""
        parsed = MeshtasticDecoder._parse_header(
            _build_header(next_hop=0xAA, relay_node=0x55)
        )
        self.assertEqual(parsed["relay_node"], 0x55)


class TestDecodePropagatesRelayNode(unittest.TestCase):
    """Confirm the relay byte makes it from raw bytes onto the Packet."""

    def setUp(self):
        self._decoder = MeshtasticDecoder(CryptoService())

    def test_decode_sets_relay_node_on_packet(self):
        """A full ``decode()`` call must populate ``Packet.relay_node``."""
        raw = _build_header(relay_node=0xAB)

        packet = self._decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.protocol, Protocol.MESHTASTIC)
        self.assertEqual(packet.relay_node, 0xAB)

    def test_decode_default_zero_when_byte_unset(self):
        """Direct packets (byte 15 = 0) yield ``relay_node = 0``."""
        raw = _build_header(relay_node=0x00)

        packet = self._decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.relay_node, 0)

    def test_to_dict_serializes_relay_node(self):
        """The WebSocket payload (``Packet.to_dict()``) must include the
        new field so the dashboard receives it on live packets."""
        raw = _build_header(relay_node=0x42)

        packet = self._decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertIn("relay_node", packet.to_dict())
        self.assertEqual(packet.to_dict()["relay_node"], 0x42)


if __name__ == "__main__":
    unittest.main()
