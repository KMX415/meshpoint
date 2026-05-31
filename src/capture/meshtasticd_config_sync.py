"""Push Meshpoint radio settings into a local meshtasticd instance."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

# Meshpoint region keys -> meshtastic protobuf RegionCode names
_MESHPOINT_TO_MT_REGION: dict[str, str] = {
    "US": "US",
    "EU_868": "EU_868",
    "ANZ": "ANZ",
    "IN": "IN",
    "KR": "KR",
    "SG_923": "SG_923",
}


@dataclass(frozen=True)
class MeshtasticdSyncSettings:
    """Radio identity Meshpoint expects meshtasticd to use."""

    region: str
    primary_channel_name: str
    modem_preset: str = "LONG_FAST"


def sync_meshtasticd_config(iface: Any, settings: MeshtasticdSyncSettings) -> None:
    """Align meshtasticd LoRa region + primary channel name with Meshpoint config."""
    node = getattr(iface, "localNode", None)
    if node is None:
        logger.warning("meshtasticd config sync skipped: no localNode on interface")
        return

    _sync_lora_region(node, settings.region)
    _sync_modem_preset(node, settings.modem_preset)
    _sync_primary_channel_name(node, settings.primary_channel_name)


def _sync_lora_region(node: Any, meshpoint_region: str) -> None:
    mt_region_name = _MESHPOINT_TO_MT_REGION.get(meshpoint_region.upper())
    if mt_region_name is None:
        logger.warning(
            "meshtasticd config sync: unknown Meshpoint region %r, skipping",
            meshpoint_region,
        )
        return

    try:
        from meshtastic.protobuf import config_pb2

        target = config_pb2.Config.LoRaConfig.RegionCode.Value(mt_region_name)
    except (ImportError, ValueError) as exc:
        logger.warning("meshtasticd config sync: region map failed: %s", exc)
        return

    current = node.localConfig.lora.region
    if current == target:
        logger.debug("meshtasticd lora.region already %s", mt_region_name)
        return

    previous_name = config_pb2.Config.LoRaConfig.RegionCode.Name(current)
    node.localConfig.lora.region = target
    node.writeConfig("lora")
    logger.info(
        "meshtasticd lora.region updated %s -> %s",
        previous_name,
        mt_region_name,
    )


def _sync_modem_preset(node: Any, preset_name: str) -> None:
    try:
        from meshtastic.protobuf import config_pb2

        target = config_pb2.Config.LoRaConfig.ModemPreset.Value(
            preset_name.upper()
        )
    except (ImportError, ValueError) as exc:
        logger.debug("meshtasticd modem preset sync skipped: %s", exc)
        return

    current = node.localConfig.lora.modem_preset
    if current == target:
        return

    node.localConfig.lora.modem_preset = target
    node.writeConfig("lora")
    logger.info(
        "meshtasticd modem preset updated to %s",
        preset_name.upper(),
    )


def _sync_primary_channel_name(node: Any, channel_name: str) -> None:
    name = (channel_name or "").strip()
    if not name:
        return

    channels = getattr(node, "channels", None)
    if not channels:
        logger.debug("meshtasticd channel sync: channels not loaded yet")
        return

    primary = node.getChannelByChannelIndex(0)
    if primary is None or not getattr(primary, "settings", None):
        logger.debug("meshtasticd channel sync: primary channel missing")
        return

    if primary.settings.name == name:
        return

    primary.settings.name = name
    node.writeChannel(0)
    logger.info("meshtasticd primary channel name set to %r", name)


def read_local_node_id_hex(iface: Any) -> str | None:
    """Return the 8-char lowercase hex node id from a meshtastic-python interface."""
    local_node = getattr(iface, "localNode", None)
    if local_node is None:
        return None
    node_num = getattr(local_node, "nodeNum", None)
    if node_num is None:
        user = getattr(local_node, "user", None)
        node_num = getattr(user, "id", None) if user is not None else None
    if node_num is None:
        return None
    try:
        return f"{int(node_num):08x}"
    except (TypeError, ValueError):
        return None


def build_sync_settings_from_config(config: Any) -> MeshtasticdSyncSettings:
    """Build sync settings from AppConfig."""
    meshtastic = getattr(config, "meshtastic", None)
    radio = getattr(config, "radio", None)
    channel_name = "LongFast"
    region = "US"
    if meshtastic is not None:
        channel_name = getattr(meshtastic, "primary_channel_name", channel_name)
    if radio is not None:
        region = getattr(radio, "region", region)
    return MeshtasticdSyncSettings(
        region=region,
        primary_channel_name=channel_name,
    )
