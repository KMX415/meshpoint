from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import AsyncIterator, Optional

from src.capture.base import CaptureSource
from src.models.packet import RawCapture
from src.models.signal import SignalMetrics

logger = logging.getLogger(__name__)


class SerialSelfOriginFilter:
    """Drops a USB stick's self-telemetry/nodeinfo; keeps its own text.

    meshtastic-python publishes the stick's locally originated beacons on
    the same ``meshtastic.receive`` topic as over-the-air packets. Those
    beacons have no real RF signal (firmware leaves rxRssi/rxSnr at 0),
    so the pipeline would otherwise store spammy −100 dBm readings.

    Text from a BLE/WiFi client on the same stick is exempt: it is real
    chat content and must reach Messages even though ``from`` is the
    stick's own node id.

    Credit: javastraat/meshpoint ``db4de9f`` + ``c190b3e``.
    """

    _TEXT_PORTNUMS = frozenset({"TEXT_MESSAGE_APP", 1})

    def __init__(self, own_node_num: Optional[int] = None) -> None:
        self._own_node_num = own_node_num

    @property
    def own_node_num(self) -> Optional[int]:
        return self._own_node_num

    def set_own_node_num(self, node_num: Optional[int]) -> None:
        self._own_node_num = node_num

    @staticmethod
    def read_own_node_num(interface) -> Optional[int]:
        """Best-effort read of ``interface.myInfo.my_node_num``."""
        try:
            return int(interface.myInfo.my_node_num)
        except Exception:
            logger.debug(
                "Could not read own node number from serial interface",
                exc_info=True,
            )
            return None

    def should_drop(self, packet: dict) -> bool:
        if self._own_node_num is None:
            return False
        if packet.get("from") != self._own_node_num:
            return False
        return not self._is_text_message(packet)

    @classmethod
    def _is_text_message(cls, packet: dict) -> bool:
        decoded = packet.get("decoded")
        if not isinstance(decoded, dict):
            return False
        return decoded.get("portnum") in cls._TEXT_PORTNUMS


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
        self._self_origin = SerialSelfOriginFilter()
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

            own_node = SerialSelfOriginFilter.read_own_node_num(self._interface)
            self._self_origin.set_own_node_num(own_node)

            pub.subscribe(self._on_receive, "meshtastic.receive")
            self._running = True
            if own_node is not None:
                logger.info(
                    "Serial capture started on %s (own_node=%08x)",
                    self._port or "auto-detect",
                    own_node,
                )
            else:
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
        self._self_origin.set_own_node_num(None)
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
            raw_capture = self._packet_to_raw_capture(packet)
            if raw_capture:
                try:
                    self._queue.put_nowait(raw_capture)
                except asyncio.QueueFull:
                    logger.warning("Serial capture queue full")
        except Exception:
            logger.debug("Failed to convert serial packet", exc_info=True)

    def _packet_to_raw_capture(self, packet: dict) -> Optional[RawCapture]:
        """Convert a meshtastic-python packet dict to a RawCapture."""
        if self._self_origin.should_drop(packet):
            logger.debug(
                "Dropping self-originated non-text packet from own node %08x",
                self._self_origin.own_node_num,
            )
            return None

        raw_bytes = packet.get("raw", b"")
        if isinstance(raw_bytes, str):
            raw_bytes = bytes.fromhex(raw_bytes)

        if not raw_bytes and "decoded" in packet:
            raw_bytes = self._reconstruct_raw(packet)

        if not raw_bytes:
            return None

        signal = SignalMetrics(
            rssi=float(packet.get("rxRssi", packet.get("rssi", -100))),
            snr=float(packet.get("rxSnr", packet.get("snr", 0))),
            frequency_mhz=906.875,
            spreading_factor=11,
            bandwidth_khz=250.0,
        )

        return RawCapture(
            payload=raw_bytes,
            signal=signal,
            capture_source=self.name,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _reconstruct_raw(packet: dict) -> bytes:
        """Build a minimal raw frame from a decoded meshtastic packet.

        When the meshtastic library provides already-decoded data
        without raw bytes, we reconstruct the header so the pipeline
        can process it. The payload portion will be empty/encrypted.
        """
        import struct

        dest = packet.get("to", 0xFFFFFFFF)
        source = packet.get("from", 0)
        pkt_id = packet.get("id", 0)

        hop_limit = packet.get("hopLimit", 3)
        hop_start = packet.get("hopStart", 3)
        want_ack = packet.get("wantAck", False)

        flags = (hop_limit & 0x07)
        if want_ack:
            flags |= 0x08
        flags |= (hop_start & 0x07) << 5

        channel = packet.get("channel", 0)

        header = struct.pack("<III", dest, source, pkt_id)
        header += bytes([flags, channel, 0, 0])

        encoded = packet.get("encoded", b"")
        if isinstance(encoded, str):
            encoded = bytes.fromhex(encoded)

        return header + encoded
