"""Pure dataclasses for location source domain.

These are the contract every ``LocationSource`` produces and every API
consumer reads. Kept dependency-free (no ``gps`` library, no FastAPI,
no ``aiohttp``) so unit tests mock easily and the runtime doesn't pay
for a gpsd handshake when the user is on ``static`` or ``uart``.

Wire shape (when serialized for ``GET /api/device/gps-status``):

    {
      "source": "gpsd",                        # static | gpsd | uart
      "available": true,                       # source ready to read
      "fix": {                                 # null when no fix yet
        "mode": 3, "mode_label": "3D",
        "latitude": 40.7128, "longitude": -74.0060, "altitude_m": 12.3,
        "speed_mps": 0.05, "track_deg": null,
        "time": "2026-05-30T16:37:01Z",
        "epx_m": 1.5, "epy_m": 1.6, "epv_m": 2.4,
        "hdop": 0.9, "pdop": 1.4, "vdop": 1.1
      },
      "satellites": {                          # null on static; empty list on no-sky
        "in_view": 11, "used": 8,
        "list": [
          { "prn": 5, "azimuth": 150.5, "elevation": 65.0,
            "snr_dbhz": 42.0, "used": true, "gnss": "GPS" },
          ...
        ]
      },
      "device": {                              # null on static
        "driver": "u-blox", "path": "/dev/ttyACM0",
        "model": "u-blox 8", "subtype": "PROTVER 18.00"
      },
      "last_update": "2026-05-30T16:37:02Z"    # when source last polled
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


_FIX_MODE_LABELS: dict[int, str] = {
    0: "UNKNOWN",
    1: "NO FIX",
    2: "2D",
    3: "3D",
}


@dataclass(frozen=True)
class Satellite:
    """One satellite seen by the GPS receiver in a single SKY report.

    Field semantics follow gpsd's ``SKY`` schema so the GpsdSource can
    project gpsd JSON onto this shape with no translation table.
    """

    prn: int
    azimuth: Optional[float]      # degrees, 0=N, 90=E, can wrap to 360
    elevation: Optional[float]    # degrees, 0=horizon, 90=zenith
    snr_dbhz: Optional[float]     # dB-Hz, 0..55 typical
    used: bool                    # contributed to the current fix
    gnss: str                     # "GPS" | "GLONASS" | "Galileo" | "BeiDou" | "QZSS" | "SBAS" | "IRNSS" | "UNKNOWN"

    def to_dict(self) -> dict:
        return {
            "prn": self.prn,
            "azimuth": self.azimuth,
            "elevation": self.elevation,
            "snr_dbhz": self.snr_dbhz,
            "used": self.used,
            "gnss": self.gnss,
        }


@dataclass(frozen=True)
class LocationFix:
    """A single position fix.

    ``mode`` follows the gpsd convention: 1=no fix, 2=2D fix, 3=3D fix.
    ``StaticSource`` reports ``mode=3`` because the configured
    coordinates are treated as a known good position.

    All ``ep*`` and ``*dop`` fields are ``None`` when the source can't
    estimate them (static, uart-without-NMEA-GST, etc.).
    """

    mode: int
    latitude: Optional[float]
    longitude: Optional[float]
    altitude_m: Optional[float]
    speed_mps: Optional[float] = None
    track_deg: Optional[float] = None
    time: Optional[datetime] = None
    epx_m: Optional[float] = None
    epy_m: Optional[float] = None
    epv_m: Optional[float] = None
    hdop: Optional[float] = None
    pdop: Optional[float] = None
    vdop: Optional[float] = None

    @property
    def has_position(self) -> bool:
        """True when this fix has lat AND lon (mode 2 or 3)."""
        return (
            self.mode >= 2
            and self.latitude is not None
            and self.longitude is not None
        )

    @property
    def mode_label(self) -> str:
        return _FIX_MODE_LABELS.get(self.mode, "UNKNOWN")

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "mode_label": self.mode_label,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude_m": self.altitude_m,
            "speed_mps": self.speed_mps,
            "track_deg": self.track_deg,
            "time": self.time.isoformat() if self.time else None,
            "epx_m": self.epx_m,
            "epy_m": self.epy_m,
            "epv_m": self.epv_m,
            "hdop": self.hdop,
            "pdop": self.pdop,
            "vdop": self.vdop,
        }


@dataclass(frozen=True)
class GpsDeviceInfo:
    """Identifying metadata for the active GPS receiver.

    ``StaticSource`` has no device, so it returns ``None`` instead of
    constructing this dataclass. ``UartSource`` populates ``path`` and
    ``driver``. ``GpsdSource`` populates everything from the gpsd
    ``DEVICES`` message; ``model`` is best-effort guessed from the
    USB descriptor when present.
    """

    driver: str = "unknown"
    path: str = ""
    model: Optional[str] = None
    subtype: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "driver": self.driver,
            "path": self.path,
            "model": self.model,
            "subtype": self.subtype,
        }


@dataclass(frozen=True)
class SatellitesView:
    """Aggregated satellite report for a single SKY snapshot.

    ``in_view`` counts every satellite the receiver can detect, even
    those with no signal (SNR 0). ``used`` counts only the satellites
    that contributed to the current fix.
    """

    in_view: int
    used: int
    satellites: tuple[Satellite, ...] = field(default_factory=tuple)

    @classmethod
    def from_satellites(cls, sats: list[Satellite]) -> "SatellitesView":
        used = sum(1 for s in sats if s.used)
        return cls(in_view=len(sats), used=used, satellites=tuple(sats))

    def to_dict(self) -> dict:
        return {
            "in_view": self.in_view,
            "used": self.used,
            "list": [s.to_dict() for s in self.satellites],
        }


@dataclass(frozen=True)
class GpsStatus:
    """Full status snapshot returned by ``GET /api/device/gps-status``.

    ``available`` distinguishes "source initialized successfully but no
    fix yet" (e.g. gpsd connected, indoors) from "source not running"
    (e.g. config says gpsd but daemon is offline). The frontend uses
    this to pick the right messaging.
    """

    source: str                   # "static" | "gpsd" | "uart"
    available: bool
    fix: Optional[LocationFix] = None
    satellites: Optional[SatellitesView] = None
    device: Optional[GpsDeviceInfo] = None
    last_update: Optional[datetime] = None
    error: Optional[str] = None   # human-readable when available=False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "available": self.available,
            "fix": self.fix.to_dict() if self.fix else None,
            "satellites": self.satellites.to_dict() if self.satellites else None,
            "device": self.device.to_dict() if self.device else None,
            "last_update": self.last_update.isoformat() if self.last_update else None,
            "error": self.error,
        }


def classify_gnss_id(gnssid: Optional[int]) -> str:
    """Translate gpsd's ``gnssid`` integer into a human label.

    Constellation IDs follow the u-blox / gpsd convention used in
    the SKY message ``gnssid`` field. Unknown IDs fall through to
    ``"UNKNOWN"`` so the skyplot still renders the satellite (it
    just shows in the default constellation shape).
    """
    if gnssid is None:
        return "UNKNOWN"
    return {
        0: "GPS",
        1: "SBAS",
        2: "Galileo",
        3: "BeiDou",
        4: "IMES",
        5: "QZSS",
        6: "GLONASS",
        7: "IRNSS",
    }.get(gnssid, "UNKNOWN")
