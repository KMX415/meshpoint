"""Coordinate precision helpers for privacy-controlled publishing."""

from __future__ import annotations

from typing import Optional

VALID_LOCATION_PRECISION = frozenset({"exact", "approximate", "none"})


class LocationPrivacy:
    """Reduce or suppress coordinate precision before RF or MQTT publish."""

    @staticmethod
    def apply(
        lat: Optional[float],
        lon: Optional[float],
        precision: str,
    ) -> tuple[Optional[float], Optional[float]]:
        if lat is None or lon is None:
            return lat, lon
        if precision == "none":
            return None, None
        if precision == "approximate":
            return round(lat, 2), round(lon, 2)
        return lat, lon
