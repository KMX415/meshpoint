"""Resolve coordinates for Meshtastic POSITION broadcasts on the mesh."""

from __future__ import annotations

from src.config import AppConfig
from src.hal.location import LocationSource
from src.hal.location.privacy import LocationPrivacy, VALID_LOCATION_PRECISION

VALID_MESH_COORDINATE_SOURCES = frozenset({"static", "live"})


class MeshPositionResolver:
    """Choose mesh POSITION coords from registered pin or live GPS fix."""

    def __init__(self, config: AppConfig, location_source: LocationSource):
        self._config = config
        self._location_source = location_source

    def resolve(self) -> tuple[float, float, float | None] | None:
        pos_cfg = self._config.transmit.position
        mesh_source = (pos_cfg.coordinate_source or "static").lower()

        if mesh_source == "live":
            if not self._live_fix_available():
                return None
            fix = self._location_source.get_status().fix
            assert fix is not None
            lat = fix.latitude
            lon = fix.longitude
            alt = fix.altitude_m
            precision = pos_cfg.location_precision or "approximate"
        else:
            device = self._config.device
            if device.latitude is None or device.longitude is None:
                return None
            lat = device.latitude
            lon = device.longitude
            alt = device.altitude
            precision = "exact"

        if precision not in VALID_LOCATION_PRECISION:
            precision = "approximate"

        lat, lon = LocationPrivacy.apply(lat, lon, precision)
        if lat is None or lon is None:
            return None
        return lat, lon, alt

    def _live_fix_available(self) -> bool:
        if self._location_source.source_name == "static":
            return False
        status = self._location_source.get_status()
        if not status.available or status.fix is None:
            return False
        return status.fix.has_position
