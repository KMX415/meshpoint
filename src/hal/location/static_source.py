"""Static location source: reports the configured device coordinates.

This is the v0.7.4-and-earlier behavior, now wrapped in the
``LocationSource`` contract so the coordinator and dashboard treat
every source identically.

A ``StaticSource`` always reports ``mode=3`` (3D fix) when the
configured coordinates are valid. The ``device.latitude`` /
``device.longitude`` fields are the source of truth: setting one of
them to ``None`` flips the source to ``mode=1`` (no fix) and
``available=False`` so the dashboard prompts the user to enter
coordinates instead of dropping a pin at (0, 0).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.config import DeviceConfig
from src.hal.location.base import LocationSource
from src.hal.location.models import GpsStatus, LocationFix

logger = logging.getLogger(__name__)


class StaticSource(LocationSource):
    """Report ``device.{latitude,longitude,altitude}`` as a fixed position."""

    def __init__(self, device: DeviceConfig) -> None:
        self._device = device
        self._started = False

    @property
    def source_name(self) -> str:
        return "static"

    async def start(self) -> None:
        if self._started:
            return
        self._started = True
        if self._has_valid_coordinates():
            logger.info(
                "Static location source: %.6f, %.6f (alt=%s)",
                self._device.latitude,
                self._device.longitude,
                "?" if self._device.altitude is None else f"{self._device.altitude:.1f}m",
            )
        else:
            logger.info(
                "Static location source: no coordinates configured -- "
                "dashboard will prompt user to set them"
            )

    async def stop(self) -> None:
        self._started = False

    def get_status(self) -> GpsStatus:
        if not self._has_valid_coordinates():
            return GpsStatus(
                source="static",
                available=False,
                error="No coordinates configured",
                last_update=datetime.now(timezone.utc),
            )

        fix = LocationFix(
            mode=3,
            latitude=self._device.latitude,
            longitude=self._device.longitude,
            altitude_m=self._device.altitude,
        )
        return GpsStatus(
            source="static",
            available=True,
            fix=fix,
            satellites=None,
            device=None,
            last_update=datetime.now(timezone.utc),
        )

    def _has_valid_coordinates(self) -> bool:
        return (
            self._device.latitude is not None
            and self._device.longitude is not None
            and -90 <= self._device.latitude <= 90
            and -180 <= self._device.longitude <= 180
        )
