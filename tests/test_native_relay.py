"""Tests for the native onboard SX1302 relay path.

The native path is identity-preserving: TxService.send_raw_relay
takes the original radio frame, decrements ``hop_limit`` (bits 0-2
of byte 12 of the Meshtastic header), and pushes the bytes through
the HAL with everything else intact — source_id, packet_id,
channel_hash, encrypted body. Other Meshtastic nodes treat the
packet as a legitimate relay rather than a fresh broadcast from
the Meshpoint.
"""
from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch

from src.config import RadioConfig, TransmitConfig
from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.transmit.tx_service import TxService


def _build_packet_bytes(hop_limit: int = 3, hop_start: int = 3) -> bytes:
    """Construct a synthetic 24-byte Meshtastic frame (16-byte header + 8-byte body)."""
    header = bytearray(16)
    # Destination, source, packet ID don't matter for the test.
    header[0:4] = (0xFFFFFFFF).to_bytes(4, "little")
    header[4:8] = (0x12345678).to_bytes(4, "little")
    header[8:12] = (0xDEADBEEF).to_bytes(4, "little")
    flags = (hop_limit & 0x07) | ((hop_start & 0x07) << 5)
    header[12] = flags
    header[13] = 0x08
    header[14] = 0
    header[15] = 0
    body = b"\xab" * 8
    return bytes(header) + body


class _FakeWrapper:
    def __init__(self, send_result: int = 0):
        self.send = MagicMock(return_value=send_result)
        self.get_time_on_air = MagicMock(return_value=120)
        self.get_tx_status = MagicMock(return_value=2)


class TestNativeRelay(unittest.IsolatedAsyncioTestCase):

    def _build_service(self, send_result: int = 0) -> TxService:
        wrapper = _FakeWrapper(send_result=send_result)
        radio = RadioConfig(
            region="US", frequency_mhz=906.875,
            bandwidth_khz=250, spreading_factor=11,
            coding_rate="4/8",
        )
        cfg = TransmitConfig(enabled=True, tx_power_dbm=14)
        with patch("src.transmit.tx_service.TxService."
                   "_persist_derived_node_id_if_needed"):
            return TxService(
                wrapper=wrapper,
                crypto=None,
                channel_plan=None,
                transmit_config=cfg,
                meshcore_tx=None,
                duty_tracker=None,
                radio_config=radio,
                primary_channel_name="LongFast",
                device_id="test-device",
                persist_derived_node_id=False,
            )

    async def test_decrements_hop_limit_in_flags_byte(self):
        svc = self._build_service()
        original = _build_packet_bytes(hop_limit=3, hop_start=3)
        result = await svc.send_raw_relay(original)
        self.assertTrue(result.success)
        # Inspect the bytes pushed through the HAL.
        called_pkt = svc._wrapper.send.call_args.args[0]
        flags = called_pkt.payload[12]
        new_hops = flags & 0x07
        new_hop_start = (flags >> 5) & 0x07
        self.assertEqual(new_hops, 2)
        # hop_start must NOT change so receivers know the original
        # source distance.
        self.assertEqual(new_hop_start, 3)

    async def test_zero_hops_packet_is_refused(self):
        svc = self._build_service()
        original = _build_packet_bytes(hop_limit=0, hop_start=3)
        result = await svc.send_raw_relay(original)
        self.assertFalse(result.success)
        self.assertIn("no hops remaining", result.error)
        svc._wrapper.send.assert_not_called()

    async def test_short_packet_is_refused(self):
        svc = self._build_service()
        result = await svc.send_raw_relay(b"\x00\x01\x02")
        self.assertFalse(result.success)
        self.assertIn("too short", result.error.lower())

    async def test_source_and_packet_id_preserved(self):
        """The whole point of native relay: identity stays intact."""
        svc = self._build_service()
        original = _build_packet_bytes(hop_limit=3)
        await svc.send_raw_relay(original)
        called_pkt = svc._wrapper.send.call_args.args[0]
        # Source ID is bytes 4-8.
        emitted_src = bytes(called_pkt.payload[4:8])
        self.assertEqual(emitted_src, original[4:8])
        # Packet ID is bytes 8-12.
        emitted_id = bytes(called_pkt.payload[8:12])
        self.assertEqual(emitted_id, original[8:12])

    async def test_duty_cycle_block_prevents_send(self):
        svc = self._build_service()
        duty = MagicMock()
        duty.check_budget = MagicMock(return_value=False)
        svc._duty = duty
        original = _build_packet_bytes(hop_limit=3)
        result = await svc.send_raw_relay(original)
        self.assertFalse(result.success)
        self.assertIn("duty cycle", result.error.lower())
        svc._wrapper.send.assert_not_called()

    async def test_disabled_meshtastic_returns_failure(self):
        svc = self._build_service()
        # Force meshtastic_enabled False.
        svc._wrapper = None
        result = await svc.send_raw_relay(_build_packet_bytes())
        self.assertFalse(result.success)
        self.assertIn("not available", result.error.lower())


class TestRelayManagerAsyncDispatch(unittest.IsolatedAsyncioTestCase):
    """Verifies RelayManager handles both sync and async transmit fns."""

    async def test_async_transmit_function_is_awaited(self):
        from src.relay.relay_manager import RelayManager

        manager = RelayManager(enabled=True)
        called_with = []

        async def _async_tx(packet):
            called_with.append(packet)

        manager.set_transmit_function(_async_tx)
        packet = Packet(
            packet_id="aa", source_id="bb", destination_id="cc",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            hop_limit=2,
            raw_radio_packet=_build_packet_bytes(hop_limit=2),
        )
        await manager._relay(packet)
        self.assertEqual(len(called_with), 1)
        self.assertIs(called_with[0], packet)

    async def test_sync_transmit_function_runs_in_thread(self):
        from src.relay.relay_manager import RelayManager

        manager = RelayManager(enabled=True)
        sync_calls = []

        def _sync_tx(packet):
            sync_calls.append(packet)

        manager.set_transmit_function(_sync_tx)
        packet = Packet(
            packet_id="aa", source_id="bb", destination_id="cc",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TEXT,
            hop_limit=2,
        )
        await manager._relay(packet)
        self.assertEqual(len(sync_calls), 1)

    def test_skips_relay_for_unicast_to_local_node(self):
        from src.relay.relay_manager import RelayManager

        manager = RelayManager(enabled=True)
        manager.set_local_node_id("c0ffee42")
        packet = Packet(
            packet_id="aa",
            source_id="7d8b98a9",
            destination_id="c0ffee42",
            protocol=Protocol.MESHTASTIC,
            packet_type=PacketType.TELEMETRY,
            hop_limit=3,
            signal=SignalMetrics(
                rssi=-50.0,
                snr=8.0,
                frequency_mhz=906.875,
                spreading_factor=11,
                bandwidth_khz=250,
            ),
        )
        decision = manager.evaluate(packet)
        self.assertFalse(decision.should_relay)
        self.assertEqual(decision.reason, "dest_local")


if __name__ == "__main__":
    unittest.main()
