"""Transmits relay packets via a Meshtastic radio (SX1262) over serial.

The SX1262 runs standard Meshtastic firmware and is connected on a
dedicated serial port, separate from any capture source. Packets
approved by the RelayManager are pushed through the Meshtastic Python
API, which handles encryption, hop management, and protocol compliance.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.config import RelayConfig
from src.models.packet import Packet, Protocol

logger = logging.getLogger(__name__)

PORTNUM_MAP = {
    "text": 1,
    "position": 3,
    "nodeinfo": 4,
    "routing": 5,
    "waypoint": 8,
    "detection_sensor": 10,
    "paxcounter": 34,
    "store_forward": 65,
    "range_test": 66,
    "telemetry": 67,
    "traceroute": 70,
    "neighborinfo": 71,
    "map_report": 73,
}


class MeshtasticTransmitter:
    """Manages a serial connection to an SX1262 relay radio and
    provides a synchronous transmit(packet) callable for RelayManager."""

    def __init__(self, config: RelayConfig):
        self._port = config.serial_port
        self._baud = config.serial_baud
        self._interface = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if not self._port:
            logger.info("Relay transmitter: no serial_port configured, TX disabled")
            return

        try:
            import meshtastic.serial_interface

            self._interface = meshtastic.serial_interface.SerialInterface(
                devPath=self._port,
                noProto=False,
            )
            self._connected = True
            logger.info("Relay transmitter connected on %s", self._port)
        except ImportError:
            logger.error(
                "meshtastic package required for relay TX. "
                "Install with: pip install meshtastic"
            )
        except Exception:
            logger.exception("Failed to open relay radio on %s", self._port)

    def disconnect(self) -> None:
        if self._interface:
            try:
                self._interface.close()
            except Exception:
                pass
            self._interface = None
        self._connected = False
        logger.info("Relay transmitter disconnected")

    def transmit(self, packet: Packet) -> None:
        """Send a packet via the Meshtastic radio.

        Called from RelayManager._relay via asyncio.to_thread,
        so this runs in a worker thread -- safe for blocking I/O.
        """
        if not self._connected or self._interface is None:
            logger.debug("Relay TX skipped: no radio connected")
            return

        if packet.protocol != Protocol.MESHTASTIC:
            logger.debug(
                "Relay TX skipped: %s packets not supported yet",
                packet.protocol.value,
            )
            return

        try:
            self._send_meshtastic(packet)
        except Exception:
            logger.exception(
                "Relay TX failed for packet %s from %s",
                packet.packet_id, packet.source_id,
            )

    def _send_meshtastic(self, packet: Packet) -> None:
        portnum = self._resolve_portnum(packet)
        destination = self._parse_destination(packet.destination_id)
        hop_limit = max(packet.hop_limit - 1, 0)
        channel_index = packet.channel_hash

        payload = self._get_payload(packet)
        if payload is None:
            logger.warning("Relay TX: no payload available for packet %s", packet.packet_id)
            return

        self._interface.sendData(
            payload,
            destinationId=destination,
            portNum=portnum,
            hopLimit=hop_limit,
            channelIndex=channel_index,
        )

        logger.info(
            "Relay TX sent: %s -> %s (port=%d, hops=%d)",
            packet.source_id,
            packet.destination_id,
            portnum,
            hop_limit,
        )

    @staticmethod
    def _resolve_portnum(packet: Packet) -> int:
        return PORTNUM_MAP.get(packet.packet_type.value, 256)

    @staticmethod
    def _parse_destination(dest_id: str) -> int:
        """Convert hex destination string to integer for sendData."""
        try:
            return int(dest_id, 16)
        except (ValueError, TypeError):
            return 0xFFFFFFFF

    @staticmethod
    def _get_payload(packet: Packet) -> Optional[bytes]:
        """Extract the best available payload for retransmission."""
        if packet.encrypted_payload:
            return packet.encrypted_payload

        if packet.decoded_payload:
            raw = packet.decoded_payload.get("raw_bytes")
            if isinstance(raw, bytes):
                return raw
            if isinstance(raw, str):
                return bytes.fromhex(raw)

        return None
