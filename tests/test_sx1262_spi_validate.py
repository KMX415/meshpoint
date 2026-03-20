"""Tests for SX1262 SPI capture config validation."""

from __future__ import annotations

import pytest

from src.capture.sx1262_spi_validate import Sx1262SpiConfigValidator
from src.config import Sx1262SpiConfig


def test_valid_config_passes() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=18,
        gpio_busy_bcm=20,
        gpio_dio1_bcm=16,
        gpio_txen_bcm=6,
        busy_timeout_seconds=5.0,
    )
    Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_valid_config_without_txen_passes() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=18,
        gpio_busy_bcm=20,
        gpio_dio1_bcm=16,
        gpio_txen_bcm=None,
        busy_timeout_seconds=5.0,
    )
    Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


@pytest.mark.parametrize(
    "path",
    ["/dev/foo", "../dev/spidev0.0", "", "/dev/spidev", "spidev0.0"],
)
def test_invalid_spi_path_rejected(path: str) -> None:
    cfg = Sx1262SpiConfig(
        spi_device=path,
        gpio_cs_bcm=21,
        gpio_reset_bcm=1,
        gpio_busy_bcm=2,
        gpio_dio1_bcm=3,
    )
    with pytest.raises(ValueError):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_missing_cs_rejected() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=None,
        gpio_reset_bcm=18,
        gpio_busy_bcm=20,
        gpio_dio1_bcm=16,
    )
    with pytest.raises(ValueError, match="gpio_cs_bcm"):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_missing_busy_rejected() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=5,
        gpio_busy_bcm=None,
        gpio_dio1_bcm=6,
    )
    with pytest.raises(ValueError, match="gpio_busy_bcm"):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_bcm_out_of_range_rejected() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=28,
        gpio_busy_bcm=2,
        gpio_dio1_bcm=3,
    )
    with pytest.raises(ValueError):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_txen_out_of_range_rejected() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=18,
        gpio_busy_bcm=20,
        gpio_dio1_bcm=16,
        gpio_txen_bcm=30,
    )
    with pytest.raises(ValueError, match="gpio_txen_bcm"):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)


def test_non_positive_busy_timeout_rejected() -> None:
    cfg = Sx1262SpiConfig(
        spi_device="/dev/spidev0.0",
        gpio_cs_bcm=21,
        gpio_reset_bcm=1,
        gpio_busy_bcm=2,
        gpio_dio1_bcm=3,
        busy_timeout_seconds=0,
    )
    with pytest.raises(ValueError, match="busy_timeout"):
        Sx1262SpiConfigValidator().validate_for_enabled_source(cfg)
