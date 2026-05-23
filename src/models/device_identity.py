from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Optional

from src.version import __version__

logger = logging.getLogger(__name__)


def _stable_device_id(configured_id: Optional[str] = None) -> str:
    """Use a persisted device_id from config, or generate a new one."""
    if configured_id:
        return configured_id
    new_id = str(uuid.uuid4())
    logger.warning(
        "No device_id in config -- generated ephemeral ID %s. "
        "Run 'meshpoint setup' to create a stable identity.",
        new_id,
    )
    return new_id


@dataclass
class DeviceIdentity:
    """This edge device's identity for upstream registration.

    Naming surfaces (kept distinct because they mean different things):
    * ``device_name``   -- internal label for the edge device itself.
                           Rarely customized; defaults to "Meshpoint".
    * ``long_name``     -- the name broadcast over RF in NodeInfo and
                           shown on meshradar / meshmap / neighbour
                           dashboards. This is the user-facing "what
                           shows up on the map" name.
    * ``short_name``    -- the 4-character call sign broadcast on the
                           same NodeInfo and shown in the topbar lamp.

    The dashboard prefers ``long_name`` for the sidebar label so the
    name visible to the operator matches what other devices and
    meshradar see.
    """

    device_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_name: str = "Meshpoint"
    long_name: str = "Meshpoint"
    short_name: str = "MPNT"
    auth_token: Optional[str] = None

    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None

    hardware_description: str = "RAK2287 + Raspberry Pi 4"
    firmware_version: str = __version__

    def to_dict(self) -> dict:
        return {
            "device_id": self.device_id,
            "device_name": self.device_name,
            "long_name": self.long_name,
            "short_name": self.short_name,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "hardware_description": self.hardware_description,
            "firmware_version": self.firmware_version,
        }
