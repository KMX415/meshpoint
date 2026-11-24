"""Receive coding-rate metadata must not alter configured transmission."""

from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.capture.concentrator_source import ConcentratorCaptureSource
from src.config import RadioConfig, TransmitConfig
from src.hal.sx1302_wrapper import BW_250KHZ, ConcentratorPacket
from src.transmit.tx_service import TxService


class TestConcentratorCodingRate(unittest.IsolatedAsyncioTestCase):
    async def _capture(self, coderate: int, radio: RadioConfig):
        packet = ConcentratorPacket(
            payload=b"synthetic-frame",
            frequency_hz=906875000,
            rssi=-80.0,
            snr=7.5,
            spreading_factor=11,
            bandwidth=BW_250KHZ,
            coderate=coderate,
            crc_ok=True,
            timestamp_us=12345,
        )
        source = ConcentratorCaptureSource(radio_config=radio)
        source._wrapper = Mock()
        source._wrapper.receive.return_value = [packet]
        source._running = True
        stream = source.packets()
        try:
            capture = await anext(stream)
        finally:
            source._running = False
            await stream.aclose()
        source._wrapper.send.assert_not_called()
        self.assertEqual(capture.payload, packet.payload)
        self.assertEqual(capture.signal.rssi, packet.rssi)
        self.assertEqual(capture.signal.snr, packet.snr)
        self.assertEqual(capture.signal.bandwidth_khz, 250.0)
        self.assertEqual(capture.signal.spreading_factor, 11)
        self.assertEqual(capture.signal.frequency_mhz, 906.875)
        return capture

    async def test_received_rates_reach_dashboard_metadata(self):
        radio = RadioConfig(frequency_mhz=906.875, coding_rate="4/8")
        for hal_rate, expected in ((1, "4/5"), (2, "4/6"), (3, "4/7"), (4, "4/8")):
            with self.subTest(hal_rate=hal_rate):
                capture = await self._capture(hal_rate, radio)
                self.assertEqual(capture.signal.to_dict()["coding_rate"], expected)

    async def test_undefined_rates_are_not_reported_as_4_8(self):
        for hal_rate in (0, 5, 255):
            with self.subTest(hal_rate=hal_rate):
                capture = await self._capture(hal_rate, RadioConfig(frequency_mhz=906.875))
                self.assertEqual(capture.signal.to_dict()["coding_rate"], "Unknown")

    async def test_receiving_different_rate_preserves_tx_packet(self):
        for configured, hal_rate in (("4/5", 1), ("4/6", 2), ("4/7", 3), ("4/8", 4)):
            with self.subTest(configured=configured):
                radio = RadioConfig(frequency_mhz=906.875, coding_rate=configured)
                tx = TxService(
                    radio_config=radio,
                    transmit_config=TransmitConfig(node_id=12345678),
                    persist_derived_node_id=False,
                )
                before = tx._build_hal_packet(b"synthetic-tx")
                self.assertEqual(before.coderate, hal_rate)
                await self._capture(2 if hal_rate == 1 else 1, radio)
                after = tx._build_hal_packet(b"synthetic-tx")
                self.assertEqual(radio.coding_rate, configured)
                self.assertEqual(bytes(after), bytes(before))


if __name__ == "__main__":
    unittest.main()
