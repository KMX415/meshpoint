"""Prepare a separate, privacy-filtered packet for all MQTT output formats."""
from copy import deepcopy
from dataclasses import replace
import math

from src.models.packet import Packet, Protocol

_LOCATION_FIELDS = {
    "latitude", "longitude", "latitude_i", "longitude_i", "altitude",
    "altitude_hae", "altitude_geoidal_separation", "precision_bits",
    "ground_speed", "ground_track",
}


def is_broadcast(packet: Packet) -> bool:
    destination = packet.destination_id
    if not isinstance(destination, str):
        return False
    destination = destination.lower()
    if packet.protocol == Protocol.MESHTASTIC:
        return destination == "ffffffff"
    if packet.protocol == Protocol.MESHCORE:
        return destination in {"ffff", "broadcast"}
    return False


def prepare_packet(packet: Packet, precision: str) -> Packet:
    # Invalid policies fail closed. Never edit the shared storage/UI packet.
    policy = precision if precision in {"exact", "approximate", "none"} else "none"

    def filtered(value):
        if isinstance(value, list):
            return [filtered(item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: filtered(item) for key, item in value.items()}
        if policy == "none":
            return {key: item for key, item in result.items() if key not in _LOCATION_FIELDS}
        lat, lon = result.get("latitude"), result.get("longitude")
        valid = (type(lat) in (int, float) and type(lon) in (int, float)
                 and math.isfinite(lat) and math.isfinite(lon)
                 and -90 <= lat <= 90 and -180 <= lon <= 180)
        if not valid:
            return {key: item for key, item in result.items() if key not in _LOCATION_FIELDS}
        if policy == "approximate":
            result = {key: item for key, item in result.items() if key not in _LOCATION_FIELDS}
            result.update(latitude=round(lat, 2), longitude=round(lon, 2))
        return result

    return replace(packet, decoded_payload=filtered(deepcopy(packet.decoded_payload)),
                   encrypted_payload=None, raw_app_payload=None, raw_radio_packet=None)
