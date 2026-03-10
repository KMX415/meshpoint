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
    """This edge device's identity for upstream registration."""

    device_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    device_name: str = "Mesh Point"
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
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "hardware_description": self.hardware_description,
            "firmware_version": self.firmware_version,
        }
