"""Convert meshtastic-python packet dicts into pipeline RawCapture objects."""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.packet import RawCapture
from src.models.signal import SignalMetrics

try:
    from meshtastic import mesh_pb2 as _mesh_pb2
except ImportError:  # pragma: no cover - meshtastic optional on gateway-only dev
    _mesh_pb2 = None


def packet_dict_to_raw_capture(
    packet: dict,
    capture_source: str,
    default_frequency_mhz: float = 906.875,
) -> Optional[RawCapture]:
    """Map a meshtastic-python receive callback packet to RawCapture."""
    signal = _signal_from_packet(packet, default_frequency_mhz)
    lora_bytes = _coerce_lora_bytes(packet)

    if lora_bytes is not None:
        return RawCapture(
            payload=lora_bytes,
            signal=signal,
            capture_source=capture_source,
            timestamp=datetime.now(timezone.utc),
        )

    if _has_decoded_api_payload(packet):
        return RawCapture(
            payload=b"",
            signal=signal,
            capture_source=capture_source,
            timestamp=datetime.now(timezone.utc),
            meshtastic_api_packet=packet,
        )

    return None


def _signal_from_packet(
    packet: dict, default_frequency_mhz: float
) -> SignalMetrics:
    return SignalMetrics(
        rssi=float(packet.get("rxRssi", packet.get("rssi", -100))),
        snr=float(packet.get("rxSnr", packet.get("snr", 0))),
        frequency_mhz=default_frequency_mhz,
        spreading_factor=11,
        bandwidth_khz=250.0,
    )


def _coerce_lora_bytes(packet: dict) -> Optional[bytes]:
    """Return on-air Meshtastic bytes (16-byte header + encrypted body)."""
    raw_field = packet.get("raw", b"")

    if _is_mesh_packet_proto(raw_field):
        lora = _mesh_packet_to_lora_bytes(raw_field)
        if lora:
            return lora

    if isinstance(raw_field, (bytes, bytearray)) and len(raw_field) >= 16:
        return bytes(raw_field)

    if isinstance(raw_field, str) and raw_field:
        try:
            return bytes.fromhex(raw_field)
        except ValueError:
            return None

    if "decoded" in packet:
        return _reconstruct_raw(packet)

    return None


def _is_mesh_packet_proto(value: Any) -> bool:
    if value is None or isinstance(value, (dict, bytes, bytearray, str)):
        return False
    if _mesh_pb2 is not None and isinstance(value, _mesh_pb2.MeshPacket):
        return True
    if type(value).__module__.startswith("unittest.mock"):
        return False
    return hasattr(value, "WhichOneof") and hasattr(value, "encrypted")


def _mesh_packet_to_lora_bytes(mesh_packet) -> Optional[bytes]:
    """Build the SX1302-style frame from a meshtastic MeshPacket protobuf."""
    variant = mesh_packet.WhichOneof("payload_variant")
    if variant not in ("encrypted", "decoded"):
        return None

    raw_enc = mesh_packet.encrypted
    if not raw_enc or not isinstance(raw_enc, (bytes, bytearray)):
        return None

    body = bytes(raw_enc)

    dest = int(getattr(mesh_packet, "to", 0) or 0xFFFFFFFF)
    source = int(getattr(mesh_packet, "from", 0) or 0)
    pkt_id = int(getattr(mesh_packet, "id", 0) or 0)
    hop_limit = int(getattr(mesh_packet, "hop_limit", 3) or 3)
    hop_start = int(getattr(mesh_packet, "hop_start", hop_limit) or hop_limit)
    want_ack = bool(getattr(mesh_packet, "want_ack", False))
    via_mqtt = bool(getattr(mesh_packet, "via_mqtt", False))
    channel = int(getattr(mesh_packet, "channel", 0) or 0) & 0xFF
    next_hop = int(getattr(mesh_packet, "next_hop", 0) or 0) & 0xFF
    relay_node = int(getattr(mesh_packet, "relay_node", 0) or 0) & 0xFF

    flags = hop_limit & 0x07
    if want_ack:
        flags |= 0x08
    if via_mqtt:
        flags |= 0x10
    flags |= (hop_start & 0x07) << 5

    header = struct.pack("<III", dest, source, pkt_id)
    header += bytes([flags, channel, next_hop, relay_node])
    if not body:
        return None
    return header + body


def _has_decoded_api_payload(packet: dict) -> bool:
    decoded = packet.get("decoded")
    return isinstance(decoded, dict) and bool(decoded.get("portnum"))


def _reconstruct_raw(packet: dict) -> Optional[bytes]:
    """Build a minimal raw frame when only dict fields are available."""
    dest = packet.get("to", 0xFFFFFFFF)
    source = packet.get("from", 0)
    pkt_id = packet.get("id", 0)

    hop_limit = packet.get("hopLimit", 3)
    hop_start = packet.get("hopStart", 3)
    want_ack = packet.get("wantAck", False)
    via_mqtt = packet.get("viaMqtt", False)

    flags = hop_limit & 0x07
    if want_ack:
        flags |= 0x08
    if via_mqtt:
        flags |= 0x10
    flags |= (hop_start & 0x07) << 5

    channel = packet.get("channel", 0) & 0xFF
    next_hop = packet.get("nextHop", packet.get("next_hop", 0)) & 0xFF
    relay_node = packet.get("relayNode", packet.get("relay_node", 0)) & 0xFF

    header = struct.pack("<III", dest, source, pkt_id)
    header += bytes([flags, channel, next_hop, relay_node])

    encoded = packet.get("encoded", b"")
    if isinstance(encoded, str):
        try:
            encoded = bytes.fromhex(encoded)
        except ValueError:
            encoded = b""

    decoded = packet.get("decoded") or {}
    payload = decoded.get("payload", encoded)
    if isinstance(payload, str):
        try:
            payload = bytes.fromhex(payload)
        except ValueError:
            payload = b""

    if not payload:
        return None

    return header + bytes(payload)
