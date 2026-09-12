"""Encode / decode Sideband-compatible LXMF telemetry frames.

Sideband -- and any LXMF client that reads ``FIELD_TELEMETRY`` (0x02) --
expects a msgpacked ``dict`` of ``{ sensor_id: packed_value }``.
:func:`build_telemetry` builds that dict from ``backend/host_stats.py``'s
readings (the caller msgpacks it and hangs it off an outbound
``LXMessage.fields``); :func:`decode_telemetry` turns a received,
already-msgunpacked frame back into a friendly flat dict for the
telemetry collector (``backend/telemetry_store.py``).

Deliberately a **small, safe subset** of Sideband's sensor set -- only
the sensors whose ``pack()`` format is a single unambiguous scalar/string
(verified against Sideband's ``sbapp/sideband/sense.py``):

    SID_TIME        0x01  int    unix seconds (always sent)
    SID_TEMPERATURE 0x07  float  celsius -- the CPU/SoC temperature
    SID_INFORMATION 0x0F  str    a one-line human-readable status

    SID_LOCATION    0x02  [7-element struct-packed list] -- only when the
                          operator opts in (Configuration -> GPS pin)

Sideband's structured PROCESSOR / RAM / NVM sensors pack as a nested
``[[label, value], ...]`` list whose exact shape we haven't verified
against a real client, so for now that content goes into the INFORMATION
string instead.

FastAPI-free, stdlib only.
"""

from __future__ import annotations

import struct
import time

# Sideband sensor IDs (sbapp/sideband/sense.py :: Sensor.SID_*)
SID_TIME = 0x01
SID_LOCATION = 0x02
SID_TEMPERATURE = 0x07
SID_INFORMATION = 0x0F


def _info_line(host: dict, node_name: str, space_open: bool | None = None) -> str:
    """A compact, human-readable status string for the INFORMATION sensor
    -- what shows on a subscriber's telemetry screen as free text.
    Temperature is deliberately left out: it's its own ``SID_TEMPERATURE``
    sensor, so repeating it here just double-prints it. ``space_open`` is
    the hosted node's SpaceAPI status (nomad_node.py's ``spaceapi_snapshot``)
    -- ``None`` (no SpaceAPI URL configured, or nothing fetched yet) omits
    it rather than printing a meaningless "unknown" on every frame."""
    parts: list[str] = []
    if node_name:
        parts.append(node_name)
    load = host.get("load_1m")
    if load is not None:
        parts.append(f"load {load}")
    used, total = host.get("mem_used_mb"), host.get("mem_total_mb")
    if used is not None and total:
        parts.append(f"RAM {round(100 * used / total)}%")
    free_gb = host.get("disk_free_gb")
    if free_gb is not None:
        parts.append(f"disk {free_gb} GB free")
    if space_open is not None:
        parts.append(f"space {'OPEN' if space_open else 'CLOSED'}")
    return " · ".join(parts) or "meshpoint"


def _pack_location(lat: float, lon: float, alt: float = 0.0) -> list:
    """Sideband's ``Location.pack()`` layout (sense.py) for a fixed pin --
    speed / bearing / accuracy are all 0. Coordinates are big-endian ints
    scaled by 1e6 (deg) / 1e2 (m)."""
    return [
        struct.pack("!i", int(round(lat, 6) * 1e6)),
        struct.pack("!i", int(round(lon, 6) * 1e6)),
        struct.pack("!i", int(round(alt, 2) * 1e2)),
        struct.pack("!I", 0),                       # speed
        struct.pack("!i", 0),                       # bearing
        struct.pack("!H", 0),                       # accuracy
        int(time.time()),                           # last_update
    ]


def build_telemetry(
    host: dict, node_name: str = "",
    location: tuple[float, float, float] | None = None,
    space_open: bool | None = None,
) -> dict[int, object]:
    """The ``{ sensor_id: packed_value }`` dict for one telemetry frame.
    The caller msgpacks it. ``host`` is ``host_stats.read_host()``'s
    output (any field may be ``None``). ``location`` is
    ``(lat, lon, alt)`` -- included as ``SID_LOCATION`` only when both
    lat and lon are real numbers. ``space_open`` folds the hosted node's
    SpaceAPI open/closed status into the INFORMATION line when known --
    see ``_info_line``."""
    frame: dict[int, object] = {SID_TIME: int(time.time())}
    if location and isinstance(location[0], (int, float)) and isinstance(location[1], (int, float)):
        alt = location[2] if len(location) > 2 and isinstance(location[2], (int, float)) else 0.0
        frame[SID_LOCATION] = _pack_location(location[0], location[1], alt)
    temp = host.get("cpu_temp_c")
    if isinstance(temp, (int, float)):
        frame[SID_TEMPERATURE] = float(temp)
    frame[SID_INFORMATION] = _info_line(host, node_name, space_open)
    return frame


def _unpack_location(packed: list) -> dict | None:
    """Inverse of :func:`_pack_location` -- Sideband's ``Location`` list
    back to ``{latitude, longitude, altitude, updated}``. Tolerant of a
    short list / bad members (returns ``None`` rather than raising)."""
    try:
        if not isinstance(packed, (list, tuple)) or len(packed) < 3:
            return None

        def _i(b, fmt="!i"):
            return struct.unpack(fmt, b)[0] if isinstance(b, (bytes, bytearray)) else None

        lat, lon, alt = _i(packed[0]), _i(packed[1]), _i(packed[2])
        if lat is None or lon is None:
            return None
        updated = packed[6] if len(packed) > 6 and isinstance(packed[6], (int, float)) else None
        return {
            "latitude": round(lat / 1e6, 6),
            "longitude": round(lon / 1e6, 6),
            "altitude": round(alt / 1e2, 2) if alt is not None else None,
            "updated": int(updated) if updated else None,
        }
    except Exception:  # noqa: BLE001
        return None


def decode_telemetry(frame: dict) -> dict:
    """A msgunpacked ``{sensor_id: value}`` frame -> a friendly flat dict
    ``{time, temperature_c, info, latitude, longitude, altitude}`` (keys
    absent when the sensor wasn't in the frame). Unknown sensor ids are
    ignored. Never raises."""
    out: dict = {}
    if not isinstance(frame, dict):
        return out
    t = frame.get(SID_TIME)
    if isinstance(t, (int, float)):
        out["time"] = int(t)
    temp = frame.get(SID_TEMPERATURE)
    if isinstance(temp, (int, float)):
        out["temperature_c"] = round(float(temp), 1)
    info = frame.get(SID_INFORMATION)
    if isinstance(info, (str, bytes)):
        out["info"] = info.decode("utf-8", "replace") if isinstance(info, bytes) else info
    loc = _unpack_location(frame.get(SID_LOCATION)) if SID_LOCATION in frame else None
    if loc:
        out["latitude"] = loc["latitude"]
        out["longitude"] = loc["longitude"]
        if loc["altitude"] is not None:
            out["altitude"] = loc["altitude"]
    return out
