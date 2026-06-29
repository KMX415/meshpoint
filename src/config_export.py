"""Public Meshtastic Quick Deploy export (QR URL + JSON).

Builds a standard ``https://meshtastic.org/e/#…`` channel URL using the
Meshpoint's radio region and modem preset with the **public default PSK**
only. Private ``channel_keys`` and non-default secrets are never included.
"""

from __future__ import annotations

import base64

from meshtastic.protobuf import apponly_pb2, config_pb2

from src.config import AppConfig
from src.radio.presets import MODEM_PRESETS, preset_from_params

# Meshtastic well-known default key (base64 ``AQ==``).
_PUBLIC_PSK = b"\x01"

_REGION_TO_PROTO: dict[str, str] = {
    "US": "US",
    "EU_868": "EU_868",
    "ANZ": "ANZ",
    "IN": "IN",
    "KR": "KR",
    "SG_923": "SG_923",
}


def build_quick_deploy_export(cfg: AppConfig) -> dict:
    """Return public channel parameters and a Meshtastic-compatible share URL."""
    radio = cfg.radio
    mt = cfg.meshtastic
    tx = cfg.transmit

    preset_key = preset_from_params(
        radio.spreading_factor,
        radio.bandwidth_khz,
        radio.coding_rate,
    ) or "LONG_FAST"
    preset = MODEM_PRESETS.get(preset_key)
    display = preset.display_name if preset else preset_key

    channel_name = (mt.primary_channel_name or display or "LongFast").strip()
    if len(channel_name) > 11:
        channel_name = channel_name[:11]

    channel_set = apponly_pb2.ChannelSet()
    lora = channel_set.lora_config
    lora.use_preset = True
    try:
        lora.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.Value(
            preset_key
        )
    except ValueError:
        lora.modem_preset = config_pb2.Config.LoRaConfig.ModemPreset.LONG_FAST

    region_proto = _REGION_TO_PROTO.get(radio.region or "US", "US")
    try:
        lora.region = config_pb2.Config.LoRaConfig.RegionCode.Value(region_proto)
    except ValueError:
        lora.region = config_pb2.Config.LoRaConfig.RegionCode.US

    lora.hop_limit = max(0, min(int(tx.hop_limit or 3), 7))
    lora.tx_enabled = True

    settings = channel_set.settings.add()
    settings.name = channel_name
    settings.psk = _PUBLIC_PSK

    raw = channel_set.SerializeToString()
    fragment = (
        base64.urlsafe_b64encode(raw)
        .decode("ascii")
        .replace("=", "")
        .replace("+", "-")
        .replace("/", "_")
    )
    meshtastic_url = f"https://meshtastic.org/e/#{fragment}"

    payload = {
        "channel_name": channel_name,
        "frequency_mhz": radio.frequency_mhz,
        "region": radio.region,
        "modem_preset": preset_key,
        "modem_preset_display": display,
        "spreading_factor": radio.spreading_factor,
        "bandwidth_khz": radio.bandwidth_khz,
        "coding_rate": radio.coding_rate,
        "hop_limit": lora.hop_limit,
        "meshtastic_url": meshtastic_url,
        "psk_included": False,
        "device_name": cfg.device.device_name,
        "note": (
            "Public default channel only (standard Meshtastic PSK). "
            "Private channel keys from this Meshpoint are not exported."
        ),
    }
    _assert_no_secrets(payload)
    return payload


def _assert_no_secrets(payload: dict) -> None:
    """Defensive check: response must not leak configured private keys."""
    if payload.get("psk_included"):
        raise ValueError("export must not include private PSK material")
    forbidden = {"psk_b64", "default_key_b64", "channel_keys", "private_key"}
    for key in payload:
        if key in forbidden or key.endswith("_key_b64"):
            raise ValueError(f"export must not include secret field: {key}")
