"""Tests for ``SX1302Wrapper.receive`` packet filtering.

Locks in the contract that CRC_BAD packets are dropped at the source
rather than being passed downstream as if they were valid packets.
Without this filter, RF-corrupted bytes flow into the Meshtastic
decoder where they create three classes of noise:
  - phantom node IDs (corrupted source field)
  - false ENCRYPTED packets (corrupted channel hash byte)
  - garbled-but-readable text (corrupted payload mid-packet)
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock

from src.hal.sx1302_types import LgwPktRxS
from src.hal.sx1302_wrapper import (
    BW_250KHZ,
    LGW_PKT_MAX,
    STAT_CRC_BAD,
    STAT_CRC_OK,
    STAT_NO_CRC,
    SX1302Wrapper,
)


def _set_packet(
    pkt: LgwPktRxS,
    *,
    status: int,
    size: int,
    if_chain: int = 0,
    rssi: float = -50.0,
    snr: float = 7.0,
    payload_byte: int = 0x42,
) -> None:
    """Populate the minimum LgwPktRxS fields the wrapper reads."""
    pkt.status = status
    pkt.size = size
    pkt.if_chain = if_chain
    pkt.datarate = 11
    pkt.bandwidth = BW_250KHZ
    pkt.coderate = 0
    pkt.rssic = rssi
    pkt.snr = snr
    pkt.freq_hz = 906_875_000
    pkt.count_us = 12345
    for i in range(min(size, 256)):
        pkt.payload[i] = payload_byte


def _build_wrapper() -> SX1302Wrapper:
    """Build a wrapper with a mocked ctypes library, ready to receive()."""
    wrapper = SX1302Wrapper()
    wrapper._lib = MagicMock()
    wrapper._started = True
    return wrapper


class TestReceiveFiltersCrcBad(unittest.TestCase):
    """CRC_BAD packets are filtered before reaching the decoder."""

    def test_crc_bad_packet_is_dropped(self):
        wrapper = _build_wrapper()

        def populate(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_CRC_BAD, size=32)
            return 1

        wrapper._lib.lgw_receive.side_effect = populate

        result = wrapper.receive()

        self.assertEqual(result, [])
        self.assertEqual(wrapper.crc_bad_count, 1)

    def test_crc_ok_packet_passes_through(self):
        wrapper = _build_wrapper()

        def populate(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_CRC_OK, size=16)
            return 1

        wrapper._lib.lgw_receive.side_effect = populate

        result = wrapper.receive()

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].crc_ok)
        self.assertEqual(len(result[0].payload), 16)
        self.assertEqual(wrapper.crc_bad_count, 0)

    def test_no_crc_packet_still_passes_through(self):
        """STAT_NO_CRC was passed through pre-fix; that behavior is unchanged.

        Locking it in so a future tightening of the filter is a deliberate
        decision, not an accident.
        """
        wrapper = _build_wrapper()

        def populate(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_NO_CRC, size=16)
            return 1

        wrapper._lib.lgw_receive.side_effect = populate

        result = wrapper.receive()

        self.assertEqual(len(result), 1)
        self.assertFalse(result[0].crc_ok)
        self.assertEqual(wrapper.crc_bad_count, 0)

    def test_mixed_batch_returns_only_good_packets(self):
        wrapper = _build_wrapper()

        def populate(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_CRC_OK, size=16, rssi=-40.0)
            _set_packet(pkt_array[1], status=STAT_CRC_BAD, size=32, rssi=-75.0)
            _set_packet(pkt_array[2], status=STAT_CRC_OK, size=24, rssi=-55.0)
            _set_packet(pkt_array[3], status=STAT_CRC_BAD, size=8, rssi=-80.0)
            return 4

        wrapper._lib.lgw_receive.side_effect = populate

        result = wrapper.receive()

        self.assertEqual(len(result), 2)
        rssi_values = sorted(p.rssi for p in result)
        self.assertEqual(rssi_values, [-55.0, -40.0])
        self.assertEqual(wrapper.crc_bad_count, 2)

    def test_crc_bad_counter_persists_across_calls(self):
        wrapper = _build_wrapper()

        def populate_one_bad(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_CRC_BAD, size=32)
            return 1

        wrapper._lib.lgw_receive.side_effect = populate_one_bad

        wrapper.receive()
        wrapper.receive()
        wrapper.receive()

        self.assertEqual(wrapper.crc_bad_count, 3)

    def test_size_zero_packet_is_skipped_before_status_check(self):
        """size==0 is a separate skip path that still works after the fix."""
        wrapper = _build_wrapper()

        def populate(_max, pkt_array):
            _set_packet(pkt_array[0], status=STAT_CRC_OK, size=0)
            return 1

        wrapper._lib.lgw_receive.side_effect = populate

        result = wrapper.receive()

        self.assertEqual(result, [])
        self.assertEqual(wrapper.crc_bad_count, 0)

    def test_receive_returns_empty_when_not_started(self):
        wrapper = SX1302Wrapper()
        wrapper._lib = MagicMock()

        result = wrapper.receive()

        self.assertEqual(result, [])
        wrapper._lib.lgw_receive.assert_not_called()

    def test_lgw_receive_error_returns_empty(self):
        wrapper = _build_wrapper()
        wrapper._lib.lgw_receive.return_value = -1

        result = wrapper.receive()

        self.assertEqual(result, [])
        self.assertEqual(wrapper.crc_bad_count, 0)


class TestReceiveBatchSize(unittest.TestCase):
    def test_uses_lgw_pkt_max_constant(self):
        """Sanity check: the wrapper requests LGW_PKT_MAX packets per poll."""
        wrapper = _build_wrapper()
        wrapper._lib.lgw_receive.return_value = 0

        wrapper.receive()

        args, _ = wrapper._lib.lgw_receive.call_args
        self.assertEqual(args[0], LGW_PKT_MAX)


if __name__ == "__main__":
    unittest.main()
