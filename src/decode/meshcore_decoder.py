from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from typing import Any, Optional

from src.decode.crypto_service import CryptoService
from src.models.node import Node
from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.models.telemetry import Telemetry

logger = logging.getLogger(__name__)

MESHCORE_HEADER_SIZE = 8
MSG_TEXT = 0x01
MSG_POSITION = 0x02
MSG_TELEMETRY = 0x03
MSG_NODEINFO = 0x04
MSG_ROUTING = 0x05
MSG_ACK = 0x06


class MeshcoreDecoder:
    """Decodes raw Meshcore LoRa frames into structured Packet objects.

    Parses the fixed-size header and dispatches the encrypted body to
    per-message-type handlers (text, position, telemetry, nodeinfo,
    routing, ack).
    """

    def __init__(self, crypto: CryptoService):
        self._crypto = crypto

    def decode(
        self, raw_bytes: bytes, signal: Optional[SignalMetrics] = None
    ) -> Optional[Packet]:
        if len(raw_bytes) < MESHCORE_HEADER_SIZE:
            logger.debug("Meshcore packet too short: %d bytes", len(raw_bytes))
            return None

        header = self._parse_header(raw_bytes[:MESHCORE_HEADER_SIZE])
        if header is None:
            return None

        encrypted_payload = raw_bytes[MESHCORE_HEADER_SIZE:]

        decrypted_bytes = self._crypto.decrypt_meshcore(
            encrypted_payload,
            header["packet_id"],
            header["source_id"],
        )

        decoded_payload = None
        packet_type = PacketType.UNKNOWN
        decrypted = False

        if decrypted_bytes and len(decrypted_bytes) > 0:
            decoded_payload, packet_type = self._decode_payload(
                decrypted_bytes
            )
            decrypted = decoded_payload is not None

        return Packet(
            packet_id=f"{header['packet_id']:04x}",
            source_id=f"{header['source_id']:04x}",
            destination_id=f"{header['dest_id']:04x}",
            protocol=Protocol.MESHCORE,
            packet_type=packet_type,
            hop_limit=header.get("hop_count", 0),
            decoded_payload=decoded_payload,
            encrypted_payload=encrypted_payload if not decrypted else None,
            decrypted=decrypted,
            signal=signal,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _parse_header(header_bytes: bytes) -> Optional[dict]:
        """Parse the 8-byte Meshcore header into its component fields.

        Layout:
        [0:2]  packet ID     (uint16 LE)
        [2:4]  source addr   (uint16 LE)
        [4:6]  dest addr     (uint16 LE)
        [6]    hop count
        [7]    flags (msg type in lower nibble)
        """
        try:
            packet_id, source_id, dest_id = struct.unpack_from(
                "<HHH", header_bytes, 0
            )
            hop_count = header_bytes[6]
            flags = header_bytes[7]

            return {
                "packet_id": packet_id,
                "source_id": source_id,
                "dest_id": dest_id,
                "hop_count": hop_count,
                "flags": flags,
                "msg_type": flags & 0x0F,
            }
        except Exception:
            logger.debug("Failed to parse Meshcore header", exc_info=True)
            return None

    def _decode_payload(
        self, decrypted: bytes
    ) -> tuple[Optional[dict[str, Any]], PacketType]:
        """Decode Meshcore payload based on message type byte."""
        if len(decrypted) < 1:
            return None, PacketType.UNKNOWN

        msg_type = decrypted[0]
        body = decrypted[1:]

        type_map = {
            MSG_TEXT: (self._decode_text, PacketType.TEXT),
            MSG_POSITION: (self._decode_position, PacketType.POSITION),
            MSG_TELEMETRY: (self._decode_telemetry, PacketType.TELEMETRY),
            MSG_NODEINFO: (self._decode_nodeinfo, PacketType.NODEINFO),
            MSG_ROUTING: (None, PacketType.ROUTING),
            MSG_ACK: (None, PacketType.ROUTING),
        }

        if msg_type in type_map:
            decoder_fn, ptype = type_map[msg_type]
            if decoder_fn:
                result = decoder_fn(body)
                return result, ptype
            return {"msg_type": msg_type}, ptype

        return None, PacketType.UNKNOWN

    @staticmethod
    def _decode_text(payload: bytes) -> dict[str, Any]:
        return {"text": payload.decode("utf-8", errors="replace")}

    @staticmethod
    def _decode_position(payload: bytes) -> Optional[dict[str, Any]]:
        """Decode position -- expects protobuf but falls back to raw."""
        if len(payload) < 8:
            return {"raw_hex": payload.hex()}
        try:
            lat_i, lon_i = struct.unpack_from("<ii", payload, 0)
            return {
                "latitude": lat_i * 1e-7,
                "longitude": lon_i * 1e-7,
            }
        except Exception:
            return {"raw_hex": payload.hex()}

    @staticmethod
    def _decode_telemetry(payload: bytes) -> Optional[dict[str, Any]]:
        return {"raw_hex": payload.hex(), "size": len(payload)}

    @staticmethod
    def _decode_nodeinfo(payload: bytes) -> Optional[dict[str, Any]]:
        """Decode node advertisement (name + key)."""
        try:
            name_end = payload.index(0x00) if 0x00 in payload else len(payload)
            name = payload[:name_end].decode("utf-8", errors="replace")
            return {"long_name": name}
        except Exception:
            return {"raw_hex": payload.hex()}

    def extract_node_update(self, packet: Packet) -> Optional[Node]:
        """Build a Node update from a decoded MeshCore packet.

        Unlike Meshtastic, MeshCore does not broadcast a separate periodic
        position packet: a node's coordinates ride on its advertisement
        (``adv_lat``/``adv_lon``), which the event adapter classifies as
        ``NODEINFO``. We therefore extract position from both ``NODEINFO``
        and ``POSITION`` packets so MeshCore nodes appear on the map.
        """
        if not packet.decoded_payload:
            return None

        node = Node(
            node_id=packet.source_id,
            protocol=packet.protocol.value,
            last_heard=packet.timestamp,
        )

        if packet.packet_type == PacketType.NODEINFO:
            node.long_name = packet.decoded_payload.get("long_name")
            self._apply_position(node, packet.decoded_payload)

        if packet.packet_type == PacketType.POSITION:
            self._apply_position(node, packet.decoded_payload)

        node.latest_signal = packet.signal
        return node

    @staticmethod
    def _apply_position(node: Node, payload: dict[str, Any]) -> None:
        """Copy lat/lon onto ``node`` when the payload carries both."""
        lat = payload.get("latitude")
        lon = payload.get("longitude")
        if lat is None or lon is None:
            return
        node.latitude = lat
        node.longitude = lon

    def extract_telemetry(self, packet: Packet) -> Optional[Telemetry]:
        if packet.packet_type != PacketType.TELEMETRY:
            return None
        if not packet.decoded_payload:
            return None
        return Telemetry(
            node_id=packet.source_id,
            timestamp=packet.timestamp,
        )
