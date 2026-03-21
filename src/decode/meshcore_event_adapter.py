"""Convert MeshCore USB events into decoded Packet objects.

The meshcore Python library yields high-level events (messages,
advertisements) rather than raw radio frames.  This adapter translates
those events into the standard Packet model so they flow through the
same storage, broadcast, and upstream paths as radio-captured packets.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.models.packet import Packet, PacketType, Protocol
from src.models.signal import SignalMetrics

_EVENT_TYPE_MAP: dict[str, PacketType] = {
    "contact_message": PacketType.TEXT,
    "channel_message": PacketType.TEXT,
    "advertisement": PacketType.NODEINFO,
    "raw_data": PacketType.UNKNOWN,
}


def adapt_event(
    raw_payload: bytes,
    signal: Optional[SignalMetrics] = None,
) -> Optional[Packet]:
    """Deserialize a JSON-encoded meshcore event envelope into a Packet."""
    try:
        envelope = json.loads(raw_payload)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None

    event_type: str = envelope.get("event_type", "")
    payload: dict = envelope.get("payload", {})

    builder = _BUILDERS.get(event_type)
    if builder is None:
        return None

    return builder(payload, signal)


def _build_contact_message(
    payload: dict, signal: Optional[SignalMetrics]
) -> Packet:
    return Packet(
        packet_id=_generate_id(),
        source_id=payload.get("pubkey_prefix", "unknown"),
        destination_id="self",
        protocol=Protocol.MESHCORE,
        packet_type=PacketType.TEXT,
        decoded_payload={"text": payload.get("text", "")},
        signal=signal,
        timestamp=_parse_timestamp(payload.get("timestamp")),
        decrypted=True,
    )


def _build_channel_message(
    payload: dict, signal: Optional[SignalMetrics]
) -> Packet:
    channel_idx = payload.get("channel_idx", 0)
    return Packet(
        packet_id=_generate_id(),
        source_id="channel",
        destination_id=f"channel:{channel_idx}",
        protocol=Protocol.MESHCORE,
        packet_type=PacketType.TEXT,
        decoded_payload={
            "text": payload.get("text", ""),
            "channel": channel_idx,
        },
        channel_hash=channel_idx,
        signal=signal,
        timestamp=_parse_timestamp(payload.get("timestamp")),
        decrypted=True,
    )


def _build_advertisement(
    payload: dict, signal: Optional[SignalMetrics]
) -> Packet:
    pubkey = payload.get("public_key", payload.get("pubkey", "unknown"))
    source_id = pubkey[:12] if len(pubkey) >= 12 else pubkey
    return Packet(
        packet_id=_generate_id(),
        source_id=source_id,
        destination_id="broadcast",
        protocol=Protocol.MESHCORE,
        packet_type=PacketType.NODEINFO,
        decoded_payload={"advertisement": payload},
        signal=signal,
        timestamp=_parse_timestamp(payload.get("timestamp")),
    )


def _build_raw_data(
    payload: dict, signal: Optional[SignalMetrics]
) -> Packet:
    return Packet(
        packet_id=_generate_id(),
        source_id="raw",
        destination_id="unknown",
        protocol=Protocol.MESHCORE,
        packet_type=PacketType.UNKNOWN,
        decoded_payload={"raw_hex": payload.get("payload", "")},
        signal=signal,
        timestamp=_parse_timestamp(payload.get("timestamp")),
    )


_BUILDERS = {
    "contact_message": _build_contact_message,
    "channel_message": _build_channel_message,
    "advertisement": _build_advertisement,
    "raw_data": _build_raw_data,
}


def _generate_id() -> str:
    return uuid.uuid4().hex[:16]


def _parse_timestamp(ts) -> datetime:
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, tz=timezone.utc)
    return datetime.now(timezone.utc)
