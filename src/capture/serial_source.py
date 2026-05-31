from __future__ import annotations

import asyncio
import logging
from typing import AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.capture.meshtastic_packet_adapter import packet_dict_to_raw_capture
from src.models.packet import RawCapture

logger = logging.getLogger(__name__)


class SerialCaptureSource(CaptureSource):
    """Captures packets from a Meshtastic radio connected via USB serial.

    Uses the meshtastic-python pub/sub API to receive decoded packets.
    Packets arrive already decoded, so they are re-serialized as raw
    capture events for the pipeline to process uniformly.
    """

    def __init__(
        self,
        port: Optional[str] = None,
        baud: int = 115200,
    ):
        self._port = port
        self._baud = baud
        self._interface = None
        self._running = False
        self._queue: asyncio.Queue[RawCapture] = asyncio.Queue(maxsize=500)

    @property
    def name(self) -> str:
        return "serial"

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        try:
            import meshtastic.serial_interface
            from pubsub import pub

            if self._port:
                self._interface = meshtastic.serial_interface.SerialInterface(
                    devPath=self._port
                )
            else:
                self._interface = meshtastic.serial_interface.SerialInterface()

            pub.subscribe(self._on_receive, "meshtastic.receive")
            self._running = True
            logger.info(
                "Serial capture started on %s",
                self._port or "auto-detect",
            )
        except ImportError:
            logger.error(
                "meshtastic package not installed. "
                "Install with: pip install meshtastic"
            )
            raise
        except Exception:
            logger.exception("Failed to open serial interface")
            raise

    async def stop(self) -> None:
        self._running = False
        if self._interface:
            try:
                self._interface.close()
            except Exception:
                pass
            self._interface = None
        logger.info("Serial capture stopped")

    async def packets(self) -> AsyncIterator[RawCapture]:
        while self._running:
            try:
                raw = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                yield raw
            except asyncio.TimeoutError:
                continue

    def _on_receive(self, packet, interface) -> None:
        """Callback invoked by meshtastic-python on packet reception."""
        if not self._running:
            return

        try:
            raw_capture = packet_dict_to_raw_capture(packet, "serial")
            if raw_capture:
                try:
                    self._queue.put_nowait(raw_capture)
                except asyncio.QueueFull:
                    logger.warning("Serial capture queue full")
        except Exception:
            logger.debug("Failed to convert serial packet", exc_info=True)

