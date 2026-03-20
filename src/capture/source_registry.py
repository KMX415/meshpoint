"""Registers capture sources from `AppConfig` onto a `PipelineCoordinator`."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.config import AppConfig
    from src.coordinator import PipelineCoordinator

logger = logging.getLogger(__name__)


class CaptureSourceRegistrationManager:
    """Maps `capture.sources` entries to `CaptureSource` instances."""

    def __init__(self, coordinator: PipelineCoordinator, config: AppConfig):
        self._coordinator = coordinator
        self._config = config

    def register_all(self) -> None:
        for source_name in self._config.capture.sources:
            if source_name == "serial":
                self._add_serial()
            elif source_name == "concentrator":
                self._add_concentrator()
            elif source_name == "sx1262_spi":
                self._add_sx1262_spi()
            else:
                logger.warning("Unknown capture source ignored: %s", source_name)

    def _add_serial(self) -> None:
        try:
            from src.capture.serial_source import SerialCaptureSource

            self._coordinator.capture_coordinator.add_source(
                SerialCaptureSource(
                    port=self._config.capture.serial_port,
                    baud=self._config.capture.serial_baud,
                )
            )
        except ImportError:
            logger.warning(
                "Serial capture unavailable — meshtastic package not installed"
            )

    def _add_concentrator(self) -> None:
        try:
            from src.capture.concentrator_source import ConcentratorCaptureSource

            self._coordinator.capture_coordinator.add_source(
                ConcentratorCaptureSource(
                    spi_path=self._config.capture.concentrator_spi_device,
                    syncword=self._config.radio.sync_word,
                )
            )
        except Exception:
            logger.exception("Concentrator source unavailable")

    def _add_sx1262_spi(self) -> None:
        try:
            from src.capture.sx1262_spi_source import Sx1262SpiCaptureSource
            from src.capture.sx1262_spi_validate import Sx1262SpiConfigValidator

            validator = Sx1262SpiConfigValidator()
            validator.validate_for_enabled_source(self._config.capture.sx1262_spi)
            sx = self._config.capture.sx1262_spi
            self._coordinator.capture_coordinator.add_source(
                Sx1262SpiCaptureSource(
                    spi_device=sx.spi_device,
                    gpio_cs_bcm=sx.gpio_cs_bcm,
                    gpio_reset_bcm=sx.gpio_reset_bcm,
                    gpio_busy_bcm=sx.gpio_busy_bcm,
                    gpio_dio1_bcm=sx.gpio_dio1_bcm,
                    gpio_txen_bcm=sx.gpio_txen_bcm,
                    busy_timeout_seconds=sx.busy_timeout_seconds,
                )
            )
        except Exception:
            logger.exception("SX1262 SPI capture source unavailable")


def register_capture_sources(
    coordinator: PipelineCoordinator, config: AppConfig
) -> None:
    """Add all configured capture sources to the pipeline coordinator."""
    CaptureSourceRegistrationManager(coordinator, config).register_all()
