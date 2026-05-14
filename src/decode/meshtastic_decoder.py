from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from typing import Any, Optional

from src.decode.crypto_service import CryptoService
from src.decode.portnum_handlers import dispatch_portnum
from src.models.node import Node
from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics
from src.models.telemetry import Telemetry

logger = logging.getLogger(__name__)

MESHTASTIC_HEADER_SIZE = 16
BROADCAST_ADDR = 0xFFFFFFFF


class MeshtasticDecoder:
    """Decodes raw Meshtastic LoRa frames into structured Packet objects."""

    def __init__(self, crypto: CryptoService):
        self._crypto = crypto

    def decode(
        self, raw_bytes: bytes, signal: Optional[SignalMetrics] = None
    ) -> Optional[Packet]:
        if len(raw_bytes) < MESHTASTIC_HEADER_SIZE:
            logger.debug("Packet too short: %d bytes", len(raw_bytes))
            return None

        header = self._parse_header(raw_bytes[:MESHTASTIC_HEADER_SIZE])
        if header is None:
            return None

        encrypted_payload = raw_bytes[MESHTASTIC_HEADER_SIZE:]

        decoded_payload = None
        packet_type = PacketType.UNKNOWN
        decrypted = False

        for key in self._crypto.get_all_keys():
            decrypted_bytes = self._crypto.decrypt_meshtastic(
                encrypted_payload,
                header["packet_id"],
                header["source_id"],
                key=key,
            )
            if decrypted_bytes is None:
                continue
            decoded_payload, packet_type = self._decode_payload(
                decrypted_bytes
            )
            if decoded_payload is not None:
                decrypted = True
                break

        if not decrypted and encrypted_payload:
            packet_type = PacketType.ENCRYPTED
            decoded_payload = {
                "encrypted": True,
                "payload_size": len(encrypted_payload),
                "channel_hash": header["channel_hash"],
            }

        return Packet(
            packet_id=f"{header['packet_id']:08x}",
            source_id=f"{header['source_id']:08x}",
            destination_id=f"{header['dest_id']:08x}",
            protocol=Protocol.MESHTASTIC,
            packet_type=packet_type,
            hop_limit=header["hop_limit"],
            hop_start=header["hop_start"],
            channel_hash=header["channel_hash"],
            want_ack=header["want_ack"],
            via_mqtt=header["via_mqtt"],
            relay_node=header["relay_node"],
            decoded_payload=decoded_payload,
            encrypted_payload=encrypted_payload if not decrypted else None,
            decrypted=decrypted,
            signal=signal,
            timestamp=datetime.now(timezone.utc),
        )

    @staticmethod
    def _parse_header(header_bytes: bytes) -> Optional[dict]:
        """Parse the 16-byte unencrypted Meshtastic radio header.

        Layout:
        [0:4]  destination node ID  (uint32 LE)
        [4:8]  sender node ID      (uint32 LE)
        [8:12] packet ID            (uint32 LE)
        [12]   flags byte: bits 0-2=hop_limit, bit 3=want_ack,
               bit 4=via_mqtt, bits 5-7=hop_start
        [13]   channel hash
        [14]   next_hop (relay)
        [15]   relay_node (lowest byte of last relay node's ID; 0 = direct)
        """
        try:
            dest_id, source_id, packet_id = struct.unpack_from(
                "<III", header_bytes, 0
            )
            flags = header_bytes[12]
            channel_hash = header_bytes[13]
            relay_node = header_bytes[15]

            hop_limit = flags & 0x07
            want_ack = bool(flags & 0x08)
            via_mqtt = bool(flags & 0x10)
            hop_start = (flags >> 5) & 0x07

            return {
                "dest_id": dest_id,
                "source_id": source_id,
                "packet_id": packet_id,
                "hop_limit": hop_limit,
                "hop_start": hop_start,
                "want_ack": want_ack,
                "via_mqtt": via_mqtt,
                "channel_hash": channel_hash,
                "relay_node": relay_node,
            }
        except Exception:
            logger.debug("Failed to parse header", exc_info=True)
            return None

    def _decode_payload(
        self, decrypted: bytes
    ) -> tuple[Optional[dict[str, Any]], PacketType]:
        """Decode the decrypted protobuf payload.

        The first byte after decryption is the portnum.
        Returns (decoded_dict, packet_type).
        """
        if len(decrypted) < 2:
            return None, PacketType.UNKNOWN

        try:
            return self._try_protobuf_decode(decrypted)
        except Exception:
            logger.debug("Protobuf decode failed", exc_info=True)
            return None, PacketType.UNKNOWN

    @staticmethod
    def _try_protobuf_decode(
        payload: bytes,
    ) -> tuple[Optional[dict[str, Any]], PacketType]:
        """Attempt to decode the inner Data protobuf message.

        The decrypted payload is a serialized protobuf `Data` message
        containing portnum + actual payload bytes.
        """
        try:
            from meshtastic.protobuf import mesh_pb2

            data_msg = mesh_pb2.Data()
            data_msg.ParseFromString(payload)
            portnum = data_msg.portnum
            inner = data_msg.payload

            return dispatch_portnum(portnum, inner)
        except ImportError:
            return {"raw_hex": payload.hex(), "size": len(payload)}, PacketType.UNKNOWN
        except Exception:
            logger.debug("Data protobuf parse failed", exc_info=True)
            return None, PacketType.UNKNOWN

    def extract_node_update(self, packet: Packet) -> Optional[Node]:
        """Extract node metadata from a decoded packet if applicable."""
        if not packet.decoded_payload:
            return None

        node = Node(
            node_id=packet.source_id,
            protocol=packet.protocol.value,
            last_heard=packet.timestamp,
        )

        if packet.packet_type == PacketType.ENCRYPTED:
            node.latest_signal = packet.signal
            return node

        if packet.packet_type == PacketType.NODEINFO:
            node.long_name = packet.decoded_payload.get("long_name")
            node.short_name = packet.decoded_payload.get("short_name")
            node.hardware_model = packet.decoded_payload.get("hw_model")

        if packet.packet_type == PacketType.POSITION:
            node.latitude = packet.decoded_payload.get("latitude")
            node.longitude = packet.decoded_payload.get("longitude")
            node.altitude = packet.decoded_payload.get("altitude")

        node.latest_signal = packet.signal
        return node

    def extract_telemetry(self, packet: Packet) -> Optional[Telemetry]:
        """Extract telemetry data from a decoded telemetry packet."""
        if packet.packet_type != PacketType.TELEMETRY:
            return None
        if not packet.decoded_payload:
            return None

        return Telemetry(
            node_id=packet.source_id,
            battery_level=packet.decoded_payload.get("battery_level"),
            voltage=packet.decoded_payload.get("voltage"),
            temperature=packet.decoded_payload.get("temperature"),
            humidity=packet.decoded_payload.get("humidity"),
            barometric_pressure=packet.decoded_payload.get("barometric_pressure"),
            channel_utilization=packet.decoded_payload.get("channel_utilization"),
            air_util_tx=packet.decoded_payload.get("air_util_tx"),
            uptime_seconds=packet.decoded_payload.get("uptime_seconds"),
            timestamp=packet.timestamp,
        )
