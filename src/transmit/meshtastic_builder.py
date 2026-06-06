"""Meshtastic packet construction for native LoRa transmission.

Builds properly formatted, encrypted Meshtastic packets matching
the firmware's on-air format. Packets are suitable for feeding
directly into lgw_send() via the SX1302 HAL.
"""

from __future__ import annotations

import logging
import struct
from typing import Sequence

from src.decode.crypto_service import CryptoService

logger = logging.getLogger(__name__)

BROADCAST_ADDR = 0xFFFFFFFF
PORTNUM_TEXT_MESSAGE = 1
PORTNUM_POSITION = 3
PORTNUM_NODEINFO = 4
PORTNUM_ROUTING = 5
PORTNUM_TELEMETRY = 67
PORTNUM_TRACEROUTE = 70
HW_MODEL_PRIVATE_HW = 255
MAINS_BATTERY_LEVEL = 101


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
        recipient_public_key: bytes | None = None,
    ) -> bytes | None:
        """Build a complete encrypted TEXT_MESSAGE_APP packet."""
        inner = self._serialize_data(PORTNUM_TEXT_MESSAGE, text.encode("utf-8"))
        ciphertext = self._encrypt_payload(
            inner,
            packet_id,
            source_id,
            dest,
            channel_key,
            channel_hash,
            recipient_public_key,
        )
        if ciphertext is None:
            logger.error("Encryption failed for packet %d", packet_id)
            return None

        on_air_hash = 0 if recipient_public_key else channel_hash
        header = self._build_header(
            dest,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=want_ack,
            channel_hash=on_air_hash,
        )
        return header + ciphertext

    def build_nodeinfo(
        self,
        source_id: int,
        packet_id: int,
        long_name: str,
        short_name: str,
        hw_model: int = HW_MODEL_PRIVATE_HW,
        public_key: bytes | None = None,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
    ) -> bytes | None:
        """Build a broadcast NODEINFO_APP packet announcing this node."""
        node_id_str = f"!{source_id:08x}"
        user_payload = self._serialize_user(
            node_id_str, long_name, short_name, hw_model, public_key
        )
        inner = self._serialize_data(PORTNUM_NODEINFO, user_payload)
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )
        if ciphertext is None:
            logger.error("Encryption failed for nodeinfo packet %d", packet_id)
            return None

        header = self._build_header(
            BROADCAST_ADDR,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=False,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    def build_routing_ack(
        self,
        source_id: int,
        dest: int,
        packet_id: int,
        request_id: int,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
        recipient_public_key: bytes | None = None,
    ) -> bytes | None:
        """Build a ROUTING ACK for an inbound direct message."""
        routing_payload = b""
        inner = self._serialize_data(
            PORTNUM_ROUTING, routing_payload, request_id=request_id
        )
        ciphertext = self._encrypt_payload(
            inner,
            packet_id,
            source_id,
            dest,
            channel_key,
            channel_hash,
            recipient_public_key,
        )
        if ciphertext is None:
            return None
        on_air_hash = 0 if recipient_public_key else channel_hash
        header = self._build_header(
            dest,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            want_ack=False,
            channel_hash=on_air_hash,
        )
        return header + ciphertext

    def build_telemetry(
        self,
        source_id: int,
        packet_id: int,
        *,
        battery_level: int = MAINS_BATTERY_LEVEL,
        voltage: float = 5.0,
        channel_utilization: float = 0.0,
        air_util_tx: float = 0.0,
        uptime_seconds: int = 0,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
    ) -> bytes | None:
        """Build a broadcast TELEMETRY device_metrics packet."""
        try:
            from meshtastic.protobuf import telemetry_pb2

            telem = telemetry_pb2.Telemetry()
            telem.device_metrics.battery_level = battery_level
            telem.device_metrics.voltage = voltage
            telem.device_metrics.channel_utilization = channel_utilization
            telem.device_metrics.air_util_tx = air_util_tx
            telem.device_metrics.uptime_seconds = uptime_seconds
            payload = telem.SerializeToString()
        except Exception:
            logger.exception("Telemetry protobuf build failed")
            return None

        inner = self._serialize_data(PORTNUM_TELEMETRY, payload)
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )
        if ciphertext is None:
            return None
        header = self._build_header(
            BROADCAST_ADDR,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    def build_telemetry_reply(
        self,
        source_id: int,
        dest: int,
        packet_id: int,
        request_id: int,
        *,
        variant: str = "device_metrics",
        battery_level: int = MAINS_BATTERY_LEVEL,
        voltage: float = 5.0,
        channel_utilization: float = 0.0,
        air_util_tx: float = 0.0,
        uptime_seconds: int = 0,
        num_packets_tx: int = 0,
        num_packets_rx: int = 0,
        num_packets_rx_bad: int = 0,
        num_online_nodes: int = 0,
        num_total_nodes: int = 0,
        num_tx_relay: int = 0,
        noise_floor: int | None = None,
        telemetry_time: int = 0,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
        recipient_public_key: bytes | None = None,
    ) -> bytes | None:
        """Build a unicast TELEMETRY reply to a telemetry request."""
        try:
            from meshtastic.protobuf import telemetry_pb2

            telem = telemetry_pb2.Telemetry()
            if telemetry_time:
                telem.time = telemetry_time
            if variant == "local_stats":
                ls = telem.local_stats
                ls.uptime_seconds = uptime_seconds
                ls.channel_utilization = channel_utilization
                ls.air_util_tx = air_util_tx
                ls.num_packets_tx = num_packets_tx
                ls.num_packets_rx = num_packets_rx
                ls.num_packets_rx_bad = num_packets_rx_bad
                ls.num_online_nodes = num_online_nodes
                ls.num_total_nodes = num_total_nodes
                ls.num_tx_relay = num_tx_relay
                if noise_floor is not None:
                    ls.noise_floor = noise_floor
            else:
                telem.device_metrics.battery_level = battery_level
                telem.device_metrics.voltage = voltage
                telem.device_metrics.channel_utilization = channel_utilization
                telem.device_metrics.air_util_tx = air_util_tx
                telem.device_metrics.uptime_seconds = uptime_seconds
            payload = telem.SerializeToString()
        except Exception:
            logger.exception("Telemetry reply protobuf build failed")
            return None

        inner = self._serialize_data(
            PORTNUM_TELEMETRY, payload, request_id=request_id
        )
        ciphertext = self._encrypt_payload(
            inner,
            packet_id,
            source_id,
            dest,
            channel_key,
            channel_hash,
            recipient_public_key,
        )
        if ciphertext is None:
            return None
        on_air_hash = 0 if recipient_public_key else channel_hash
        header = self._build_header(
            dest,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            channel_hash=on_air_hash,
        )
        return header + ciphertext

    def build_position(
        self,
        source_id: int,
        packet_id: int,
        latitude: float,
        longitude: float,
        altitude: float | None = None,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
    ) -> bytes | None:
        """Build a broadcast POSITION packet."""
        try:
            from meshtastic.protobuf import mesh_pb2

            pos = mesh_pb2.Position()
            pos.latitude_i = int(latitude * 1e7)
            pos.longitude_i = int(longitude * 1e7)
            if altitude is not None:
                pos.altitude = int(altitude)
            payload = pos.SerializeToString()
        except Exception:
            logger.exception("Position protobuf build failed")
            return None

        inner = self._serialize_data(PORTNUM_POSITION, payload)
        ciphertext = self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )
        if ciphertext is None:
            return None
        header = self._build_header(
            BROADCAST_ADDR,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            channel_hash=channel_hash,
        )
        return header + ciphertext

    def build_traceroute_reply(
        self,
        source_id: int,
        dest: int,
        packet_id: int,
        route_nodes: Sequence[int],
        *,
        request_id: int = 0,
        snr_towards: Sequence[int] | None = None,
        route_back: Sequence[int] | None = None,
        snr_back: Sequence[int] | None = None,
        channel_key: bytes | None = None,
        channel_hash: int = 0x08,
        hop_limit: int = 3,
        hop_start: int = 3,
        recipient_public_key: bytes | None = None,
    ) -> bytes | None:
        """Build a TRACEROUTE reply with a RouteDiscovery payload."""
        try:
            from meshtastic.protobuf import mesh_pb2

            rd = mesh_pb2.RouteDiscovery()
            for node in route_nodes:
                rd.route.append(node)
            if snr_towards:
                rd.snr_towards.extend(snr_towards)
            if route_back:
                rd.route_back.extend(route_back)
            if snr_back:
                rd.snr_back.extend(snr_back)
            payload = rd.SerializeToString()
        except Exception:
            logger.exception("Traceroute protobuf build failed")
            return None

        inner = self._serialize_data(
            PORTNUM_TRACEROUTE, payload, request_id=request_id
        )
        ciphertext = self._encrypt_payload(
            inner,
            packet_id,
            source_id,
            dest,
            channel_key,
            channel_hash,
            recipient_public_key,
        )
        if ciphertext is None:
            return None
        on_air_hash = 0 if recipient_public_key else channel_hash
        header = self._build_header(
            dest,
            source_id,
            packet_id,
            hop_limit=hop_limit,
            hop_start=hop_start,
            channel_hash=on_air_hash,
        )
        return header + ciphertext

    def _encrypt_payload(
        self,
        inner: bytes,
        packet_id: int,
        source_id: int,
        dest: int,
        channel_key: bytes | None,
        channel_hash: int,
        recipient_public_key: bytes | None,
    ) -> bytes | None:
        if (
            recipient_public_key
            and dest != BROADCAST_ADDR
            and self._crypto.has_pki()
        ):
            return self._crypto.encrypt_meshtastic_pki(
                inner,
                packet_id,
                source_id,
                recipient_public_key,
            )
        return self._crypto.encrypt_meshtastic(
            inner, packet_id, source_id, key=channel_key
        )

    @staticmethod
    def _serialize_data(
        portnum: int, payload: bytes, request_id: int = 0
    ) -> bytes:
        """Serialize a mesh_pb2.Data protobuf manually."""
        result = bytearray()
        result.append(0x08)
        result.extend(_encode_varint(portnum))
        result.append(0x12)
        result.extend(_encode_varint(len(payload)))
        result.extend(payload)
        if request_id:
            result.append(0x35)
            result.extend(struct.pack("<I", request_id & 0xFFFFFFFF))
        return bytes(result)

    @staticmethod
    def _serialize_user(
        node_id_str: str,
        long_name: str,
        short_name: str,
        hw_model: int,
        public_key: bytes | None = None,
    ) -> bytes:
        """Serialize a mesh_pb2.User protobuf manually."""
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
        if public_key:
            result.append(0x42)
            result.extend(_encode_varint(len(public_key)))
            result.extend(public_key)
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
