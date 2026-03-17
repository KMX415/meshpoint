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

MESHTASTIC_SYNC_WORD = 0x2B
MESHCORE_SYNC_WORD = 0x12


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

    @staticmethod
    def meshtastic_us915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_anz915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshtastic_eu868_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshcore_us915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshcore_anz915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def meshcore_eu868_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    @staticmethod
    def for_config(region: str, protocol: str) -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    def to_hal_config(self) -> dict:
        raise RuntimeError(_CORE_MISSING)
