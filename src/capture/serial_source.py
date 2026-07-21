from __future__ import annotations

import asyncio
import base64
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
        self._radio_info: dict = {"channel_table": {}}
        self._queue: asyncio.Queue[RawCapture] = asyncio.Queue(maxsize=500)

    @property
    def name(self) -> str:
        return "serial"

    @property
    def is_running(self) -> bool:
        return self._running

    def resolve_channel_index(self, name: str) -> Optional[int]:
        """This stick's channel-table index for ``name``, or None."""
        table = self._radio_info.get("channel_table") or {}
        for idx, ch_name in table.items():
            if ch_name == name:
                return idx
        return None

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
            try:
                modem_preset = self._read_modem_preset_name(self._interface)
                self._radio_info["channel_table"] = self._read_channel_table(
                    self._interface, modem_preset
                )
            except Exception:
                logger.debug(
                    "Could not read channel table from serial interface",
                    exc_info=True,
                )
                self._radio_info["channel_table"] = {}

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

    @staticmethod
    def _read_modem_preset_name(interface) -> Optional[str]:
        try:
            from meshtastic.protobuf import config_pb2

            lora = interface.localNode.localConfig.lora
            if not lora.use_preset:
                return None
            return config_pb2.Config.LoRaConfig.ModemPreset.Name(lora.modem_preset)
        except Exception:
            return None

    @staticmethod
    def _read_channel_table(
        interface, modem_preset_name: Optional[str] = None
    ) -> dict:
        """Stick channel-table index -> name (for locally decoded packets)."""
        from meshtastic.protobuf import channel_pb2

        table: dict[int, str] = {}
        channels = getattr(interface.localNode, "channels", None) or []
        for ch in channels:
            if ch.role == channel_pb2.Channel.Role.DISABLED:
                continue
            name = ch.settings.name
            if not name and ch.role == channel_pb2.Channel.Role.PRIMARY:
                name = modem_preset_name
            if name:
                table[ch.index] = name
        return table

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
        elif not isinstance(raw_bytes, (bytes, bytearray)):
            # meshtastic-python sets packet["raw"] to the MeshPacket
            # protobuf object, not bytes. Treat as absent so reconstruct runs.
            raw_bytes = b""

        if not raw_bytes:
            # Reconstruct even without "decoded": encrypted/decoded share a
            # oneof, so undecryptable-by-stick traffic has no "decoded" key.
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
            pre_decoded=self._build_pre_decoded(packet),
        )

    def _build_pre_decoded(self, packet: dict) -> Optional[dict]:
        """Portnum + payload when the stick already decrypted locally."""
        decoded = packet.get("decoded")
        if not isinstance(decoded, dict):
            return None
        portnum_name = decoded.get("portnum")
        if portnum_name is None:
            return None
        try:
            if isinstance(portnum_name, int):
                portnum = portnum_name
            else:
                from meshtastic.protobuf import portnums_pb2

                portnum = portnums_pb2.PortNum.Value(portnum_name)
        except (ImportError, ValueError):
            logger.debug("Unrecognized portnum name %r", portnum_name)
            return None

        payload_b64 = decoded.get("payload", "")
        try:
            payload = base64.b64decode(payload_b64) if payload_b64 else b""
        except Exception:
            logger.debug("Could not base64-decode decoded.payload", exc_info=True)
            payload = b""

        result = {
            "portnum": portnum,
            "payload": payload,
            "request_id": decoded.get("requestId", 0),
        }
        channel_idx = packet.get("channel")
        if channel_idx is not None:
            channel_name = self._radio_info.get("channel_table", {}).get(
                channel_idx
            )
            if channel_name:
                result["channel_name"] = channel_name
        return result

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

        # MessageToDict base64-encodes the MeshPacket "encrypted" field.
        encoded = packet.get("encrypted", b"")
        if isinstance(encoded, str):
            encoded = base64.b64decode(encoded)

        return header + encoded
