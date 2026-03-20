"""Validates `sx1262_spi` capture settings before hardware access."""

from __future__ import annotations

import re
from dataclasses import dataclass

from src.config import Sx1262SpiConfig

_SPIDEV_PATTERN = re.compile(r"^/dev/spidev\d+\.\d+$")
_MAX_BCM = 27


@dataclass
class Sx1262SpiConfigValidator:
    """Validates SPI device path and GPIO BCM numbers for Waveshare SX1262 SPI."""

    def validate_for_enabled_source(self, cfg: Sx1262SpiConfig) -> None:
        """Raise ValueError if any field is invalid or incomplete."""
        self._validate_spi_path(cfg.spi_device)
        self._require_gpio("gpio_cs_bcm", cfg.gpio_cs_bcm)
        self._require_gpio("gpio_reset_bcm", cfg.gpio_reset_bcm)
        self._require_gpio("gpio_busy_bcm", cfg.gpio_busy_bcm)
        self._require_gpio("gpio_dio1_bcm", cfg.gpio_dio1_bcm)
        self._optional_gpio("gpio_txen_bcm", cfg.gpio_txen_bcm)
        if cfg.busy_timeout_seconds <= 0:
            raise ValueError(
                "capture.sx1262_spi.busy_timeout_seconds must be positive"
            )

    @staticmethod
    def _optional_gpio(name: str, value: int | None) -> None:
        if value is None:
            return
        if not isinstance(value, int) or value < 0 or value > _MAX_BCM:
            raise ValueError(
                f"capture.sx1262_spi.{name} must be an integer BCM id 0-{_MAX_BCM} "
                f"(got: {value!r})"
            )

    @staticmethod
    def _validate_spi_path(path: str) -> None:
        if not path or not isinstance(path, str):
            raise ValueError("capture.sx1262_spi.spi_device must be a non-empty string")
        if not _SPIDEV_PATTERN.match(path):
            raise ValueError(
                "capture.sx1262_spi.spi_device must look like /dev/spidev0.1 "
                f"(got: {path!r})"
            )

    @staticmethod
    def _require_gpio(name: str, value: int | None) -> None:
        if value is None:
            raise ValueError(
                f"capture.sx1262_spi.{name} is required when "
                "'sx1262_spi' is in capture.sources — set it in config/local.yaml "
                "for your Waveshare HAT wiring."
            )
        if not isinstance(value, int) or value < 0 or value > _MAX_BCM:
            raise ValueError(
                f"capture.sx1262_spi.{name} must be an integer BCM id 0–{_MAX_BCM} "
                f"(got: {value!r})"
            )
