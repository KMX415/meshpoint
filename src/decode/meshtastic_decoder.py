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
        raw_app_payload: Optional[bytes] = None

        for key in self._crypto.get_all_keys():
            decrypted_bytes = self._crypto.decrypt_meshtastic(
                encrypted_payload,
                header["packet_id"],
                header["source_id"],
                key=key,
            )
            if decrypted_bytes is None:
                continue
            decoded_payload, packet_type, raw_app_payload = (
                self._decode_payload(decrypted_bytes)
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
            raw_app_payload=raw_app_payload,
            raw_radio_packet=bytes(raw_bytes),
            decrypted=decrypted,
            signal=signal,
            timestamp=datetime.now(timezone.utc),
        )

    def decode_from_api_packet(
        self,
        packet: dict[str, Any],
        signal: Optional[SignalMetrics] = None,
    ) -> Optional[Packet]:
        """Decode a meshtastic-python receive dict (meshtasticd / TCP path).

        meshtastic-python stores the live MeshPacket protobuf in ``raw`` and
        often delivers only the decoded payload variant over TCP. This path
        reuses the same Packet model without round-tripping through LoRa bytes.
        """
        decoded = packet.get("decoded")
        if not isinstance(decoded, dict):
            return None

        source_id = int(packet.get("from", 0) or 0)
        dest_id = int(packet.get("to", 0) or 0xFFFFFFFF)
        packet_id = int(packet.get("id", 0) or 0)
        hop_limit = int(packet.get("hopLimit", 3) or 3)
        hop_start = int(packet.get("hopStart", hop_limit) or hop_limit)
        if hop_limit > hop_start:
            logger.debug(
                "Dropping API packet with impossible hops hl=%d > hs=%d",
                hop_limit,
                hop_start,
            )
            return None

        want_ack = bool(packet.get("wantAck", False))
        via_mqtt = bool(packet.get("viaMqtt", False))
        channel_hash = int(packet.get("channel", 0) or 0) & 0xFF
        relay_node = int(
            packet.get("relayNode", packet.get("relay_node", 0)) or 0
        ) & 0xFF

        portnum = _portnum_from_decoded(decoded)
        inner = decoded.get("payload", b"")
        if isinstance(inner, str):
            try:
                inner = bytes.fromhex(inner)
            except ValueError:
                inner = b""

        decoded_payload = None
        packet_type = PacketType.UNKNOWN
        raw_app_payload: Optional[bytes] = None

        if inner:
            decoded_payload, packet_type, raw_app_payload = self._decode_payload(
                _build_data_bytes(portnum, inner)
            )

        if decoded_payload is None:
            decoded_payload, packet_type = _decoded_from_api_fields(decoded, portnum)
            raw_app_payload = inner or None

        if decoded_payload is None:
            return None

        return Packet(
            packet_id=f"{packet_id:08x}",
            source_id=f"{source_id:08x}",
            destination_id=f"{dest_id:08x}",
            protocol=Protocol.MESHTASTIC,
            packet_type=packet_type,
            hop_limit=hop_limit,
            hop_start=hop_start,
            channel_hash=channel_hash,
            want_ack=want_ack,
            via_mqtt=via_mqtt,
            relay_node=relay_node,
            decoded_payload=decoded_payload,
            encrypted_payload=None,
            raw_app_payload=raw_app_payload,
            raw_radio_packet=None,
            decrypted=True,
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

        Returns None if the header parses but fails a structural-validity
        check (currently only ``hop_limit > hop_start``, which is
        mathematically impossible for an honestly-originated Meshtastic
        packet: hop_limit starts at hop_start and only ever decrements
        through relays). Defense in depth against any future status-code
        blind spot in the wrapper letting corrupted bytes reach the
        decoder.
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

            if hop_limit > hop_start:
                logger.debug(
                    "Dropping packet with impossible hops hl=%d > hs=%d "
                    "(corrupted header bytes; source=0x%08x dest=0x%08x)",
                    hop_limit, hop_start, source_id, dest_id,
                )
                return None

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
    ) -> tuple[Optional[dict[str, Any]], PacketType, Optional[bytes]]:
        """Decode the decrypted protobuf payload.

        The first byte after decryption is the portnum.
        Returns (decoded_dict, packet_type, raw_app_payload). The
        third element is the inner application-payload bytes (the
        bytes that follow ``portnum`` in the Meshtastic Data
        protobuf); the relay TX path needs these to re-emit the
        packet via ``interface.sendData``.
        """
        if len(decrypted) < 2:
            return None, PacketType.UNKNOWN, None

        try:
            return self._try_protobuf_decode(decrypted)
        except Exception:
            logger.debug("Protobuf decode failed", exc_info=True)
            return None, PacketType.UNKNOWN, None

    @staticmethod
    def _try_protobuf_decode(
        payload: bytes,
    ) -> tuple[Optional[dict[str, Any]], PacketType, Optional[bytes]]:
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

            decoded, packet_type = dispatch_portnum(portnum, inner)
            return decoded, packet_type, bytes(inner) if inner else None
        except ImportError:
            return (
                {"raw_hex": payload.hex(), "size": len(payload)},
                PacketType.UNKNOWN,
                None,
            )
        except Exception:
            logger.debug("Data protobuf parse failed", exc_info=True)
            return None, PacketType.UNKNOWN, None

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


def _portnum_from_decoded(decoded: dict[str, Any]) -> int:
    raw = decoded.get("portnum", 0)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str):
        try:
            from meshtastic.protobuf import portnums_pb2

            return int(portnums_pb2.PortNum.Value(raw))
        except (ValueError, KeyError, ImportError):
            return 0
    return 0


def _build_data_bytes(portnum: int, inner: bytes) -> bytes:
    try:
        from meshtastic.protobuf import mesh_pb2

        data_msg = mesh_pb2.Data()
        data_msg.portnum = portnum
        data_msg.payload = inner
        return data_msg.SerializeToString()
    except ImportError:
        return bytes([portnum & 0xFF]) + inner


def _decoded_from_api_fields(
    decoded: dict[str, Any], portnum: int
) -> tuple[Optional[dict[str, Any]], PacketType]:
    """Use meshtastic-python's pre-parsed sub-messages when payload is empty."""
    if "text" in decoded:
        return {"text": decoded["text"]}, PacketType.TEXT
    if "user" in decoded and isinstance(decoded["user"], dict):
        user = decoded["user"]
        return (
            {
                "long_name": user.get("longName", user.get("long_name")),
                "short_name": user.get("shortName", user.get("short_name")),
                "hw_model": user.get("hwModel", user.get("hw_model")),
            },
            PacketType.NODEINFO,
        )
    if "position" in decoded and isinstance(decoded["position"], dict):
        pos = decoded["position"]
        return (
            {
                "latitude": pos.get("latitude"),
                "longitude": pos.get("longitude"),
                "altitude": pos.get("altitude"),
            },
            PacketType.POSITION,
        )
    if portnum:
        return {"portnum": portnum}, PacketType.UNKNOWN
    return None, PacketType.UNKNOWN
