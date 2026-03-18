"""Channel plan configuration for the SX1302 concentrator.

This is a stub module. The compiled core module (.so) shipped alongside
this file overrides it at runtime. If you see an error from this file,
the .so binary may be missing -- reinstall from the meshpoint release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

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

    @staticmethod
    def meshtastic_us915_default() -> ConcentratorChannelPlan:
        raise RuntimeError(_CORE_MISSING)

    def apply_meshcore_service_channel(
        self,
        frequency_mhz: float,
        spreading_factor: int,
        bandwidth_khz: float,
    ) -> None:
        """Configure the service channel for MeshCore reception.

        When dual-protocol mode is enabled, the single-SF service channel
        is dedicated to MeshCore with its own sync word (set at the HAL
        level). This method configures the service channel's frequency,
        spreading factor, and bandwidth from MeshcoreRadioConfig.
        """
        self.single_sf_channel = ChannelConfig(
            frequency_hz=int(frequency_mhz * 1_000_000),
            bandwidth_khz=int(bandwidth_khz),
            spreading_factor=spreading_factor,
            enabled=True,
        )

    def to_hal_config(self) -> dict:
        raise RuntimeError(_CORE_MISSING)


def build_channel_plan(
    radio_config,
    meshcore_radio_config: Optional[object] = None,
) -> ConcentratorChannelPlan:
    """Build a channel plan from AppConfig radio sections.

    Starts with the Meshtastic US915 defaults for the 8 multi-SF channels.
    If meshcore_radio_config is provided and enabled, dedicates the service
    channel to MeshCore reception.
    """
    plan = ConcentratorChannelPlan.meshtastic_us915_default()

    if meshcore_radio_config and getattr(meshcore_radio_config, "enabled", False):
        plan.apply_meshcore_service_channel(
            frequency_mhz=meshcore_radio_config.frequency_mhz,
            spreading_factor=meshcore_radio_config.spreading_factor,
            bandwidth_khz=meshcore_radio_config.bandwidth_khz,
        )

    return plan
