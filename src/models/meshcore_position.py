"""Validate the position pair used by MeshCore adverts and contact rosters."""

import math


def meshcore_position(latitude, longitude) -> tuple[float, float] | None:
    """Return degrees, treating (0, 0) as the companion's unset position."""
    if isinstance(latitude, bool) or isinstance(longitude, bool):
        return None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(lat) or not math.isfinite(lon):
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if lat == 0 and lon == 0:
        return None
    return lat, lon
