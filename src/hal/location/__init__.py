"""Location source abstraction: pluggable static / gpsd / uart implementations.

Public API:

    from src.hal.location import (
        # Domain models
        GpsDeviceInfo, GpsStatus, LocationFix, Satellite, SatellitesView,
        classify_gnss_id,
        # Source contract + concrete implementations
        LocationSource, StaticSource, GpsdSource, UartSource,
        # Factory
        build_location_source,
    )

Coordinator owns the lifecycle: ``start()`` after config load, poll
``get_status()`` for live fixes (gpsd/uart). Registered coordinates in
``device.{lat,lon,alt}`` are not overwritten by live GPS.
"""

from src.hal.location.base import LocationSource
from src.hal.location.factory import build_location_source
from src.hal.location.gpsd_source import GpsdSource
from src.hal.location.models import (
    GpsDeviceInfo,
    GpsStatus,
    LocationFix,
    Satellite,
    SatellitesView,
    classify_gnss_id,
)
from src.hal.location.static_source import StaticSource
from src.hal.location.uart_source import UartSource

__all__ = [
    # Domain models
    "GpsDeviceInfo",
    "GpsStatus",
    "LocationFix",
    "Satellite",
    "SatellitesView",
    "classify_gnss_id",
    # Source contract + concrete implementations
    "LocationSource",
    "StaticSource",
    "GpsdSource",
    "UartSource",
    # Factory
    "build_location_source",
]
