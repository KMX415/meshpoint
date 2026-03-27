"""Channel plan configuration for the SX1302 concentrator.

This is a stub module. The compiled core module (.so) shipped alongside
this file overrides it at runtime. If you see an error from this file,
the .so binary may be missing -- reinstall from the meshpoint release.
"""

from __future__ import annotations

from dataclasses import dataclass, field

_CORE_MISSING = (
    "meshpoint-core is required for concentrator operation. "
    "See README.md for installation instructions."
)


@dataclass
class ChannelConfig:
    frequency_hz: int = 0
    bandwidth_khz: int = 125
    spreading_factor: int = 0
    enabled: bool = True


@dataclass
class ConcentratorChannelPlan:
    """Full channel configuration for the SX1302 concentrator."""

    multi_sf_channels: list[ChannelConfig] = field(default_factory=list)
    single_sf_channel: ChannelConfig | None = None
    radio_0_freq_hz: int = 0
    radio_1_freq_hz: int = 0

    @classmethod
    def from_radio_config(
        cls,
        region: str,
        frequency_mhz: float,
        spreading_factor: int = 11,
        bandwidth_khz: float = 250.0,
    ) -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def default_frequency_hz(region: str) -> int | None:
        raise RuntimeError(_CORE_MISSING)

    @classmethod
    def for_region(cls, region: str) -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_us915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_eu868_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_anz_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_in865_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_kr920_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_sg923_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    def to_hal_config(self) -> dict:
        raise RuntimeError(_CORE_MISSING)
