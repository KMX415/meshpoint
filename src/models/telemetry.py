from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Telemetry:
    """Device telemetry data extracted from mesh packets."""

    node_id: str
    battery_level: Optional[float] = None
    voltage: Optional[float] = None
    temperature: Optional[float] = None
    humidity: Optional[float] = None
    barometric_pressure: Optional[float] = None
    channel_utilization: Optional[float] = None
    air_util_tx: Optional[float] = None
    uptime_seconds: Optional[int] = None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "battery_level": self.battery_level,
            "voltage": self.voltage,
            "temperature": self.temperature,
            "humidity": self.humidity,
            "barometric_pressure": self.barometric_pressure,
            "channel_utilization": self.channel_utilization,
            "air_util_tx": self.air_util_tx,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp.isoformat(),
        }
