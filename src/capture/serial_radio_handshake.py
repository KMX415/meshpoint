"""Connect-time LoRa / identity readout from a Meshtastic USB stick.

Populates region, channel_num, modem preset (or custom SF/BW/CR), and
primary channel name so serial packets can stamp real signal metadata.

Credit: javastraat/meshpoint ``77cdaa2`` + ``dc3fc0a``.
"""

from __future__ import annotations

import logging
from typing import Optional

from src.radio.presets import get_preset

logger = logging.getLogger(__name__)


class SerialRadioHandshake:
    """Best-effort read of ``localNode`` LoRa config after SerialInterface open."""

    @staticmethod
    def read(interface) -> dict:
        """Region/channel/modem/name from the interface's own config.

        meshtastic-python's StreamInterface already waits for config before
        SerialInterface returns, so localConfig.lora is populated here.
        Any field that fails to read stays None; never raises.
        """
        info: dict = {
            "region": None,
            "channel_num": None,
            "short_name": None,
            "long_name": None,
            "modem_preset": None,
            "use_preset": True,
            "spreading_factor": None,
            "bandwidth_khz": None,
            "coding_rate": None,
            "channel_name": None,
            "frequency_offset": 0.0,
            "override_frequency": 0.0,
            "channel_table": {},
        }
        try:
            from meshtastic.protobuf import config_pb2

            lora = interface.localNode.localConfig.lora
            info["channel_num"] = int(lora.channel_num)
            info["region"] = config_pb2.Config.LoRaConfig.RegionCode.Name(
                lora.region
            )
            info["use_preset"] = bool(lora.use_preset)
            info["frequency_offset"] = float(lora.frequency_offset)
            info["override_frequency"] = float(lora.override_frequency)
            if lora.use_preset:
                preset_name = config_pb2.Config.LoRaConfig.ModemPreset.Name(
                    lora.modem_preset,
                )
                info["modem_preset"] = preset_name
                preset = get_preset(preset_name)
                if preset:
                    info["spreading_factor"] = preset.spreading_factor
                    info["bandwidth_khz"] = preset.bandwidth_khz
                    info["coding_rate"] = preset.coding_rate
            else:
                info["modem_preset"] = "CUSTOM"
                if lora.spread_factor:
                    info["spreading_factor"] = int(lora.spread_factor)
                if lora.bandwidth:
                    info["bandwidth_khz"] = float(lora.bandwidth)
                if lora.coding_rate:
                    info["coding_rate"] = f"4/{int(lora.coding_rate)}"
        except Exception:
            logger.debug(
                "Could not read LoRa config from serial interface",
                exc_info=True,
            )
        try:
            info["short_name"] = interface.getShortName()
            info["long_name"] = interface.getLongName()
        except Exception:
            logger.debug(
                "Could not read node identity from serial interface",
                exc_info=True,
            )
        try:
            info["channel_name"] = SerialRadioHandshake.read_primary_channel_name(
                interface
            )
        except Exception:
            logger.debug(
                "Could not read primary channel name from serial interface",
                exc_info=True,
            )
        return info

    @staticmethod
    def read_primary_channel_name(interface) -> Optional[str]:
        """Primary channel settings.name, or None if no primary channel.

        Empty string means a blank name (firmware falls back to preset
        display string for slot hashing). None means no primary found.
        """
        from meshtastic.protobuf import channel_pb2

        channels = getattr(interface.localNode, "channels", None) or []
        for ch in channels:
            if ch.role == channel_pb2.Channel.Role.PRIMARY:
                return ch.settings.name
        return None
