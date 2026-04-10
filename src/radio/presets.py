"""Meshtastic modem presets and region frequency defaults.

Defines the 9 standard Meshtastic modem presets with their LoRa
modulation parameters and the default frequencies for each
supported region.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModemPreset:
    """LoRa modulation parameters for a single Meshtastic preset."""

    name: str
    display_name: str
    spreading_factor: int
    bandwidth_khz: float
    coding_rate: str
    tx_capable: bool = True


MODEM_PRESETS: dict[str, ModemPreset] = {
    "LONG_FAST": ModemPreset(
        name="LONG_FAST",
        display_name="LongFast",
        spreading_factor=11,
        bandwidth_khz=250,
        coding_rate="4/5",
    ),
    "LONG_MODERATE": ModemPreset(
        name="LONG_MODERATE",
        display_name="LongModerate",
        spreading_factor=11,
        bandwidth_khz=125,
        coding_rate="4/8",
    ),
    "LONG_SLOW": ModemPreset(
        name="LONG_SLOW",
        display_name="LongSlow",
        spreading_factor=12,
        bandwidth_khz=125,
        coding_rate="4/8",
    ),
    "VERY_LONG_SLOW": ModemPreset(
        name="VERY_LONG_SLOW",
        display_name="VeryLongSlow",
        spreading_factor=12,
        bandwidth_khz=62.5,
        coding_rate="4/8",
        tx_capable=False,
    ),
    "MEDIUM_FAST": ModemPreset(
        name="MEDIUM_FAST",
        display_name="MediumFast",
        spreading_factor=9,
        bandwidth_khz=250,
        coding_rate="4/8",
    ),
    "MEDIUM_SLOW": ModemPreset(
        name="MEDIUM_SLOW",
        display_name="MediumSlow",
        spreading_factor=10,
        bandwidth_khz=250,
        coding_rate="4/8",
    ),
    "SHORT_FAST": ModemPreset(
        name="SHORT_FAST",
        display_name="ShortFast",
        spreading_factor=7,
        bandwidth_khz=250,
        coding_rate="4/8",
    ),
    "SHORT_SLOW": ModemPreset(
        name="SHORT_SLOW",
        display_name="ShortSlow",
        spreading_factor=8,
        bandwidth_khz=250,
        coding_rate="4/8",
    ),
    "SHORT_TURBO": ModemPreset(
        name="SHORT_TURBO",
        display_name="ShortTurbo",
        spreading_factor=7,
        bandwidth_khz=500,
        coding_rate="4/5",
    ),
}


REGION_DEFAULTS: dict[str, dict] = {
    "US": {"frequency_mhz": 906.875, "name": "US 915"},
    "EU_868": {"frequency_mhz": 869.525, "name": "EU 868"},
    "ANZ": {"frequency_mhz": 916.0, "name": "Australia/NZ"},
    "IN": {"frequency_mhz": 865.4625, "name": "India 865"},
    "KR": {"frequency_mhz": 921.9, "name": "Korea 920"},
    "SG_923": {"frequency_mhz": 923.0, "name": "Singapore 923"},
}

SUPPORTED_REGIONS = list(REGION_DEFAULTS.keys())


def get_preset(name: str) -> ModemPreset | None:
    """Look up a modem preset by name (case-insensitive)."""
    return MODEM_PRESETS.get(name.upper())


def preset_from_params(
    sf: int, bw_khz: float, cr: str
) -> str | None:
    """Reverse-lookup: find the preset name matching SF/BW/CR."""
    bw_int = int(bw_khz) if bw_khz == int(bw_khz) else bw_khz
    for name, preset in MODEM_PRESETS.items():
        p_bw = int(preset.bandwidth_khz) if preset.bandwidth_khz == int(preset.bandwidth_khz) else preset.bandwidth_khz
        if preset.spreading_factor == sf and p_bw == bw_int and preset.coding_rate == cr:
            return name
    return None


def all_presets_list() -> list[dict]:
    """Return all presets as dicts for API/frontend consumption."""
    return [
        {
            "name": p.name,
            "display_name": p.display_name,
            "sf": p.spreading_factor,
            "bw_khz": p.bandwidth_khz,
            "cr": p.coding_rate,
            "tx_capable": p.tx_capable,
        }
        for p in MODEM_PRESETS.values()
    ]
