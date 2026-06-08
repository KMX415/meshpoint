"""Meshtastic packet construction for native LoRa transmission.

Builds properly formatted, encrypted Meshtastic packets matching
the firmware's on-air format. Packets are suitable for feeding
directly into lgw_send() via the SX1302 HAL.
"""

from __future__ import annotations

import logging
import struct

from src.decode.crypto_service import CryptoService

logger = logging.getLogger(__name__)

BROADCAST_ADDR = 0xFFFFFFFF
PORTNUM_TEXT_MESSAGE = 1
PORTNUM_NODEINFO = 4
PORTNUM_ADMIN = 6
HW_MODEL_PRIVATE_HW = 255


class MeshtasticPacketBuilder:
    """Constructs encrypted Meshtastic packets ready for RF transmission."""

    def __init__(self, crypto: CryptoService):
        self._crypto = crypto

    def build_text_message(
        self,
        text: str,
        dest: int,
        source_id: int,
        packet_id: int,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
        want_ack: bool = False,
    ) -> bytes | None:
        """Build a complete encrypted TEXT_MESSAGE_APP packet.

        Returns the full on-air byte sequence (header + ciphertext),
        or None if encryption fails.
        """
        inner = self._serialize_data(PORTNUM_TEXT_MESSAGE, text.encode("utf-8"))
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )
        if ciphertext is None:
            logger.error("Encryption failed for packet %d", packet_id)
            return None

        header = self._build_header(
            dest, source_id, packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=want_ack,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    def build_nodeinfo(
        self,
        source_id: int,
        packet_id: int,
        long_name: str,
        short_name: str,
        hw_model: int = HW_MODEL_PRIVATE_HW,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
    ) -> bytes | None:
        """Build a broadcast NODEINFO_APP packet announcing this node.

        Wraps a serialized ``User`` protobuf in the standard encrypted
        Meshtastic envelope. Recipients use this to populate their
        contact list so DMs can be addressed by name.
        """
        node_id_str = f"!{source_id:08x}"
        user_payload = self._serialize_user(
            node_id_str, long_name, short_name, hw_model
        )
        inner = self._serialize_data(PORTNUM_NODEINFO, user_payload)
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )
        if ciphertext is None:
            logger.error("Encryption failed for nodeinfo packet %d", packet_id)
            return None

        header = self._build_header(
            BROADCAST_ADDR, source_id, packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=False,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    def build_admin_message(
        self,
        admin_payload: bytes,
        dest: int,
        source_id: int,
        packet_id: int,
        admin_key: bytes,
        admin_channel_name: str = "admin",
        hop_limit: int = 3,
        hop_start: int = 3,
        want_ack: bool = True,
    ) -> bytes | None:
        """Build an encrypted ADMIN_APP packet using the admin channel PSK."""
        inner = self._serialize_data(PORTNUM_ADMIN, admin_payload)
        channel_hash = self._crypto.compute_channel_hash(
            admin_channel_name, admin_key
        )
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=admin_key
        )
        if ciphertext is None:
            logger.error("Admin encryption failed for packet %d", packet_id)
            return None

        header = self._build_header(
            dest,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=want_ack,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    @staticmethod
    def _serialize_data(portnum: int, payload: bytes) -> bytes:
        """Serialize a mesh_pb2.Data protobuf manually.

        Avoids importing the full protobuf library at runtime.
        Wire format: field 1 (portnum) varint + field 2 (payload) bytes.
        """
        result = bytearray()
        result.append(0x08)
        result.extend(_encode_varint(portnum))
        result.append(0x12)
        result.extend(_encode_varint(len(payload)))
        result.extend(payload)
        return bytes(result)

    @staticmethod
    def _serialize_user(
        node_id_str: str,
        long_name: str,
        short_name: str,
        hw_model: int,
    ) -> bytes:
        """Serialize a mesh_pb2.User protobuf manually.

        Wire format used here: field 1 (id, string), field 2
        (long_name, string), field 3 (short_name, string), and field 5
        (hw_model, varint). The ``macaddr`` field (4) is intentionally
        omitted since the Meshpoint has no canonical radio MAC and
        clients tolerate its absence.
        """
        result = bytearray()
        for tag, text in (
            (0x0A, node_id_str),
            (0x12, long_name),
            (0x1A, short_name),
        ):
            encoded = text.encode("utf-8")
            result.append(tag)
            result.extend(_encode_varint(len(encoded)))
            result.extend(encoded)
        result.append(0x28)
        result.extend(_encode_varint(hw_model))
        return bytes(result)

    @staticmethod
    def _build_header(
        dest: int,
        source_id: int,
        packet_id: int,
        hop_limit: int = 3,
        hop_start: int = 3,
        want_ack: bool = False,
        via_mqtt: bool = False,
        channel_hash: int = 0x08,
    ) -> bytes:
        """Build the 16-byte unencrypted Meshtastic packet header."""
        flags = hop_limit & 0x07
        if want_ack:
            flags |= 0x08
        if via_mqtt:
            flags |= 0x10
        flags |= (hop_start & 0x07) << 5

        header = struct.pack("<III", dest, source_id, packet_id)
        header += bytes([flags, channel_hash, 0x00, 0x00])
        return header


def _encode_varint(value: int) -> bytes:
    """Encode an integer as a protobuf varint."""
    result = bytearray()
    while value > 0x7F:
        result.append((value & 0x7F) | 0x80)
        value >>= 7
    result.append(value & 0x7F)
    return bytes(result)
