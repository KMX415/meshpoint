"""Convert meshtastic-python packet dicts into pipeline RawCapture objects."""

from __future__ import annotations

import logging
import struct
from datetime import datetime, timezone
from typing import Any, Optional

from src.models.packet import RawCapture
from src.models.signal import SignalMetrics

logger = logging.getLogger(__name__)

# meshtastic protobuf TransportMechanism: LoRa over-the-air
_TRANSPORT_LORA_NAMES = frozenset(
    {
        "TRANSPORT_LORA",
        "TRANSPORT_LORA_ALT1",
        "TRANSPORT_LORA_ALT2",
        "TRANSPORT_LORA_ALT3",
    }
)

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

    # meshtasticd / meshtastic-python already decrypt locally and populate
    # packet["decoded"]. Never round-trip that through the LoRa byte decoder:
    # rebuilding header + plaintext and AES-decrypting it always yields ENCRYPTED.
    if _has_decoded_api_payload(packet):
        return RawCapture(
            payload=b"",
            signal=signal,
            capture_source=capture_source,
            timestamp=datetime.now(timezone.utc),
            meshtastic_api_packet=packet,
        )

    lora_bytes = _coerce_lora_bytes(packet)
    if lora_bytes is not None:
        return RawCapture(
            payload=lora_bytes,
            signal=signal,
            capture_source=capture_source,
            timestamp=datetime.now(timezone.utc),
        )

    return None


def _signal_from_packet(
    packet: dict, default_frequency_mhz: float
) -> SignalMetrics:
    rssi, snr = _extract_rf_metrics(packet)
    normalized_rssi = _normalize_rssi(rssi)
    normalized_snr = _normalize_snr(snr, rssi=normalized_rssi)
    if normalized_rssi is None and _is_lora_transport(packet):
        logger.debug(
            "meshtasticd OTA packet missing rxRssi from=%s port=%s",
            packet.get("from"),
            (packet.get("decoded") or {}).get("portnum"),
        )
    return SignalMetrics(
        rssi=normalized_rssi,
        snr=normalized_snr,
        frequency_mhz=default_frequency_mhz,
        spreading_factor=11,
        bandwidth_khz=250.0,
    )


def _extract_rf_metrics(packet: dict) -> tuple[Any, Any]:
    """Read RSSI/SNR from meshtastic-python dict and live MeshPacket proto."""
    rssi = packet.get("rxRssi", packet.get("rx_rssi", packet.get("rssi")))
    snr = packet.get("rxSnr", packet.get("rx_snr", packet.get("snr")))

    raw_field = packet.get("raw")
    if _is_mesh_packet_proto(raw_field):
        proto_rssi = getattr(raw_field, "rx_rssi", None)
        proto_snr = getattr(raw_field, "rx_snr", None)
        # Proto3 scalars default to 0; Meshtastic uses 0 as "not measured".
        if rssi is None and proto_rssi not in (None, 0):
            rssi = proto_rssi
        if snr is None and proto_snr not in (None, 0.0):
            snr = proto_snr

    return rssi, snr


def _is_lora_transport(packet: dict) -> bool:
    transport = packet.get("transportMechanism", packet.get("transport_mechanism"))
    if transport is None and _is_mesh_packet_proto(packet.get("raw")):
        raw = packet["raw"]
        transport = getattr(raw, "transport_mechanism", None)
        if transport is not None and hasattr(transport, "name"):
            transport = transport.name
    if isinstance(transport, int):
        # TRANSPORT_LORA == 1 in mesh.proto
        return transport in (1, 2, 3, 4)
    if isinstance(transport, str):
        return transport in _TRANSPORT_LORA_NAMES
    return False


def _normalize_rssi(value: Any) -> Optional[float]:
    """Map meshtastic unset/zero RSSI to unknown (LoRa RSSI is always negative)."""
    if value is None:
        return None
    try:
        rssi = float(value)
    except (TypeError, ValueError):
        return None
    if rssi >= 0.0:
        return None
    return rssi


def _normalize_snr(value: Any, *, rssi: Optional[float]) -> Optional[float]:
    """SNR 0 with no RSSI is meshtastic's unset sentinel on the TCP bridge."""
    if value is None:
        return None
    try:
        snr = float(value)
    except (TypeError, ValueError):
        return None
    if rssi is None and snr == 0.0:
        return None
    return snr


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
    if not isinstance(decoded, dict):
        return False
    if decoded.get("portnum"):
        return True
    return any(
        key in decoded for key in ("text", "user", "position", "telemetry")
    )
