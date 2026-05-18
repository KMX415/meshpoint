"""Capture source for the RAK2287 SX1302 LoRa concentrator.

Requires a Raspberry Pi with the RAK2287 HAT connected via SPI,
and the patched libloragw.so compiled and installed.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.hal.concentrator_config import ConcentratorChannelPlan
from src.hal.sx1302_wrapper import BW_MAP, SX1302Wrapper
from src.models.packet import Protocol, RawCapture
from src.models.signal import SignalMetrics

if TYPE_CHECKING:
    from src.config import RadioConfig

logger = logging.getLogger(__name__)


class ConcentratorCaptureSource(CaptureSource):
    """Captures LoRa packets via the RAK2287 SX1302 concentrator."""

    def __init__(
        self,
        spi_path: str = "/dev/spidev0.0",
        lib_path: Optional[str] = None,
        channel_plan: Optional[ConcentratorChannelPlan] = None,
        poll_interval_ms: int = 10,
        syncword: int = 0x2B,
        radio_config: Optional[RadioConfig] = None,
        sx1261_spi_path: str = "",
    ):
        self._wrapper = SX1302Wrapper(
            lib_path=lib_path,
            spi_path=spi_path,
            sx1261_spi_path=sx1261_spi_path,
        )
        self._channel_plan = self._resolve_channel_plan(
            channel_plan, radio_config
        )
        self._poll_interval = poll_interval_ms / 1000.0
        self._syncword = syncword
        self._running = False

    @staticmethod
    def _resolve_channel_plan(
        channel_plan: Optional[ConcentratorChannelPlan],
        radio_config: Optional[RadioConfig],
    ) -> ConcentratorChannelPlan:
        if radio_config is not None:
            return ConcentratorChannelPlan.from_radio_config(
                region=radio_config.region,
                frequency_mhz=radio_config.frequency_mhz,
                spreading_factor=radio_config.spreading_factor,
                bandwidth_khz=radio_config.bandwidth_khz,
            )
        if channel_plan is not None:
            return channel_plan
        return ConcentratorChannelPlan.meshtastic_us915_default()

    @property
    def name(self) -> str:
        return "concentrator"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        self._wrapper.load()
        self._wrapper.reset()
        self._wrapper.configure(self._channel_plan)
        self._wrapper.start()
        self._wrapper.set_syncword(self._syncword)
        self._running = True
        logger.info(
            "Concentrator capture started (syncword=0x%02X)",
            self._syncword,
        )

    async def stop(self) -> None:
        self._running = False
        self._wrapper.stop()
        logger.info("Concentrator capture stopped")

    async def packets(self) -> AsyncIterator[RawCapture]:
        poll_count = 0
        while self._running:
            raw_packets = self._wrapper.receive()
            poll_count += 1
            if poll_count == 1 or poll_count % 50000 == 0:
                logger.info(
                    "Receive loop alive (poll #%d, %d pkt this cycle)",
                    poll_count, len(raw_packets),
                )

            for pkt in raw_packets:
                signal = SignalMetrics(
                    rssi=pkt.rssi,
                    snr=pkt.snr,
                    frequency_mhz=pkt.frequency_hz / 1_000_000.0,
                    spreading_factor=pkt.spreading_factor,
                    bandwidth_khz=BW_MAP.get(pkt.bandwidth, 125.0),
                    timestamp=datetime.now(timezone.utc),
                )

                yield RawCapture(
                    payload=pkt.payload,
                    signal=signal,
                    capture_source="concentrator",
                    timestamp=datetime.now(timezone.utc),
                    protocol_hint=Protocol.MESHTASTIC,
                )

            await asyncio.sleep(self._poll_interval)
