"""Convert meshtastic-python packet dicts into pipeline RawCapture objects."""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from typing import Optional

from src.models.packet import RawCapture
from src.models.signal import SignalMetrics


def packet_dict_to_raw_capture(
    packet: dict,
    capture_source: str,
    default_frequency_mhz: float = 906.875,
) -> Optional[RawCapture]:
    """Map a meshtastic-python receive callback packet to RawCapture."""
    raw_bytes = packet.get("raw", b"")
    if isinstance(raw_bytes, str):
        raw_bytes = bytes.fromhex(raw_bytes)

    if not raw_bytes and "decoded" in packet:
        raw_bytes = _reconstruct_raw(packet)

    if not raw_bytes:
        return None

    signal = SignalMetrics(
        rssi=float(packet.get("rxRssi", packet.get("rssi", -100))),
        snr=float(packet.get("rxSnr", packet.get("snr", 0))),
        frequency_mhz=default_frequency_mhz,
        spreading_factor=11,
        bandwidth_khz=250.0,
    )

    return RawCapture(
        payload=raw_bytes,
        signal=signal,
        capture_source=capture_source,
        timestamp=datetime.now(timezone.utc),
    )


def _reconstruct_raw(packet: dict) -> bytes:
    """Build a minimal raw frame when the library omits raw bytes."""
    dest = packet.get("to", 0xFFFFFFFF)
    source = packet.get("from", 0)
    pkt_id = packet.get("id", 0)

    hop_limit = packet.get("hopLimit", 3)
    hop_start = packet.get("hopStart", 3)
    want_ack = packet.get("wantAck", False)

    flags = hop_limit & 0x07
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
