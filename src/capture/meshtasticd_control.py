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
    frequency_mhz: float = 0.0
    spreading_factor: int = 0
    bandwidth_khz: float = 0.0
    nodeinfo_interval_seconds: int = 0
    telemetry_interval_seconds: int = 0
    telemetry_enabled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MeshtasticdWriteLoraRequest:
    region: str | None = None
    modem_preset: str | None = None
    tx_power_dbm: int | None = None
    tx_enabled: bool | None = None
    primary_channel_name: str | None = None
    nodeinfo_interval_seconds: int | None = None
    telemetry_interval_seconds: int | None = None
    telemetry_enabled: bool | None = None


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
    if user is None:
        nodes = getattr(iface, "nodesByNum", None) or {}
        user = nodes.get(getattr(local_node, "nodeNum", None), {}).get("user")
    if isinstance(user, dict):
        state.long_name = user.get("longName", "")
        state.short_name = user.get("shortName", "")
        model = user.get("hwModel", DEFAULT_HW_MODEL)
        if isinstance(model, int):
            state.hw_model = model
        user = None
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
        state.firmware_version = (getattr(metadata, "firmware_version", "")
                                  or getattr(metadata, "firmwareVersion", "") or "")

    primary = local_node.getChannelByChannelIndex(0) if hasattr(local_node, "getChannelByChannelIndex") else None
    if primary is not None and getattr(primary, "settings", None) is not None:
        state.primary_channel_name = getattr(primary.settings, "name", "") or ""

    if lora is not None:
        from src.radio.channel_frequency import resolve_frequency_mhz
        from src.radio.presets import MODEM_PRESETS

        preset = MODEM_PRESETS.get(state.modem_preset)
        if getattr(lora, 'use_preset', True) and preset:
            state.spreading_factor = preset.spreading_factor
            state.bandwidth_khz = preset.bandwidth_khz
        else:
            state.spreading_factor = int(getattr(lora, 'spread_factor', 0))
            state.bandwidth_khz = float(getattr(lora, 'bandwidth', 0))
        state.frequency_mhz = resolve_frequency_mhz(
            region=state.region, channel_num=getattr(lora, 'channel_num', 0),
            bandwidth_khz=state.bandwidth_khz, channel_name=state.primary_channel_name,
            modem_preset=state.modem_preset, use_preset=getattr(lora, 'use_preset', True),
            frequency_offset=getattr(lora, 'frequency_offset', 0),
            override_frequency=getattr(lora, 'override_frequency', 0))

    device = getattr(getattr(local_node, 'localConfig', None), 'device', None)
    telemetry = getattr(getattr(local_node, 'moduleConfig', None), 'telemetry', None)
    if device is not None:
        state.nodeinfo_interval_seconds = int(device.node_info_broadcast_secs)
    if telemetry is not None:
        state.telemetry_interval_seconds = int(telemetry.device_update_interval)
        state.telemetry_enabled = bool(telemetry.device_telemetry_enabled)

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
        _sync_lora_region,
        _sync_modem_preset,
        _sync_primary_channel_name,
    )

    changes: list[str] = []
    if request.nodeinfo_interval_seconds is not None:
        node.localConfig.device.node_info_broadcast_secs = request.nodeinfo_interval_seconds
        node.writeConfig('device')
        changes.append('nodeinfo_interval_seconds')
    if request.telemetry_interval_seconds is not None or request.telemetry_enabled is not None:
        if request.telemetry_interval_seconds is not None:
            node.moduleConfig.telemetry.device_update_interval = request.telemetry_interval_seconds
        if request.telemetry_enabled is not None:
            node.moduleConfig.telemetry.device_telemetry_enabled = request.telemetry_enabled
        node.writeConfig('telemetry')
        changes.append('telemetry')
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
        nodeinfo_interval_seconds=payload.get('nodeinfo_interval_seconds'),
        telemetry_interval_seconds=payload.get('telemetry_interval_seconds'),
        telemetry_enabled=payload.get('telemetry_enabled'),
    )


def parse_write_owner_payload(payload: dict[str, Any]) -> MeshtasticdWriteOwnerRequest:
    return MeshtasticdWriteOwnerRequest(
        long_name=str(payload.get("long_name", "")),
        short_name=str(payload.get("short_name", "")),
        hw_model=int(payload.get("hw_model", DEFAULT_HW_MODEL)),
    )
