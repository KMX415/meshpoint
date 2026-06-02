"""Read/write meshtasticd radio state via meshtastic-python localNode."""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

logger = logging.getLogger(__name__)

_MESHPOINT_TO_MT_REGION: dict[str, str] = {
    "US": "US",
    "EU_868": "EU_868",
    "ANZ": "ANZ",
    "IN": "IN",
    "KR": "KR",
    "SG_923": "SG_923",
}

_MT_REGION_TO_MESHPOINT: dict[str, str] = {v: k for k, v in _MESHPOINT_TO_MT_REGION.items()}

DEFAULT_HW_MODEL = 37  # PORTDUINO


@dataclass
class MeshtasticdRadioState:
    """Snapshot of meshtasticd owner + LoRa preferences."""

    bridge_connected: bool = False
    local_node_id_hex: str = ""
    long_name: str = ""
    short_name: str = ""
    hw_model: int = DEFAULT_HW_MODEL
    region: str = ""
    modem_preset: str = ""
    tx_power_dbm: int = 0
    tx_enabled: bool = True
    firmware_version: str = ""
    primary_channel_name: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeshtasticdWriteLoraRequest:
    region: str | None = None
    modem_preset: str | None = None
    tx_power_dbm: int | None = None
    tx_enabled: bool | None = None
    primary_channel_name: str | None = None


@dataclass(frozen=True)
class MeshtasticdWriteOwnerRequest:
    long_name: str
    short_name: str
    hw_model: int = DEFAULT_HW_MODEL


def read_radio_state_from_iface(iface: Any) -> MeshtasticdRadioState:
    """Build a radio snapshot from a connected meshtastic-python interface."""
    state = MeshtasticdRadioState(bridge_connected=iface is not None)
    if iface is None:
        return state

    from src.capture.meshtasticd_config_sync import read_local_node_id_hex

    node_id = read_local_node_id_hex(iface)
    if node_id:
        state.local_node_id_hex = node_id

    local_node = getattr(iface, "localNode", None)
    if local_node is None:
        return state

    user = getattr(local_node, "user", None)
    if user is not None:
        state.long_name = getattr(user, "longName", "") or ""
        state.short_name = getattr(user, "shortName", "") or ""
        try:
            state.hw_model = int(getattr(user, "hwModel", DEFAULT_HW_MODEL))
        except (TypeError, ValueError):
            state.hw_model = DEFAULT_HW_MODEL

    lora = getattr(getattr(local_node, "localConfig", None), "lora", None)
    if lora is not None:
        state.tx_power_dbm = int(getattr(lora, "tx_power", 0) or getattr(lora, "txPower", 0) or 0)
        tx_enabled = getattr(lora, "tx_enabled", None)
        if tx_enabled is None:
            tx_enabled = getattr(lora, "txEnabled", True)
        state.tx_enabled = bool(tx_enabled)
        state.region = _region_name_from_lora(lora)
        state.modem_preset = _modem_preset_name_from_lora(lora)

    metadata = getattr(iface, "metadata", None)
    if metadata is not None:
        state.firmware_version = getattr(metadata, "firmwareVersion", "") or ""

    primary = local_node.getChannelByChannelIndex(0) if hasattr(local_node, "getChannelByChannelIndex") else None
    if primary is not None and getattr(primary, "settings", None) is not None:
        state.primary_channel_name = getattr(primary.settings, "name", "") or ""

    return state


def _region_name_from_lora(lora: Any) -> str:
    try:
        from meshtastic.protobuf import config_pb2

        code = getattr(lora, "region", None)
        if code is None:
            return ""
        name = config_pb2.Config.LoRaConfig.RegionCode.Name(int(code))
        return _MT_REGION_TO_MESHPOINT.get(name, name)
    except Exception:
        return ""


def _modem_preset_name_from_lora(lora: Any) -> str:
    try:
        from meshtastic.protobuf import config_pb2

        code = getattr(lora, "modem_preset", None)
        if code is None:
            return ""
        return config_pb2.Config.LoRaConfig.ModemPreset.Name(int(code))
    except Exception:
        return ""


def apply_write_lora(node: Any, request: MeshtasticdWriteLoraRequest) -> list[str]:
    """Apply LoRa/channel writes; returns human-readable change log lines."""
    from src.capture.meshtasticd_config_sync import (
        MeshtasticdSyncSettings,
        _sync_lora_region,
        _sync_modem_preset,
        _sync_primary_channel_name,
    )

    changes: list[str] = []
    if request.region is not None:
        _sync_lora_region(node, request.region)
        changes.append(f"region={request.region}")
    if request.modem_preset is not None:
        _sync_modem_preset(node, request.modem_preset)
        changes.append(f"preset={request.modem_preset.upper()}")
    if request.primary_channel_name is not None:
        _sync_primary_channel_name(node, request.primary_channel_name)
        changes.append(f"channel={request.primary_channel_name!r}")

    lora = getattr(getattr(node, "localConfig", None), "lora", None)
    if lora is None:
        return changes

    lora_dirty = False
    if request.tx_power_dbm is not None:
        if not 0 <= request.tx_power_dbm <= 30:
            raise ValueError("TX power must be 0-30 dBm")
        if hasattr(lora, "tx_power"):
            lora.tx_power = request.tx_power_dbm
        if hasattr(lora, "txPower"):
            lora.txPower = request.tx_power_dbm
        lora_dirty = True
        changes.append(f"tx_power={request.tx_power_dbm}")

    if request.tx_enabled is not None:
        if hasattr(lora, "tx_enabled"):
            lora.tx_enabled = request.tx_enabled
        if hasattr(lora, "txEnabled"):
            lora.txEnabled = request.tx_enabled
        lora_dirty = True
        changes.append(f"tx_enabled={request.tx_enabled}")

    if lora_dirty:
        node.writeConfig("lora")
        logger.info("meshtasticd lora config written: %s", ", ".join(changes))

    return changes


def apply_write_owner(node: Any, request: MeshtasticdWriteOwnerRequest) -> None:
    """Update owner identity via setOwner."""
    node.setOwner(
        long_name=request.long_name,
        short_name=request.short_name,
    )
    logger.info(
        "meshtasticd setOwner: long=%r short=%r",
        request.long_name,
        request.short_name,
    )


def parse_write_lora_payload(payload: dict[str, Any]) -> MeshtasticdWriteLoraRequest:
    return MeshtasticdWriteLoraRequest(
        region=payload.get("region"),
        modem_preset=payload.get("modem_preset"),
        tx_power_dbm=payload.get("tx_power_dbm"),
        tx_enabled=payload.get("tx_enabled"),
        primary_channel_name=payload.get("primary_channel_name"),
    )


def parse_write_owner_payload(payload: dict[str, Any]) -> MeshtasticdWriteOwnerRequest:
    return MeshtasticdWriteOwnerRequest(
        long_name=str(payload.get("long_name", "")),
        short_name=str(payload.get("short_name", "")),
        hw_model=int(payload.get("hw_model", DEFAULT_HW_MODEL)),
    )
