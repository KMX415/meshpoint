"""Lock the structural-validity check in ``MeshtasticDecoder._parse_header``.

A Meshtastic packet originates with ``hop_limit == hop_start`` and decrements
``hop_limit`` at each relay while ``hop_start`` stays fixed. Therefore at any
point in flight, ``hop_limit <= hop_start`` is mathematically guaranteed.
A header where ``hop_limit > hop_start`` cannot have come from an honest
sender, which means the flags byte was corrupted in transit (or the
"packet" was decoded from RF noise that the chip flagged with a status
the wrapper failed to filter).

The check exists as defense in depth alongside the wrapper's status-code
filter (CRC_BAD / NO_CRC / unknown all dropped at source). If a future HAL
revision introduces a new status code, or if the chip ever false-positives
a CRC at the noise floor, this check still catches the resulting corrupted
header before a phantom node row materializes in SQLite.

History: shipped in v0.7.3 alongside the wrapper-level NO_CRC filter after
fleet diagnostics on nopemesh and kmax confirmed corrupted headers were
the root cause of phantom node accumulation (>72k phantoms on nopemesh's
local DB before the fix).
"""

from __future__ import annotations

import struct
import unittest

from src.decode.crypto_service import CryptoService
from src.decode.meshtastic_decoder import MeshtasticDecoder


def _flags(hop_limit: int, hop_start: int, *,
           want_ack: bool = False, via_mqtt: bool = False) -> int:
    """Pack a Meshtastic header flags byte.

    Bits 0-2: hop_limit
    Bit  3:   want_ack
    Bit  4:   via_mqtt
    Bits 5-7: hop_start
    """
    return (
        (hop_limit & 0x07)
        | (0x08 if want_ack else 0)
        | (0x10 if via_mqtt else 0)
        | ((hop_start & 0x07) << 5)
    )


def _build_header(
    *,
    flags: int,
    dest_id: int = 0xFFFFFFFF,
    source_id: int = 0xDEADBEEF,
    packet_id: int = 0x12345678,
    channel_hash: int = 0x08,
    next_hop: int = 0x00,
    relay_node: int = 0x00,
) -> bytes:
    """Synthesize a 16-byte Meshtastic header for tests."""
    return (
        struct.pack("<III", dest_id, source_id, packet_id)
        + bytes([flags, channel_hash, next_hop, relay_node])
    )


class TestParseHeaderRejectsImpossibleHops(unittest.TestCase):
    """``hop_limit > hop_start`` returns None at the parser."""

    def test_hl_greater_than_hs_returns_none(self):
        """Classic corruption signature: hl=4 > hs=3 cannot happen
        on an honestly-originated packet."""
        header = _build_header(flags=_flags(hop_limit=4, hop_start=3))

        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNone(parsed)

    def test_extreme_hl_greater_than_hs_returns_none(self):
        """hl=7 (max) > hs=0 (also possible after corruption) returns None."""
        header = _build_header(flags=_flags(hop_limit=7, hop_start=0))

        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNone(parsed)

    def test_hl_equal_to_hs_is_accepted(self):
        """A direct (zero-hop-consumed) packet has hl == hs. Real."""
        header = _build_header(flags=_flags(hop_limit=3, hop_start=3))

        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["hop_limit"], 3)
        self.assertEqual(parsed["hop_start"], 3)

    def test_hl_less_than_hs_is_accepted(self):
        """A relayed packet has hl < hs. Real."""
        header = _build_header(flags=_flags(hop_limit=2, hop_start=4))

        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["hop_limit"], 2)
        self.assertEqual(parsed["hop_start"], 4)

    def test_zero_hop_packet_is_accepted(self):
        """A node configured with max_hops=0 transmits with hl=0/hs=0."""
        header = _build_header(flags=_flags(hop_limit=0, hop_start=0))

        parsed = MeshtasticDecoder._parse_header(header)

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["hop_limit"], 0)
        self.assertEqual(parsed["hop_start"], 0)


class TestDecodeRejectsImpossibleHops(unittest.TestCase):
    """End-to-end: ``decode()`` returns None for hl > hs packets,
    so no Packet object reaches the storage layer."""

    def setUp(self):
        self._decoder = MeshtasticDecoder(CryptoService())

    def test_decode_returns_none_for_impossible_hops(self):
        """A full ``decode()`` call must reject corrupted hop arithmetic
        before constructing a Packet object. This is the structural
        guarantee that prevents phantom node rows."""
        raw = _build_header(flags=_flags(hop_limit=5, hop_start=2))

        packet = self._decoder.decode(raw)

        self.assertIsNone(packet)

    def test_decode_succeeds_for_valid_hops(self):
        """Sanity check: plausible hop arithmetic still decodes normally."""
        raw = _build_header(flags=_flags(hop_limit=2, hop_start=5))

        packet = self._decoder.decode(raw)

        self.assertIsNotNone(packet)
        self.assertEqual(packet.hop_limit, 2)
        self.assertEqual(packet.hop_start, 5)


class TestImpossibleHopsAcrossFlagsCombinations(unittest.TestCase):
    """The hl > hs check must trigger regardless of want_ack / via_mqtt."""

    def test_with_want_ack_set(self):
        header = _build_header(
            flags=_flags(hop_limit=4, hop_start=3, want_ack=True)
        )
        self.assertIsNone(MeshtasticDecoder._parse_header(header))

    def test_with_via_mqtt_set(self):
        header = _build_header(
            flags=_flags(hop_limit=6, hop_start=1, via_mqtt=True)
        )
        self.assertIsNone(MeshtasticDecoder._parse_header(header))

    def test_with_both_flag_bits_set(self):
        header = _build_header(
            flags=_flags(hop_limit=7, hop_start=2,
                         want_ack=True, via_mqtt=True)
        )
        self.assertIsNone(MeshtasticDecoder._parse_header(header))


if __name__ == "__main__":
    unittest.main()
