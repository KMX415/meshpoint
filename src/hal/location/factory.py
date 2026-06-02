"""Factory: pick the right ``LocationSource`` based on configuration.

Single entry point for the coordinator. Returns a fully-constructed
source matching ``LocationConfig.source``; falls back to ``StaticSource``
for unknown values so a typo in ``local.yaml`` doesn't crash boot.
"""

from __future__ import annotations

import logging

from src.config import DeviceConfig, LocationConfig
from src.hal.location.base import LocationSource
from src.hal.location.gpsd_source import GpsdSource
from src.hal.location.static_source import StaticSource
from src.hal.location.uart_source import UartSource

logger = logging.getLogger(__name__)


def build_location_source(
    location_config: LocationConfig,
    device_config: DeviceConfig,
) -> LocationSource:
    """Instantiate the configured ``LocationSource``.

    Unknown ``source`` values fall back to ``StaticSource`` with a
    warning, so a malformed ``local.yaml`` degrades to "use the
    coordinates I typed in once" rather than crashing the boot path.
    """
    source = (location_config.source or "static").lower()

    if source == "static":
        return StaticSource(device_config)
    if source == "gpsd":
        return GpsdSource(
            host=location_config.gpsd_host,
            port=location_config.gpsd_port,
            min_fix_quality=location_config.min_fix_quality,
        )
    if source == "uart":
        return UartSource()

    logger.warning(
        "Unknown location.source=%r in config -- falling back to static",
        location_config.source,
    )
    return StaticSource(device_config)
