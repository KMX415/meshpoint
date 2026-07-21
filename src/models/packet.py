from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.models.signal import SignalMetrics


class Protocol(str, Enum):
    MESHTASTIC = "meshtastic"
    MESHCORE = "meshcore"
    UNKNOWN = "unknown"


class PacketType(str, Enum):
    TEXT = "text"
    POSITION = "position"
    TELEMETRY = "telemetry"
    NODEINFO = "nodeinfo"
    ROUTING = "routing"
    ADMIN = "admin"
    TRACEROUTE = "traceroute"
    NEIGHBORINFO = "neighborinfo"
    WAYPOINT = "waypoint"
    RANGE_TEST = "range_test"
    STORE_FORWARD = "store_forward"
    DETECTION_SENSOR = "detection_sensor"
    PAXCOUNTER = "paxcounter"
    MAP_REPORT = "map_report"
    ENCRYPTED = "encrypted"
    UNKNOWN = "unknown"


@dataclass
class RawCapture:
    """A raw LoRa frame as received from the capture source."""

    payload: bytes
    signal: SignalMetrics
    capture_source: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    protocol_hint: Optional[Protocol] = None
    # Set when an upstream library already decrypted (meshtastic-python
    # serial): portnum (int) + inner payload (bytes). Header-only
    # ``payload`` has no ciphertext left to decrypt.
    pre_decoded: Optional[dict] = None


@dataclass
class Packet:
    """A fully decoded mesh packet with metadata."""

    packet_id: str
    source_id: str
    destination_id: str
    protocol: Protocol
    packet_type: PacketType

    hop_limit: int = 0
    hop_start: int = 0
    channel_hash: int = 0
    want_ack: bool = False
    via_mqtt: bool = False
    relay_node: int = 0

    decoded_payload: Optional[dict[str, Any]] = None
    encrypted_payload: Optional[bytes] = None
    # Inner application-payload bytes from the decrypted protobuf (the
    # bytes that follow `portnum` in a Meshtastic Data message). Used
    # by the legacy USB-companion relay path that calls
    # `interface.sendData(payload, portNum=…)`.
    raw_app_payload: Optional[bytes] = None
    # The full original radio frame as captured (16-byte Meshtastic
    # header + encrypted body). Used by the native relay path to
    # re-emit the packet verbatim through the onboard SX1302 with
    # only the hop_limit decremented, preserving the original
    # source_id and packet_id so other nodes' dedup treats it as a
    # legitimate relay rather than a fresh broadcast.
    raw_radio_packet: Optional[bytes] = None
    decrypted: bool = False
    # Index into crypto.get_all_keys() of the key that decrypted this
    # packet. Set even when channel_hash does not match a local name+key
    # hash (remote used a different channel name, same PSK).
    matched_channel_index: Optional[int] = None
    # Stick-local channel name when meshtastic-python decoded with its
    # own table. packet.channel_hash may hold the stick's index, not OTA hash.
    remote_channel_name: Optional[str] = None

    signal: Optional[SignalMetrics] = None
    capture_source: str = "unknown"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def hop_count(self) -> int:
        if self.hop_start > 0:
            return self.hop_start - self.hop_limit
        return 0

    def to_dict(self) -> dict:
        result = {
            "packet_id": self.packet_id,
            "source_id": self.source_id,
            "destination_id": self.destination_id,
            "protocol": self.protocol.value,
            "packet_type": self.packet_type.value,
            "hop_limit": self.hop_limit,
            "hop_start": self.hop_start,
            "hop_count": self.hop_count,
            "channel_hash": self.channel_hash,
            "want_ack": self.want_ack,
            "via_mqtt": self.via_mqtt,
            "relay_node": self.relay_node,
            "decoded_payload": self.decoded_payload,
            "decrypted": self.decrypted,
            "capture_source": self.capture_source,
            "timestamp": self.timestamp.isoformat(),
        }
        if self.signal:
            result["signal"] = self.signal.to_dict()
        return result
