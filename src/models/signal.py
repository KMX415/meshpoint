from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class SignalMetrics:
    """RF signal quality measurements from a received packet."""

    rssi: float
    snr: float
    frequency_mhz: float
    spreading_factor: int
    bandwidth_khz: float
    coding_rate: str = "4/8"
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def signal_quality_percent(self) -> float:
        """Rough 0-100 quality estimate from RSSI (-120 worst, -30 best)."""
        clamped = max(-120.0, min(-30.0, self.rssi))
        return round(((clamped + 120.0) / 90.0) * 100.0, 1)

    def to_dict(self) -> dict:
        return {
            "rssi": self.rssi,
            "snr": self.snr,
            "frequency_mhz": self.frequency_mhz,
            "spreading_factor": self.spreading_factor,
            "bandwidth_khz": self.bandwidth_khz,
            "coding_rate": self.coding_rate,
            "signal_quality_percent": self.signal_quality_percent,
            "timestamp": self.timestamp.isoformat(),
        }
