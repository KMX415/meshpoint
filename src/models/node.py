from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from src.models.signal import SignalMetrics
from src.models.telemetry import Telemetry


@dataclass
class Node:
    """A discovered mesh network node."""

    node_id: str
    long_name: Optional[str] = None
    short_name: Optional[str] = None
    hardware_model: Optional[str] = None
    firmware_version: Optional[str] = None
    protocol: str = "meshtastic"

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None

    last_heard: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    packet_count: int = 0

    latest_signal: Optional[SignalMetrics] = None
    latest_telemetry: Optional[Telemetry] = None

    @property
    def has_position(self) -> bool:
        return self.latitude is not None and self.longitude is not None

    @property
    def display_name(self) -> str:
        return self.long_name or self.short_name or f"!{self.node_id}"

    def to_dict(self) -> dict:
        result = {
            "node_id": self.node_id,
            "long_name": self.long_name,
            "short_name": self.short_name,
            "hardware_model": self.hardware_model,
            "firmware_version": self.firmware_version,
            "protocol": self.protocol,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "last_heard": self.last_heard.isoformat(),
            "first_seen": self.first_seen.isoformat(),
            "packet_count": self.packet_count,
            "display_name": self.display_name,
            "has_position": self.has_position,
        }
        if self.latest_signal:
            result["latest_signal"] = self.latest_signal.to_dict()
        if self.latest_telemetry:
            result["latest_telemetry"] = self.latest_telemetry.to_dict()
        return result
